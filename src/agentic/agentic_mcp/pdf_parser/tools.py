import io
import logging
import os
from pathlib import Path

import requests
from fastmcp.tools import tool
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# Directory PDFs are read from/downloaded to when a bare filename (not an
# absolute path) is supplied. Mirrors the `downloads/` convention used
# elsewhere in the repo for generated/fetched media.
DEFAULT_PDF_DIR = os.environ.get("PDF_DOWNLOAD_DIR", "downloads")


def _resolve_path(file_path: str) -> Path:
    """Resolve a user-supplied path, falling back to DEFAULT_PDF_DIR for bare filenames."""
    path = Path(file_path)
    if path.is_absolute() or path.exists():
        return path
    return Path(DEFAULT_PDF_DIR) / path


def _read_pdf(source) -> PdfReader:
    return PdfReader(source)


def _is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


def _load_reader(source: str) -> tuple[PdfReader, str]:
    """Load a PdfReader from either a URL or a local file path.

    Returns the reader and a human-readable label identifying where the
    PDF came from, for inclusion in tool responses.
    """
    if _is_url(source):
        response = requests.get(source, timeout=30)
        response.raise_for_status()
        return _read_pdf(io.BytesIO(response.content)), source

    path = _resolve_path(source)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")
    return _read_pdf(str(path)), str(path)


def get_pdf_parser_tools():
    @tool
    def pdf_parser(source: str, max_pages: int | None = None) -> dict:
        """Parse a PDF (local file path or URL) and extract its text content
        and metadata in a single call.

        Use this as the primary/default tool for reading PDFs — e.g. bank
        statements, invoices, or reports — before performing any analysis
        on their contents.

        Args:
            source: Local path to a PDF file (relative to the downloads
                directory unless absolute), or an http(s) URL to download
                and parse on the fly.
            max_pages: Optional cap on the number of pages to read
                (useful for very large PDFs).
        """
        try:
            reader, label = _load_reader(source)
            pages_to_read = reader.pages[:max_pages] if max_pages else reader.pages
            pages_text = [page.extract_text() or "" for page in pages_to_read]
            metadata = reader.metadata or {}

            return {
                "source": label,
                "page_count": len(reader.pages),
                "extracted_pages": len(pages_text),
                "is_encrypted": reader.is_encrypted,
                "metadata": {k.lstrip("/"): v for k, v in dict(metadata).items()},
                "text": "\n\n".join(pages_text),
            }
        except Exception as e:
            logger.error(f"Error parsing PDF '{source}': {e}")
            return {"error": str(e)}

    @tool
    def extract_pdf_text(file_path: str, max_pages: int | None = None) -> dict:
        """Extract the text content of a local PDF file.

        Args:
            file_path: Path to the PDF file, relative to the downloads
                directory unless absolute.
            max_pages: Optional cap on the number of pages to read
                (useful for very large PDFs).
        """
        try:
            path = _resolve_path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"PDF file not found: {path}")

            reader = _read_pdf(str(path))
            pages_to_read = reader.pages[:max_pages] if max_pages else reader.pages

            pages_text = [page.extract_text() or "" for page in pages_to_read]
            return {
                "file_path": str(path),
                "page_count": len(reader.pages),
                "extracted_pages": len(pages_text),
                "text": "\n\n".join(pages_text),
            }
        except Exception as e:
            logger.error(f"Error extracting text from PDF '{file_path}': {e}")
            return {"error": str(e)}

    @tool
    def extract_pdf_metadata(file_path: str) -> dict:
        """Extract metadata (title, author, page count, etc.) from a local PDF file."""
        try:
            path = _resolve_path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"PDF file not found: {path}")

            reader = _read_pdf(str(path))
            metadata = reader.metadata or {}
            return {
                "file_path": str(path),
                "page_count": len(reader.pages),
                "is_encrypted": reader.is_encrypted,
                "metadata": {k.lstrip("/"): v for k, v in dict(metadata).items()},
            }
        except Exception as e:
            logger.error(f"Error extracting metadata from PDF '{file_path}': {e}")
            return {"error": str(e)}

    @tool
    def extract_pdf_text_from_url(url: str, max_pages: int | None = None) -> dict:
        """Download a PDF from a URL and extract its text content without saving it permanently."""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            reader = _read_pdf(io.BytesIO(response.content))
            pages_to_read = reader.pages[:max_pages] if max_pages else reader.pages
            pages_text = [page.extract_text() or "" for page in pages_to_read]

            return {
                "url": url,
                "page_count": len(reader.pages),
                "extracted_pages": len(pages_text),
                "text": "\n\n".join(pages_text),
            }
        except Exception as e:
            logger.error(f"Error extracting text from PDF URL '{url}': {e}")
            return {"error": str(e)}

    return [pdf_parser, extract_pdf_text, extract_pdf_metadata, extract_pdf_text_from_url]


