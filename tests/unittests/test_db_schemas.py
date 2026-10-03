"""Tests for `agentic.app.db.schemas` Pydantic models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agentic.app.db.models import DataRecord
from agentic.app.db.schemas import DataRecordCreate, DataRecordRead, DataRecordUpdate


def test_data_record_create_accepts_valid_payload():
    payload = DataRecordCreate(key="greeting", value="hello")
    assert payload.key == "greeting"
    assert payload.value == "hello"


def test_data_record_create_rejects_empty_key():
    with pytest.raises(ValidationError):
        DataRecordCreate(key="", value="hello")


def test_data_record_create_rejects_missing_value():
    with pytest.raises(ValidationError):
        DataRecordCreate(key="greeting")


def test_data_record_create_rejects_overlong_key():
    with pytest.raises(ValidationError):
        DataRecordCreate(key="x" * 256, value="hello")


def test_data_record_update_requires_value():
    with pytest.raises(ValidationError):
        DataRecordUpdate()

    payload = DataRecordUpdate(value="new value")
    assert payload.value == "new value"


def test_data_record_read_from_orm_attributes():
    now = datetime.now(timezone.utc)
    orm_record = DataRecord(id=1, key="greeting", value="hello", created_at=now, updated_at=now)

    read_model = DataRecordRead.model_validate(orm_record)

    assert read_model.id == 1
    assert read_model.key == "greeting"
    assert read_model.value == "hello"
    assert read_model.created_at == now
    assert read_model.updated_at == now


def test_data_record_read_serializes_to_json_compatible_dict():
    now = datetime.now(timezone.utc)
    read_model = DataRecordRead(id=1, key="greeting", value="hello", created_at=now, updated_at=now)

    dumped = read_model.model_dump(mode="json")

    assert dumped["key"] == "greeting"
    assert isinstance(dumped["created_at"], str)

