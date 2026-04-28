from contextlib import contextmanager
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector
from src.core.config import settings

_pool: ConnectionPool | None = None


def _configure_connection(conn) -> None:
    """Register pgvector type adapter on every pooled connection."""
    register_vector(conn)


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=settings.dsn(),
            min_size=1,
            max_size=10,
            open=False,  # don't connect at construction
            configure=_configure_connection,
        )
    return _pool


@contextmanager
def with_connection():
    pool = get_pool()
    pool.open()  # idempotent in psycopg-pool 3.x
    with pool.connection() as conn:
        yield conn


def close_pool():
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:
            pass
        _pool = None
