from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from src.core.config import settings

config = context.config
# Use psycopg (v3) driver — SQLAlchemy defaults to psycopg2 for "postgresql://".
_dsn = settings.dsn().replace("postgresql://", "postgresql+psycopg://", 1)
config.set_main_option("sqlalchemy.url", _dsn)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None  # we use raw SQL migrations, not autogenerate

def run_migrations_offline():
    context.configure(
        url=_dsn,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
