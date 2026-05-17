"""Pytest-konfiguration: lägg projektroten i sys.path så lokala moduler är importerbara."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Säkerställ deterministiska defaults i tester.
os.environ.setdefault("ORDER_REQUIRE_DB_COMMIT", "true")
os.environ.setdefault("DASHBOARD_FROM_DB", "false")
os.environ.setdefault("DRAFT_SIGNING_SECRET", "test-secret-rotate")
os.environ.setdefault("ADMIN_SECRET", "test-admin")
