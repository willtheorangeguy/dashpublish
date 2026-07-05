"""Shared fixtures for unit tests."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from dashpublish.db.engine import create_all_for_tests, get_engine


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.sqlite")


@pytest.fixture()
def session(db_path: str) -> Iterator[Session]:
    engine = get_engine(db_path)
    create_all_for_tests(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    db = factory()
    try:
        yield db
        db.commit()
    finally:
        db.close()
