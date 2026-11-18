"""Lightweight health check script for Docker container."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def check_health() -> int:
    try:
        db_path = Path(os.environ.get("DATABASE_PATH", "data/promoradar.db"))
        if db_path.exists():
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                cursor = conn.execute("PRAGMA quick_check;")
                result = cursor.fetchone()
                if not result or result[0] != "ok":
                    print(
                        f"Healthcheck FAILED: SQLite check returned '{result}'",
                        file=sys.stderr,
                    )
                    return 1

        print("Healthcheck OK")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Healthcheck FAILED with exception: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(check_health())
