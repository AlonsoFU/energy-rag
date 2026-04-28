import pytest
from src.storage.connection import get_pool, with_connection


def test_pool_returns_singleton():
    p1 = get_pool()
    p2 = get_pool()
    assert p1 is p2


@pytest.mark.integration
def test_with_connection_executes_query(postgres_container):
    with with_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS x")
            row = cur.fetchone()
            assert row[0] == 1
