import base64
import logging
import os
import os.path
from pathlib import Path

from fastmcp.tools import ToolResult, tool
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Directory attachments are saved to when a bare filename (not an absolute
# path) is supplied. Mirrors the `downloads/` convention used elsewhere in
# the repo (see agentic_mcp/pdf_parser/tools.py).
DEFAULT_ATTACHMENT_DIR = os.environ.get("GMAIL_ATTACHMENT_DIR", "downloads")


def get_message_body(payload):
    """Recursively extract text/plain (preferred) or text/html from a Gmail message payload."""
    body_data = None
    mime_type = None

    def walk(part):
        nonlocal body_data, mime_type
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            body_data = part["body"]["data"]
            mime_type = "text/plain"
            return True  # prefer plain text, stop here
        if (
            part.get("mimeType") == "text/html"
            and part.get("body", {}).get("data")
            and body_data is None
        ):
            body_data = part["body"]["data"]
            mime_type = "text/html"
        for sub in part.get("parts", []):
            if walk(sub):
                return True
        return False

    walk(payload)

    if not body_data:
        return "", None

    decoded = base64.urlsafe_b64decode(body_data.encode("ASCII")).decode(
        "utf-8", errors="replace"
    )
    return decoded, mime_type


def get_attachments_metadata(payload):
    """Recursively walk a Gmail message payload and collect attachment metadata.

    Returns a list of dicts with ``filename``, ``attachment_id``,
    ``mime_type``, and ``size`` for every part that represents an
    attachment (i.e. has a filename and an ``attachmentId``).
    """
    attachments = []

    def walk(part):
        filename = part.get("filename")
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        if filename and attachment_id:
            attachments.append(
                {
                    "filename": filename,
                    "attachment_id": attachment_id,
                    "mime_type": part.get("mimeType"),
                    "size": body.get("size"),
                }
            )
        for sub in part.get("parts", []):
            walk(sub)

    walk(payload)
    return attachments


class GMailTool:
    def __init__(self, credentials_path: str):
        self._creds = None
        self._creds_path = credentials_path
        self._token_path = str(Path(credentials_path).with_name('google_creds_token.json'))
        self._init_credentials()

    def _init_credentials(self):
        if os.path.exists(self._token_path):
            self._creds = Credentials.from_authorized_user_file(self._token_path, SCOPES)
        if not self._creds or not self._creds.valid:
            if self._creds and self._creds.expired and self._creds.refresh_token:
                self._creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._creds_path, SCOPES
                )
                self._creds = flow.run_local_server(port=0)
            with open(self._token_path, "w") as token:
                token.write(self._creds.to_json())

    def list_messages(self):
        service = build("gmail", "v1", credentials=self._creds)
        results = service.users().messages().list(userId="me").execute()
        return map(lambda x: x["id"], results.get("messages", []))

    def list_labels(self):
        try:
            service = build("gmail", "v1", credentials=self._creds)
            results = service.users().labels().list(userId="me").execute()
            labels = results.get("labels", [])
            if not labels:
                return "No labels found."
            return [label["name"] for label in labels]
        except HttpError as error:
            return f"An error occurred: {error}"

    def read_message(self, msg_id):
        """Read and print the subject and snippet of a message."""
        try:
            service = build("gmail", "v1", credentials=self._creds)
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
            headers = msg["payload"]["headers"]

            from_ = next(
                (h["value"] for h in headers if h["name"] == "From"), "(No From)"
            )
            subject = next(
                (h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)"
            )
            raw_body, mime_type = get_message_body(msg["payload"])
            snippet = msg.get("snippet", "")
            attachments = get_attachments_metadata(msg["payload"])
            return dict(
                from_=from_,
                subject=subject,
                snippet=snippet,
                body=raw_body,
                attachments=attachments,
            )

        except HttpError as error:
            print(f"An error occurred: {error}")

    def search_messages(self, query):
        """Search for messages matching a Gmail Query."""
        try:
            service = build("gmail", "v1", credentials=self._creds)
            results = service.users().messages().list(userId="me", q=query).execute()
            messages = results.get("messages", [])
            return [msg["id"] for msg in messages]
        except HttpError as error:
            print(f"An error occurred: {error}")
            return []

    def list_attachments(self, msg_id):
        """List attachment metadata (filename, id, mime type, size) for a message."""
        try:
            service = build("gmail", "v1", credentials=self._creds)
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
            return get_attachments_metadata(msg["payload"])
        except HttpError as error:
            logger.error(f"An error occurred listing attachments for '{msg_id}': {error}")
            return []

    def download_attachment(self, msg_id, attachment_id, filename, download_dir=None):
        """Fetch an attachment's data and save it to disk.

        Returns the resolved file path the attachment was written to.
        """
        service = build("gmail", "v1", credentials=self._creds)
        attachment = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=msg_id, id=attachment_id)
            .execute()
        )
        data = attachment.get("data")
        if not data:
            raise ValueError(f"No data returned for attachment '{attachment_id}'")

        file_bytes = base64.urlsafe_b64decode(data.encode("ASCII"))

        target_dir = Path(download_dir or DEFAULT_ATTACHMENT_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)
        if (
            not filename
            or filename in {".", ".."}
            or Path(filename).is_absolute()
            or "/" in filename
            or "\\" in filename
        ):
            raise ValueError(f"Invalid attachment filename '{filename}'")
        file_path = target_dir / filename
        file_path.write_bytes(file_bytes)
        return str(file_path)


def get_gmail_tools(google_credentials_path: str):
    gmail_tool = GMailTool(google_credentials_path)

    @tool
    def search_gmail_messages(gmail_query: str):
        """Search for messages matching a Gmail Query"""
        messages = gmail_tool.search_messages(gmail_query)
        return ToolResult(content=messages)

    @tool
    def get_message_from_message_id(message_id: str):
        """Get message details from a message ID"""
        message_details = gmail_tool.read_message(message_id)
        return ToolResult(content=message_details)

    @tool
    def list_gmail_attachments(message_id: str):
        """List attachments (filename, attachment_id, mime_type, size) on a Gmail message.

        Use ``get_message_from_message_id`` first to find a message ID (or
        pass one from ``search_gmail_messages``), then call this to see what
        attachments are available before downloading one.
        """
        attachments = gmail_tool.list_attachments(message_id)
        return ToolResult(content=attachments)

    @tool
    def download_gmail_attachment(message_id: str, attachment_id: str, filename: str):
        """Download a Gmail attachment to the downloads directory and return its saved path.

        Args:
            message_id: The Gmail message ID the attachment belongs to.
            attachment_id: The attachment ID, as returned by
                ``list_gmail_attachments`` or ``get_message_from_message_id``.
            filename: Name to save the attachment as (relative to the
                downloads directory unless absolute).
        """
        try:
            file_path = gmail_tool.download_attachment(message_id, attachment_id, filename)
            return ToolResult(content={"file_path": file_path})
        except Exception as error:
            logger.error(
                f"Error downloading attachment '{attachment_id}' from message "
                f"'{message_id}': {error}"
            )
            return ToolResult(content={"error": str(error)})

    return [
        search_gmail_messages,
        get_message_from_message_id,
        list_gmail_attachments,
        download_gmail_attachment,
    ]

# (Manual test harness removed; use unit tests instead.)
