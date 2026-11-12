"""Postgres access: one-off connections and a shared, lazily created pool."""
import threading

import psycopg
from psycopg_pool import ConnectionPool

from .settings import get_settings

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def connect() -> psycopg.Connection:
    """A new connection with autocommit off. Use as a context manager."""
    return psycopg.connect(get_settings().database_url, autocommit=False)


def pool() -> ConnectionPool:
    """The process-wide connection pool (created on first use)."""
    global _pool
    with _lock:
        if _pool is None:
            _pool = ConnectionPool(get_settings().database_url, min_size=1, max_size=10, open=True)
        return _pool


def close_pool() -> None:
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None
