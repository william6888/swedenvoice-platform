"""
timing_utils.py – Per-request timing instrumentation for Railway deployment logs.

Usage:
    from timing_utils import RequestTimer

    timer = RequestTimer(path="/vapi/webhook", method="POST")
    with timer.measure("json_parse"):
        body = await request.json()
    with timer.measure("supabase_select_menu"):
        result = supabase.table("menu").select("*").execute()
    timer.log(status_code=200)

Each request emits ONE JSON line to stdout, captured by Railway deployment logs.
No sensitive data (keys, secrets, request/response bodies) is ever logged.
"""

import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Optional


class RequestTimer:
    """
    Collects per-step timing for a single request and emits one structured
    JSON log line to stdout when log() is called.

    All times are measured with time.perf_counter() for sub-millisecond
    precision. The wall-clock timestamp is captured at construction time.

    Example output (one line, pretty-printed here for readability):
    {
        "request_id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp": "2026-03-29T10:28:22.124Z",
        "path": "/vapi/webhook",
        "method": "POST",
        "status_code": 200,
        "total_time_ms": 3421,
        "timings": {
            "json_parse_ms": 2,
            "auth_check_ms": 1,
            "supabase_select_restaurant_ms": 45,
            "supabase_insert_order_ms": 1200,
            "vonage_sms_ms": 1850,
            "item_mapping_ms": 15,
            "other_ms": 308
        },
        "error": null
    }
    """

    def __init__(self, path: str = "", method: str = "POST"):
        self.request_id: str = str(uuid.uuid4())
        self.timestamp: str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
            f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
        self.path: str = path
        self.method: str = method
        self._start: float = time.perf_counter()
        self._timings: Dict[str, float] = {}   # step_name -> elapsed_ms
        self._active_step: Optional[str] = None
        self._step_start: float = 0.0

    @contextmanager
    def measure(self, step: str):
        """
        Context manager that records elapsed milliseconds for *step*.

        with timer.measure("supabase_insert_order"):
            result = supabase.table("orders").insert(row).execute()

        If an exception propagates out of the block the timing is still
        recorded (partial data is better than no data).
        """
        t0 = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            # Accumulate in case the same step is measured more than once
            self._timings[step] = self._timings.get(step, 0.0) + elapsed_ms

    def record(self, step: str, elapsed_ms: float) -> None:
        """
        Manually record a timing (e.g. when you already have start/end times).

        elapsed_ms = (time.perf_counter() - t0) * 1000
        timer.record("vonage_sms", elapsed_ms)
        """
        self._timings[step] = self._timings.get(step, 0.0) + elapsed_ms

    def log(self, status_code: int = 200, error: Optional[str] = None) -> None:
        """
        Emit one JSON line to stdout with all collected timings.

        Computes an "other_ms" bucket = total_time_ms minus all named steps,
        so the numbers always add up and untracked overhead is visible.

        Call this once at the very end of the request handler (in a
        finally block so it fires even on exceptions).
        """
        total_ms = (time.perf_counter() - self._start) * 1000.0

        # Build named timings dict (round to 1 decimal for readability)
        named: Dict[str, float] = {
            k + "_ms": round(v, 1) for k, v in self._timings.items()
        }

        # "other_ms" = total minus all explicitly measured steps
        accounted = sum(self._timings.values())
        other_ms = max(0.0, total_ms - accounted)
        named["other_ms"] = round(other_ms, 1)

        record = {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "path": self.path,
            "method": self.method,
            "status_code": status_code,
            "total_time_ms": round(total_ms, 1),
            "timings": named,
            "error": error,
        }

        try:
            print(json.dumps(record, ensure_ascii=False), flush=True)
        except Exception:
            # Last-resort: never let logging crash the request
            pass
