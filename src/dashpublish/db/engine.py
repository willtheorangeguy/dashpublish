"""Database engine, session management, and pragmas.

SQLite is configured with WAL journaling and foreign-key enforcement. Sessions are
obtained via :func:`session_scope` (a transactional context manager) or via the
:class:`sqlalchemy.orm.sessionmaker` returned by :func:`get_sessionmaker`.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from dashpublish.db.models import Base

_engines: dict[str, Engine] = {}


def _apply_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(db_path: str | Path) -> Engine:
    """Return a cached SQLite engine for ``db_path`` (":memory:" allowed)."""
    key = str(db_path)
    engine = _engines.get(key)
    if engine is not None:
        return engine

    if key == ":memory:":
        url = "sqlite://"
    else:
        url = f"sqlite:///{key}"

    engine = create_engine(
        url,
        future=True,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _apply_sqlite_pragmas)
    _engines[key] = engine
    return engine


def get_sessionmaker(db_path: str | Path) -> sessionmaker[Session]:
    """Return a sessionmaker bound to the engine for ``db_path``."""
    return sessionmaker(bind=get_engine(db_path), expire_on_commit=False, future=True)


@contextmanager
def session_scope(db_path: str | Path) -> Iterator[Session]:
    """Provide a transactional session: commit on success, rollback on error."""
    factory = get_sessionmaker(db_path)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all_for_tests(engine: Engine) -> None:
    """Create all tables directly from the ORM metadata (test-only shortcut)."""
    Base.metadata.create_all(engine)


def upgrade_db(db_path: str | Path) -> None:
    """Run Alembic migrations up to head against ``db_path`` programmatically."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    project_root = Path(__file__).resolve().parents[3]
    ini_path = project_root / "alembic.ini"

    cfg = AlembicConfig(str(ini_path))
    cfg.set_main_option("script_location", str(project_root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")
