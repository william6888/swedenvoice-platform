"""
FakeSupabase – minimal in-memory simulering av supabase-py så hot path kan testas
deterministiskt. Stödjer .table(name).insert/select/update/delete/upsert/eq/in_/limit/order/lte/lt/execute().
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Callable, Dict, List, Optional


class _Result:
    def __init__(self, data: List[Dict[str, Any]], error: Optional[str] = None):
        self.data = data
        self.error = error


class _Query:
    def __init__(self, db: "FakeSupabase", table_name: str):
        self._db = db
        self._table_name = table_name
        self._mode: Optional[str] = None
        self._payload: Any = None
        self._filters: List[Callable[[Dict[str, Any]], bool]] = []
        self._select_cols: Optional[str] = None
        self._order: Optional[Dict[str, Any]] = None
        self._limit: Optional[int] = None
        self._range: Optional[tuple] = None
        self._upsert_conflict: Optional[str] = None

    # ----- read -----
    def select(self, cols: str = "*"):
        self._mode = "select"
        self._select_cols = cols
        return self

    def order(self, col: str, desc: bool = False):
        self._order = {"col": col, "desc": desc}
        return self

    def limit(self, n: int):
        self._limit = int(n)
        return self

    def range(self, start: int, end: int):
        # PostgREST range är inklusivt i båda ändar.
        self._range = (int(start), int(end))
        return self

    # ----- write -----
    def insert(self, payload: Any):
        self._mode = "insert"
        self._payload = payload
        return self

    def upsert(self, payload: Any, on_conflict: Optional[str] = None):
        self._mode = "upsert"
        self._payload = payload
        self._upsert_conflict = on_conflict
        return self

    def update(self, payload: Dict[str, Any]):
        self._mode = "update"
        self._payload = payload
        return self

    def delete(self):
        self._mode = "delete"
        return self

    # ----- filters -----
    def eq(self, col: str, val: Any):
        self._filters.append(lambda r, c=col, v=val: r.get(c) == v)
        return self

    def in_(self, col: str, values: List[Any]):
        vs = list(values)
        self._filters.append(lambda r, c=col, v=vs: r.get(c) in v)
        return self

    def lte(self, col: str, val: Any):
        self._filters.append(lambda r, c=col, v=val: (r.get(c) is None) or (r.get(c) <= v))
        return self

    def lt(self, col: str, val: Any):
        self._filters.append(lambda r, c=col, v=val: (r.get(c) is not None) and (r.get(c) < v))
        return self

    # ----- exec -----
    def execute(self) -> _Result:
        with self._db._lock:
            if self._db.simulate_missing_table.get(self._table_name):
                raise RuntimeError(f"relation \"public.{self._table_name}\" does not exist")
            if self._db.simulate_unique_violation_on_insert and self._mode == "insert":
                # Bara för idempotency_records-testet.
                if self._table_name == "idempotency_records":
                    raise RuntimeError("duplicate key value violates unique constraint")
            if self._db.fail_next_on_table.get(self._table_name):
                self._db.fail_next_on_table.pop(self._table_name, None)
                raise RuntimeError("simulated transient supabase failure")
            tbl = self._db.tables.setdefault(self._table_name, [])
            if self._mode == "insert":
                rows = self._payload if isinstance(self._payload, list) else [self._payload]
                inserted = []
                for r in rows:
                    row = dict(r)
                    if "id" not in row:
                        row["id"] = str(uuid.uuid4())
                    # Unik-kollision för idempotency_records.key
                    if self._table_name == "idempotency_records":
                        for existing in tbl:
                            if existing.get("key") == row.get("key"):
                                raise RuntimeError("duplicate key value violates unique constraint")
                    if self._table_name == "orders":
                        for existing in tbl:
                            if (
                                row.get("idempotency_key")
                                and existing.get("idempotency_key") == row.get("idempotency_key")
                            ):
                                raise RuntimeError("duplicate key value violates unique constraint")
                    tbl.append(row)
                    inserted.append(row)
                return _Result(inserted)
            if self._mode == "upsert":
                rows = self._payload if isinstance(self._payload, list) else [self._payload]
                conflict = self._upsert_conflict
                results = []
                for r in rows:
                    row = dict(r)
                    matched = None
                    if conflict:
                        for existing in tbl:
                            if existing.get(conflict) == row.get(conflict):
                                matched = existing
                                break
                    if matched:
                        matched.update(row)
                        results.append(matched)
                    else:
                        if "id" not in row:
                            row["id"] = str(uuid.uuid4())
                        tbl.append(row)
                        results.append(row)
                return _Result(results)
            if self._mode == "select":
                rows = list(tbl)
                for f in self._filters:
                    rows = [r for r in rows if f(r)]
                if self._order:
                    col = self._order["col"]
                    desc = self._order["desc"]
                    rows.sort(key=lambda r: r.get(col) or "", reverse=bool(desc))
                if self._range is not None:
                    start, end = self._range
                    rows = rows[start : end + 1]
                if self._limit is not None:
                    rows = rows[: self._limit]
                return _Result(rows)
            if self._mode == "update":
                rows = list(tbl)
                for f in self._filters:
                    rows = [r for r in rows if f(r)]
                for r in rows:
                    r.update(self._payload or {})
                return _Result(rows)
            if self._mode == "delete":
                rows = list(tbl)
                for f in self._filters:
                    rows = [r for r in rows if f(r)]
                for r in rows:
                    if r in tbl:
                        tbl.remove(r)
                return _Result(rows)
            return _Result([])


class _FakeBucket:
    def __init__(self, store: Dict[str, bytes]):
        self._store = store

    def upload(self, path: str, data: bytes, file_options: Optional[dict] = None):
        self._store[path] = bytes(data)
        return {"path": path}

    def download(self, path: str) -> bytes:
        if path not in self._store:
            raise RuntimeError(f"Object not found: {path}")
        return self._store[path]

    def list(self, *args, **kwargs):
        return [{"name": k} for k in self._store]

    def remove(self, paths):
        for p in (paths if isinstance(paths, list) else [paths]):
            self._store.pop(p, None)
        return {"removed": paths}


class _FakeStorage:
    def __init__(self):
        self.buckets: Dict[str, Dict[str, bytes]] = {}

    def from_(self, bucket: str) -> _FakeBucket:
        return _FakeBucket(self.buckets.setdefault(bucket, {}))


class FakeSupabase:
    def __init__(self):
        self.tables: Dict[str, List[Dict[str, Any]]] = {}
        self.simulate_missing_table: Dict[str, bool] = {}
        self.fail_next_on_table: Dict[str, bool] = {}
        self.simulate_unique_violation_on_insert = False
        self.storage = _FakeStorage()
        self._lock = threading.RLock()

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    # ---- helpers ----
    def get_orders(self) -> List[Dict[str, Any]]:
        return list(self.tables.get("orders", []))

    def get_idempotency(self) -> List[Dict[str, Any]]:
        return list(self.tables.get("idempotency_records", []))

    def get_events(self) -> List[Dict[str, Any]]:
        return list(self.tables.get("order_events", []))

    def get_incidents(self) -> List[Dict[str, Any]]:
        return list(self.tables.get("incidents", []))

    def get_sms_jobs(self) -> List[Dict[str, Any]]:
        return list(self.tables.get("sms_jobs", []))
