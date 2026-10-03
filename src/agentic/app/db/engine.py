"""Engine/session management for Agentic's SQLite data store.

The database file always lives at ``workspace/data/agentic.db`` (relative
to the repo/working directory Agentic is run from), matching the rest of
Agentic's config-driven ``workspace``-relative layout. The path can be
overridden (e.g. for tests) via the ``AGENTIC_SQLITE_PATH`` environment
variable.
"""

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_SQLITE_RELATIVE_PATH = os.path.join("workspace", "data", "agentic.db")

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def get_sqlite_path() -> str:
    """Resolve the SQLite file path, honoring the ``AGENTIC_SQLITE_PATH`` override."""
    return os.getenv("AGENTIC_SQLITE_PATH", DEFAULT_SQLITE_RELATIVE_PATH)


def get_sqlite_url() -> str:
    """Build the ``sqlite:///`` URL for the resolved SQLite path."""
    path = get_sqlite_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def get_engine() -> Engine:
    """Get (creating if needed) the module-level SQLAlchemy engine.

    Cached at module level so repeated calls (e.g. from multiple MCP
    tool invocations) reuse the same connection pool instead of opening
    a new SQLite connection every time.
    """
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_sqlite_url(),
            connect_args={"check_same_thread": False},
        )
    return _engine


def get_session_factory() -> sessionmaker:
    """Get (creating if needed) the module-level session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


def get_session() -> Session:
    """Create a new `Session` bound to the SQLite engine.

    Callers are responsible for closing the session (e.g. via
    ``with get_session() as session:``).
    """
    return get_session_factory()()


def reset_engine() -> None:
    """Dispose of and clear the cached engine/session factory.

    Used by tests that point ``AGENTIC_SQLITE_PATH`` at a temp file and
    need a fresh engine for that path.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None

