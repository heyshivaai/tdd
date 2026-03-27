"""
Document reader: extracts text from PDF files and chunks them for Claude API calls.

Why: PDFs can be large. We chunk to stay within Claude's context window (max_chars=32000
per chunk). Chunks preserve source metadata so signals can be traced back to their document.
"""
import logging
from pathlib import Path
from typing import List

import PyPDF2

logger = logging.getLogger(__name__)

MAX_CHARS = 32000


def extract_text_from_pdf(filepath: str) -> List[dict]:
    """
    Extract text from a PDF and return as a list of chunks.

    Each chunk is a dict with keys: text, source_doc, chunk_index, total_chunks.
    Returns an empty list if the file cannot be read (logs the error).

    Args:
        filepath: Path to the PDF file to extract text from.

    Returns:
        List of chunk dicts, or empty list if file cannot be read.
    """
    path = Path(filepath)
    if not path.exists():
        logger.warning("PDF not found: %s", filepath)
        return []

    try:
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            full_text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            ).strip()
    except Exception as exc:
        logger.error("Failed to read PDF %s: %s", filepath, exc)
        return []

    if not full_text:
        logger.warning("No text extracted from %s", filepath)
        return []

    return chunk_text(full_text, source_doc=path.name)


def chunk_text(text: str, source_doc: str, max_chars: int = MAX_CHARS) -> List[dict]:
    """
    Split text into chunks no larger than max_chars, preserving word boundaries.

    Never breaks a word. If a single word exceeds max_chars, logs a warning but
    includes it in its own chunk (to ensure no data is lost).

    Args:
        text: The text to chunk.
        source_doc: The source document name (for metadata).
        max_chars: Maximum character limit per chunk (default 32000).

    Returns:
        List of dicts: {text, source_doc, chunk_index, total_chunks}.
    """
    words = text.split()
    chunks: List[str] = []
    current_chunk_words: List[str] = []
    current_length = 0

    for word in words:
        word_len = len(word) + 1  # +1 for space
        if current_length + word_len > max_chars and current_chunk_words:
            chunks.append(" ".join(current_chunk_words))
            current_chunk_words = [word]
            current_length = word_len
        else:
            current_chunk_words.append(word)
            current_length += word_len

    if current_chunk_words:
        chunks.append(" ".join(current_chunk_words))

    total = len(chunks)
    return [
        {
            "text": chunk,
            "source_doc": source_doc,
            "chunk_index": i,
            "total_chunks": total,
        }
        for i, chunk in enumerate(chunks)
    ]
