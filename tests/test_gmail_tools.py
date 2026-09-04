"""Unit tests for agentic.agentic_mcp.gmail.tools helpers.

These target the pure payload-parsing helpers (``get_message_body`` and
``get_attachments_metadata``) in isolation, since ``GMailTool`` itself
requires Google OAuth credentials and network access to construct.
"""

from agentic.agentic_mcp.gmail.tools import (
    get_attachments_metadata,
    get_message_body,
)


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

