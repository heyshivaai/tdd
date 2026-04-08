"""
JSON extraction utilities for parsing Claude API responses.

Why: Claude's responses sometimes wrap JSON in markdown code fences,
explanatory text, or trailing comments. This module robustly extracts
the JSON object regardless of wrapping.
"""
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def extract_json(raw: str) -> Optional[dict]:
    """
    Extract and parse a JSON object from a string that may contain
    surrounding text, markdown fences, or other non-JSON content.

    Tries multiple strategies in order:
      1. Direct parse (raw string is valid JSON)
      2. Extract from markdown code fence (```json ... ```)
      3. Find first { ... } block via brace matching
      4. Find first [ ... ] block via bracket matching

    Args:
        raw: Raw string that may contain a JSON object.

    Returns:
        Parsed dict/list, or None if no valid JSON found.
    """
    if not raw or not raw.strip():
        return None

    text = raw.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: extract from markdown code fence
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3: find first { ... } block via brace matching
    result = _extract_braced(text, "{", "}")
    if result is not None:
        return result

    # Strategy 4: find first [ ... ] block via bracket matching
    result = _extract_braced(text, "[", "]")
    if result is not None:
        return result

    logger.warning("Could not extract JSON from response (%d chars)", len(text))
    return None


def _extract_braced(text: str, open_char: str, close_char: str) -> Optional[dict]:
    """
    Find the first balanced brace/bracket block in text and parse it as JSON.

    Args:
        text: Input text to search.
        open_char: Opening delimiter ('{' or '[').
        close_char: Closing delimiter ('}' or ']').

    Returns:
        Parsed JSON object, or None if not found or invalid.
    """
    start = text.find(open_char)
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == "\\":
            escape_next = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except (json.JSONDecodeError, ValueError):
                    return None

    return None
