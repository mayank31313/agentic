"""MCP tools exposing CRUD operations over Agentic's SQLite data store.

Thin wrappers around `agentic.app.db.repository` — persistence logic
itself lives there, keeping this module focused on tool
naming/docstrings/error-shaping for the agent-facing surface. Inputs are
validated via `agentic.app.db.schemas` before hitting the repository, so
malformed tool calls (e.g. an empty key) surface as a clean `{"error":
...}` rather than a raw traceback.
"""

import logging

from fastmcp.tools import tool
from pydantic import ValidationError

from agentic.app.db import repository
from agentic.app.db.repository import RecordAlreadyExistsError, RecordNotFoundError
from agentic.app.db.schemas import DataRecordCreate, DataRecordUpdate

logger = logging.getLogger(__name__)


def get_sqlite_store_tools():
    @tool
    def sqlite_create_record(key: str, value: str) -> dict:
        """Create a new key/value record in the SQLite data store.

        Fails if a record with the given key already exists — use
        `sqlite_update_record` to modify an existing one.
        """
        try:
            payload = DataRecordCreate(key=key, value=value)
            return repository.create_record(payload).model_dump(mode="json")
        except ValidationError as e:
            return {"error": str(e)}
        except RecordAlreadyExistsError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Error creating record {key!r}: {e}")
            return {"error": str(e)}

    @tool
    def sqlite_get_record(key: str) -> dict:
        """Fetch a record from the SQLite data store by its key."""
        try:
            return repository.get_record(key).model_dump(mode="json")
        except RecordNotFoundError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Error fetching record {key!r}: {e}")
            return {"error": str(e)}

    @tool
    def sqlite_update_record(key: str, value: str) -> dict:
        """Update the value of an existing record in the SQLite data store."""
        try:
            payload = DataRecordUpdate(value=value)
            return repository.update_record(key, payload).model_dump(mode="json")
        except ValidationError as e:
            return {"error": str(e)}
        except RecordNotFoundError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Error updating record {key!r}: {e}")
            return {"error": str(e)}

    @tool
    def sqlite_delete_record(key: str) -> dict:
        """Delete a record from the SQLite data store by its key."""
        try:
            repository.delete_record(key)
            return {"deleted": key}
        except RecordNotFoundError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Error deleting record {key!r}: {e}")
            return {"error": str(e)}

    @tool
    def sqlite_list_records(limit: int = 100, offset: int = 0) -> list[dict]:
        """List records in the SQLite data store, most-recently-updated first."""
        try:
            records = repository.list_records(limit=limit, offset=offset)
            return [record.model_dump(mode="json") for record in records]
        except Exception as e:
            logger.error(f"Error listing records: {e}")
            return [{"error": str(e)}]

    return [
        sqlite_create_record,
        sqlite_get_record,
        sqlite_update_record,
        sqlite_delete_record,
        sqlite_list_records,
    ]



