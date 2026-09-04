"""SQLAlchemy ORM models for Agentic's SQLite-backed data store.

Schema changes must be accompanied by an Alembic migration under
``alembic/versions/`` (see ``alembic/env.py``, which imports ``Base``
from this module as its migration target).
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all Agentic ORM models."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataRecord(Base):
    """Generic key/value record stored in the ``data_records`` table.

    Intentionally generic (rather than a bespoke table per feature) so it
    can back arbitrary agent/tool state; ``key`` is unique so callers can
    treat it as a simple key-value store.
    """

    __tablename__ = "data_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"DataRecord(id={self.id!r}, key={self.key!r})"

