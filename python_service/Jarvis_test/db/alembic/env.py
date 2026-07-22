"""
Alembic environment. Overrides sqlalchemy.url from our app config
so we don't have to duplicate connection settings.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from config import settings


# Alembic Config object, provides access to .ini values.
alembic_config = context.config

# Override the URL from the .ini with our env-driven URL.
alembic_config.set_main_option("sqlalchemy.url", settings.database_url)

# Logging setup from .ini.
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# We use raw SQL migrations (no ORM models), so target_metadata stays None.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations without an Engine - just emit SQL to stdout."""
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the live database."""
    connectable = engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}),
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