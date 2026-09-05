"""Pydantic schemas for the `DataRecord` SQLAlchemy table.

Separates the wire/validation layer (used by the repository and the
`sqlite_store` MCP tools) from the ORM layer in `models.py` — request
payloads are validated here before ever touching the database, and reads
are serialized here rather than via ad-hoc dict-building.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DataRecordBase(BaseModel):
    """Fields shared by create/read payloads."""

    key: str = Field(
        ..., min_length=1, max_length=255, description="Unique key identifying the record"
    )
    value: str = Field(..., description="Arbitrary string value stored for this key")


class DataRecordCreate(DataRecordBase):
    """Payload for creating a new record."""


class DataRecordUpdate(BaseModel):
    """Payload for updating an existing record's value."""

    value: str = Field(..., description="New value to store for the existing key")


class DataRecordRead(DataRecordBase):
    """Serialized representation of a persisted `DataRecord` row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

