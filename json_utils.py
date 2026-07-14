"""
json_utils.py
--------------
Two responsibilities:

1. `sanitize_json_output` — a defensive post-processing pass that guarantees
   the JSON shown to the user and written to the download file is always
   perfectly clean: every dict key and every string value has stray
   leading/trailing whitespace stripped, regardless of what the LLM or any
   upstream step produced. This runs on EVERY payload right before it's
   rendered or downloaded — nothing reaches the screen unsanitized.

2. `json_to_highlighted_html` — a lightweight, dependency-free JSON syntax
   highlighter that wraps tokens (keys, strings, numbers, booleans, null) in
   `<span>` tags with CSS classes, powering the neon "code editor" look of
   the output panel without needing a JS highlighting library.
"""
from __future__ import annotations

import html
import json
import re
from typing import Any


def sanitize_json_output(data: Any) -> Any:
    """
    Recursively strip whitespace from every dict key and string value in a
    JSON-like structure (dict / list / str / number / bool / None).

    This is the single choke point every payload passes through before it's
    displayed or downloaded, so malformed spacing like `" sender "` can
    never reach the user, no matter where it originated upstream.
    """
    if isinstance(data, dict):
        return {
            (key.strip() if isinstance(key, str) else key): sanitize_json_output(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [sanitize_json_output(item) for item in data]
    if isinstance(data, str):
        return data.strip()
    return data


def to_clean_json_string(data: Any, indent: int = 2) -> str:
    """
    Sanitize `data` and serialize it as a strictly-formatted JSON string:
    `"key": value` with a single space after the colon and none before it,
    and no padding inside keys or string values.
    """
    clean = sanitize_json_output(data)
    return json.dumps(clean, indent=indent, ensure_ascii=False, separators=(",", ": "), default=str)


# Matches, in priority order: a quoted key (a quoted string immediately
# followed by a colon), any other quoted string (i.e. a value), true/false,
# null, or a number. Used to tokenize a JSON string for highlighting.
_TOKEN_PATTERN = re.compile(
    r'(?P<key>"(?:\\.|[^"\\])*")(?=\s*:)'
    r'|(?P<string>"(?:\\.|[^"\\])*")'
    r'|(?P<bool>\btrue\b|\bfalse\b)'
    r'|(?P<null>\bnull\b)'
    r'|(?P<number>-?\d+\.?\d*(?:[eE][+-]?\d+)?)'
)


def json_to_highlighted_html(json_string: str) -> str:
    """
    Convert an already-clean JSON string into HTML with neon-colored
    `<span>` tags around each token type. Structural characters (braces,
    brackets, commas, colons, whitespace/indentation) pass through
    untouched so the original formatting is preserved exactly.
    """
    pieces: list[str] = []
    last_end = 0

    for match in _TOKEN_PATTERN.finditer(json_string):
        start, end = match.span()
        pieces.append(html.escape(json_string[last_end:start]))

        token = match.group()
        css_class = match.lastgroup  # "key" | "string" | "bool" | "null" | "number"
        pieces.append(f'<span class="tok-{css_class}">{html.escape(token)}</span>')
        last_end = end

    pieces.append(html.escape(json_string[last_end:]))
    return "".join(pieces)
