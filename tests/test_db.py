"""Tests for the SQLite data store (engine, migrations, repository CRUD)."""

import subprocess
import sys
from pathlib import Path

import pytest

from agentic.app.db import engine as db_engine
from agentic.app.db import repository
from agentic.app.db.schemas import DataRecordCreate, DataRecordRead, DataRecordUpdate


@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    """Point the SQLite data store at a temp file, migrated to head, for
    the duration of a test, then reset the cached engine afterwards so
    other tests aren't affected.
    """
    db_path = tmp_path / "agentic_test.db"
    monkeypatch.setenv("AGENTIC_SQLITE_PATH", str(db_path))
    db_engine.reset_engine()

    repo_root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo_root,
        env={"AGENTIC_SQLITE_PATH": str(db_path), **_current_env()},
        check=True,
        capture_output=True,
        text=True,
    )

    yield db_path

    db_engine.reset_engine()


def _current_env():
    import os

    return dict(os.environ)


# --------------------------------------------------------------------------
# engine
# --------------------------------------------------------------------------

def test_get_sqlite_path_honors_env_override(monkeypatch, tmp_path):
    custom_path = str(tmp_path / "custom.db")
    monkeypatch.setenv("AGENTIC_SQLITE_PATH", custom_path)
    assert db_engine.get_sqlite_path() == custom_path


def test_get_engine_creates_sqlite_file(sqlite_db):
    engine = db_engine.get_engine()
    with engine.connect():
        pass
    assert sqlite_db.exists()


# --------------------------------------------------------------------------
# repository CRUD
# --------------------------------------------------------------------------

def test_create_and_get_record(sqlite_db):
    created = repository.create_record(DataRecordCreate(key="greeting", value="hello world"))
    assert isinstance(created, DataRecordRead)
    assert created.key == "greeting"
    assert created.value == "hello world"

    fetched = repository.get_record("greeting")
    assert fetched.value == "hello world"


def test_create_record_duplicate_key_raises(sqlite_db):
    repository.create_record(DataRecordCreate(key="dup", value="first"))
    with pytest.raises(repository.RecordAlreadyExistsError):
        repository.create_record(DataRecordCreate(key="dup", value="second"))


def test_get_record_missing_raises(sqlite_db):
    with pytest.raises(repository.RecordNotFoundError):
        repository.get_record("does-not-exist")


def test_update_record(sqlite_db):
    repository.create_record(DataRecordCreate(key="counter", value="1"))
    updated = repository.update_record("counter", DataRecordUpdate(value="2"))
    assert updated.value == "2"
    assert repository.get_record("counter").value == "2"


def test_update_record_missing_raises(sqlite_db):
    with pytest.raises(repository.RecordNotFoundError):
        repository.update_record("does-not-exist", DataRecordUpdate(value="value"))


def test_delete_record(sqlite_db):
    repository.create_record(DataRecordCreate(key="temp", value="value"))
    repository.delete_record("temp")
    with pytest.raises(repository.RecordNotFoundError):
        repository.get_record("temp")


def test_delete_record_missing_raises(sqlite_db):
    with pytest.raises(repository.RecordNotFoundError):
        repository.delete_record("does-not-exist")


def test_list_records_orders_by_most_recently_updated(sqlite_db):
    repository.create_record(DataRecordCreate(key="a", value="1"))
    repository.create_record(DataRecordCreate(key="b", value="2"))
    repository.update_record("a", DataRecordUpdate(value="1-updated"))

    records = repository.list_records()
    keys_in_order = [r.key for r in records]
    assert keys_in_order[0] == "a"
    assert "b" in keys_in_order


def test_list_records_respects_limit(sqlite_db):
    for i in range(5):
        repository.create_record(DataRecordCreate(key=f"key{i}", value=str(i)))

    assert len(repository.list_records(limit=2)) == 2

