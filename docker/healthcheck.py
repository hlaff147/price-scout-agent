"""Lightweight health check script for Docker container."""

import sys
import sqlite3
from pathlib import Path

def check_health() -> int:
    try:
        db_path = Path("data/promoradar.db")
        # Se o banco já foi criado, valida integridade
        if db_path.exists():
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                cursor = conn.execute("PRAGMA quick_check;")
                result = cursor.fetchone()
                if not result or result[0] != "ok":
                    print(f"Healthcheck FAILED: SQLite check returned '{result}'", file=sys.stderr)
                    return 1

        print("Healthcheck OK")
        return 0
    except Exception as exc:
        print(f"Healthcheck FAILED with exception: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(check_health())
