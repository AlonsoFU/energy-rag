import pytest


@pytest.mark.integration
def test_postgres_fixture_provides_db(postgres_container, db_clean):
    from src.storage.connection import with_connection
    with with_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM normas")
            assert cur.fetchone()[0] == 0
