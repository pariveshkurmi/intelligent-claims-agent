"""Database connection and pooling utilities with pgvector support."""

import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional
import psycopg
from psycopg.rows import dict_row
from pgvector.psycopg import register_vector
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "claims_db")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


def get_connection() -> psycopg.Connection:
    """Create a new PostgreSQL connection with pgvector registered, dict_row, and 3s connect timeout."""
    conn = psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        row_factory=dict_row,
        autocommit=False,
        connect_timeout=3,
    )
    register_vector(conn)
    return conn


@contextmanager
def get_db_cursor(commit: bool = True) -> Generator[psycopg.Cursor, None, None]:
    """Context manager yielding a cursor with transactional control."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_query(query: str, params: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Execute a read query and return list of dictionary records."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(query, params)
        if cur.description:
            return cur.fetchall()
        return []


def execute_mutation(query: str, params: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Execute an INSERT/UPDATE/DELETE mutation and optionally return RETURNING clause."""
    with get_db_cursor(commit=True) as cur:
        cur.execute(query, params)
        if cur.description:
            return cur.fetchone()
        return None


def execute_batch(query: str, param_list: List[Any]) -> None:
    """Execute a batch mutation."""
    with get_db_cursor(commit=True) as cur:
        cur.executemany(query, param_list)
