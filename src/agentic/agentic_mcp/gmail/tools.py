import base64
import os.path
from pathlib import Path

from fastmcp.tools import ToolResult, tool
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


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
            return dict(
                from_=from_,
                subject=subject,
                snippet=snippet,
                body=raw_body,
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

    return [search_gmail_messages, get_message_from_message_id]
