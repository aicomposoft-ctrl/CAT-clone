"""
Text sanitization utilities for scraped content.

Rules:
  - Strip all HTML tags
  - Unescape HTML entities (&amp; → &, etc.)
  - Collapse whitespace
  - Truncate to max_len
"""

from __future__ import annotations

import html
import re

_HTML_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)  # re.DOTALL covers multiline tags
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize(text: str | None, max_len: int) -> str:
    """
    Clean scraped text for storage.

    1. Return empty string for None/empty input.
    2. Unescape HTML entities.
    3. Strip HTML tags.
    4. Collapse whitespace.
    5. Truncate to max_len.
    """
    if not text:
        return ""
    text = html.unescape(text)
    text = _HTML_TAG_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text[:max_len] if len(text) > max_len else text
