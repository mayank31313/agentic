"""CRUD repository for `DataRecord`, isolating persistence logic from
tool/agent code (see the MCP tool wrappers in
``agentic_mcp/sqlite_store/tools.py``).

Inputs are validated via `schemas.DataRecordCreate`/`DataRecordUpdate`
and results are returned as `schemas.DataRecordRead` instances, keeping
Pydantic validation/serialization separate from the SQLAlchemy ORM layer
in `models.py`.
"""

from __future__ import annotations

from agentic.app.db.engine import get_session
from agentic.app.db.models import DataRecord
from agentic.app.db.schemas import DataRecordCreate, DataRecordRead, DataRecordUpdate


class RecordNotFoundError(Exception):
    """Raised when a `DataRecord` with the given key does not exist."""


class RecordAlreadyExistsError(Exception):
    """Raised when attempting to create a `DataRecord` whose key already exists."""


def create_record(payload: DataRecordCreate) -> DataRecordRead:
    """Create a new record. Raises `RecordAlreadyExistsError` if `key` exists."""
    with get_session() as session:
        existing = session.query(DataRecord).filter_by(key=payload.key).one_or_none()
        if existing is not None:
            raise RecordAlreadyExistsError(f"Record with key {payload.key!r} already exists")

        record = DataRecord(key=payload.key, value=payload.value)
        session.add(record)
        session.commit()
        session.refresh(record)
        return DataRecordRead.model_validate(record)


def get_record(key: str) -> DataRecordRead:
    """Fetch a record by key. Raises `RecordNotFoundError` if missing."""
    with get_session() as session:
        record = session.query(DataRecord).filter_by(key=key).one_or_none()
        if record is None:
            raise RecordNotFoundError(f"Record with key {key!r} not found")
        return DataRecordRead.model_validate(record)


def update_record(key: str, payload: DataRecordUpdate) -> DataRecordRead:
    """Update an existing record's value. Raises `RecordNotFoundError` if missing."""
    with get_session() as session:
        record = session.query(DataRecord).filter_by(key=key).one_or_none()
        if record is None:
            raise RecordNotFoundError(f"Record with key {key!r} not found")
        record.value = payload.value
        session.commit()
        session.refresh(record)
        return DataRecordRead.model_validate(record)


def delete_record(key: str) -> None:
    """Delete a record by key. Raises `RecordNotFoundError` if missing."""
    with get_session() as session:
        record = session.query(DataRecord).filter_by(key=key).one_or_none()
        if record is None:
            raise RecordNotFoundError(f"Record with key {key!r} not found")
        session.delete(record)
        session.commit()


def list_records(limit: int = 100, offset: int = 0) -> list[DataRecordRead]:
    """List records ordered by most-recently-updated first."""
    with get_session() as session:
        records = (
            session.query(DataRecord)
            .order_by(DataRecord.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [DataRecordRead.model_validate(record) for record in records]


