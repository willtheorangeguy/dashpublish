"""Tests for upgrade_db: fresh migrate, create_all-stamping, and idempotency."""

from __future__ import annotations

from sqlalchemy import inspect

from dashpublish.db.engine import create_all_for_tests, get_engine, upgrade_db


def test_upgrade_fresh_db(tmp_path):
    db = tmp_path / "fresh.sqlite"
    upgrade_db(db)
    inspector = inspect(get_engine(db))
    assert inspector.has_table("videos")
    assert inspector.has_table("alembic_version")


def test_upgrade_stamps_create_all_db(tmp_path):
    """A DB whose tables came from Base.metadata.create_all (no alembic_version)
    must be stamped, not re-migrated (which would fail on CREATE TABLE)."""
    db = tmp_path / "createall.sqlite"
    create_all_for_tests(get_engine(db))
    inspector = inspect(get_engine(db))
    assert inspector.has_table("videos") and not inspector.has_table("alembic_version")

    upgrade_db(db)  # must not raise "table ... already exists"
    assert inspect(get_engine(db)).has_table("alembic_version")


def test_upgrade_idempotent(tmp_path):
    db = tmp_path / "twice.sqlite"
    upgrade_db(db)
    upgrade_db(db)  # no-op second run
    assert inspect(get_engine(db)).has_table("alembic_version")
