"""
Postgres connection pool using psycopg3.

Lifecycle is tied to FastAPI startup/shutdown via the functions below.
Always acquire connections via `with pool.connection() as conn:` so they
return to the pool, even on exceptions.
"""

import logging
from contextlib import contextmanager
from typing import Iterator

from psycopg import Connection
from psycopg_pool import ConnectionPool

from config import settings


logger = logging.getLogger(__name__)

# Created on startup, closed on shutdown.
_pool: ConnectionPool | None = None


def init_pool() -> None:
    """Initialize the global connection pool. Call once at startup."""
    global _pool
    if _pool is not None:
        return
    _pool = ConnectionPool(
        conninfo=settings.database_dsn,
        min_size=1,
        max_size=10,
        open=True,
    )
    logger.info(
        "Postgres pool ready: host=%s db=%s",
        settings.DB_HOST, settings.DB_NAME,
    )


def close_pool() -> None:
    """Close all connections. Call on shutdown."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        logger.info("Postgres pool closed")


@contextmanager
def get_connection() -> Iterator[Connection]:
    """
    Acquire a connection from the pool. Use as a context manager:

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
    """
    if _pool is None:
        raise RuntimeError("DB pool not initialized; call init_pool() first")
    with _pool.connection() as conn:
        yield conn