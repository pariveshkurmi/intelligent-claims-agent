"""Initialize database schema by executing schema.sql."""

import os
import sys

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.db.connection import get_connection

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def init_db() -> None:
    """Execute schema.sql to initialize all tables, indices, and extensions."""
    print(f"Reading schema from: {SCHEMA_PATH}")
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
    print("[SUCCESS] Schema initialized successfully!")



if __name__ == "__main__":
    init_db()
