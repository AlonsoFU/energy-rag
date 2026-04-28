import pytest
from testcontainers.postgres import PostgresContainer
from alembic.config import Config
from alembic import command
import os


@pytest.fixture(scope="session")
def postgres_container():
    """Spin up Postgres + pgvector for integration tests."""
    with PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="test",
    ) as pg:
        os.environ["POSTGRES_HOST"] = pg.get_container_host_ip()
        os.environ["POSTGRES_PORT"] = str(pg.get_exposed_port(5432))
        os.environ["POSTGRES_DB"] = "test"
        os.environ["POSTGRES_USER"] = "test"
        os.environ["POSTGRES_PASSWORD"] = "test"
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-fake"

        # Re-import settings so it picks up env
        from src.core import config as cfg_module
        cfg_module.settings = cfg_module.Settings()

        # Reset connection pool so it uses the new DSN. The connection module
        # imported `settings` by name at load time, so rebind that reference
        # too — otherwise get_pool() builds a DSN from the stale instance.
        from src.storage import connection as conn_module
        conn_module.settings = cfg_module.settings
        conn_module.close_pool()

        # Run migrations
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", cfg_module.settings.dsn())
        command.upgrade(alembic_cfg, "head")

        yield pg

        # Cleanup pool before container exits
        conn_module.close_pool()


@pytest.fixture
def db_clean(postgres_container):
    """Truncate all tables between tests for isolation."""
    from src.storage.connection import with_connection
    yield
    with with_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                TRUNCATE TABLE
                  fragmentos, referencias, consultas_log, descargas_estado,
                  aliases_aprendidos, conceptos, articulos, normas
                RESTART IDENTITY CASCADE;
            """)
        conn.commit()
