"""Tests for the sqlite_store MCP tool wrappers."""

import subprocess
import sys
import os
from pathlib import Path

import pytest

from agentic.agentic_mcp.sqlite_store.tools import get_sqlite_store_tools
from agentic.app.db import engine as db_engine


@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    db_path = tmp_path / "agentic_test.db"
    monkeypatch.setenv("AGENTIC_SQLITE_PATH", str(db_path))
    db_engine.reset_engine()

    repo_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "AGENTIC_SQLITE_PATH": str(db_path)}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    yield db_path

    db_engine.reset_engine()


@pytest.fixture()
def tools(sqlite_db):
    (
        create,
        get,
        update,
        delete,
        list_,
    ) = get_sqlite_store_tools()
    return {
        "create": create,
        "get": get,
        "update": update,
        "delete": delete,
        "list": list_,
    }


def test_create_get_update_delete_round_trip(tools):
    created = tools["create"]("note", "hello")
    assert created["key"] == "note"
    assert created["value"] == "hello"

    fetched = tools["get"]("note")
    assert fetched["value"] == "hello"

    updated = tools["update"]("note", "updated")
    assert updated["value"] == "updated"

    deleted = tools["delete"]("note")
    assert deleted == {"deleted": "note"}

    missing = tools["get"]("note")
    assert "error" in missing


def test_create_duplicate_key_returns_error(tools):
    tools["create"]("dup", "first")
    result = tools["create"]("dup", "second")
    assert "error" in result


def test_update_missing_key_returns_error(tools):
    result = tools["update"]("missing", "value")
    assert "error" in result


def test_delete_missing_key_returns_error(tools):
    result = tools["delete"]("missing")
    assert "error" in result


def test_list_records(tools):
    tools["create"]("a", "1")
    tools["create"]("b", "2")
    records = tools["list"]()
    keys = [r["key"] for r in records]
    assert "a" in keys and "b" in keys

