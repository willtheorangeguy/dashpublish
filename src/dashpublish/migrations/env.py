"""Alembic environment for dashpublish.

The database URL is resolved in this order:
1. ``DASHPUBLISH_DB_URL`` env var (a full SQLAlchemy URL), if set.
2. ``DASHPUBLISH_DB`` env var (a plain sqlite file path), if set.
3. ``sqlalchemy.url`` from alembic.ini (default: ./dashpublish-dev.sqlite).

The ORM metadata is imported from ``dashpublish.db.models`` for autogenerate support.
``render_as_batch`` is enabled for SQLite ALTER support.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# These scripts live inside the package (src/dashpublish/migrations). Make the
# src/ layout importable when alembic runs from a repo checkout where the
# package isn't installed.
_SRC = Path(__file__).resolve().parents[2]
if (_SRC / "dashpublish" / "__init__.py").is_file() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dashpublish.db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_url() -> str:
    url = os.environ.get("DASHPUBLISH_DB_URL")
    if url:
        return url
    db_path = os.environ.get("DASHPUBLISH_DB")
    if db_path:
        return f"sqlite:///{db_path}"
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
