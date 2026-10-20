"""A small reader for Valve's KeyValues text format (libraryfolders.vdf, *.acf)."""

from __future__ import annotations

import re

_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|//[^\n]*')


def parse(text: str) -> dict:
    stack: list[dict] = [{}]
    key: str | None = None
    for match in _TOKEN.finditer(text):
        string, brace = match.group(1), match.group(2)
        if string is None and brace is None:
            continue  # comment
        if brace == "{":
            child: dict = {}
            stack[-1][key or ""] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif key is None:
            key = string.replace("\\\\", "\\")
        else:
            stack[-1][key] = string.replace("\\\\", "\\")
            key = None
    return stack[0]
