"""Unit tests for gmail tool helpers.

These target the pure payload-parsing helpers (``get_message_body`` and
``get_attachments_metadata``) in isolation, since ``GMailTool`` itself
requires Google OAuth credentials and network access to construct.
"""

import base64
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _load_gmail_tools_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "agentic"
        / "agentic_mcp"
        / "gmail"
        / "tools.py"
    )
    spec = importlib.util.spec_from_file_location("gmail_tools_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gmail_tools = _load_gmail_tools_module()
GMailTool = gmail_tools.GMailTool
get_attachments_metadata = gmail_tools.get_attachments_metadata
get_message_body = gmail_tools.get_message_body


def test_get_attachments_metadata_returns_empty_list_when_no_attachments():
    payload = {
        "mimeType": "text/plain",
        "body": {"data": "aGVsbG8"},
    }
    assert get_attachments_metadata(payload) == []


def test_get_attachments_metadata_finds_top_level_attachment():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": "aGVsbG8"}},
            {
                "filename": "invoice.pdf",
                "mimeType": "application/pdf",
                "body": {"attachmentId": "abc123", "size": 4096},
            },
        ],
    }
    attachments = get_attachments_metadata(payload)
    assert attachments == [
        {
            "filename": "invoice.pdf",
            "attachment_id": "abc123",
            "mime_type": "application/pdf",
            "size": 4096,
        }
    ]


def test_get_attachments_metadata_finds_nested_attachments():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/related",
                "parts": [
                    {
                        "filename": "photo.png",
                        "mimeType": "image/png",
                        "body": {"attachmentId": "img1", "size": 1024},
                    }
                ],
            },
            {
                "filename": "report.csv",
                "mimeType": "text/csv",
                "body": {"attachmentId": "csv1", "size": 512},
            },
        ],
    }
    attachments = get_attachments_metadata(payload)
    filenames = {a["filename"] for a in attachments}
    assert filenames == {"photo.png", "report.csv"}


def test_get_attachments_metadata_ignores_parts_without_filename_or_id():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": "aGVsbG8"}},
            {"filename": "", "body": {"attachmentId": "no-name"}},
            {"filename": "inline.png", "body": {}},
        ],
    }
    assert get_attachments_metadata(payload) == []


def test_get_message_body_prefers_plain_text():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": "PGI-aGk8L2I-"}},
            {"mimeType": "text/plain", "body": {"data": "aGVsbG8="}},
        ],
    }
    text, mime_type = get_message_body(payload)
    assert text == "hello"
    assert mime_type == "text/plain"


def test_download_attachment_rejects_path_traversal(monkeypatch, tmp_path):
    attachment_resource = MagicMock()
    attachment_resource.get.return_value.execute.return_value = {
        "data": base64.urlsafe_b64encode(b"hello").decode("ascii")
    }
    messages_resource = MagicMock()
    messages_resource.attachments.return_value = attachment_resource
    users_resource = MagicMock()
    users_resource.messages.return_value = messages_resource
    service = MagicMock()
    service.users.return_value = users_resource
    monkeypatch.setattr(gmail_tools, "build", lambda *args, **kwargs: service)

    gmail_tool = object.__new__(GMailTool)
    gmail_tool._creds = object()

    with pytest.raises(ValueError, match="Invalid attachment filename"):
        gmail_tool.download_attachment("message", "attachment", "../escape.txt", tmp_path)
