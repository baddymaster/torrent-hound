"""Shared source-layer contract and utilities.

`Source` is a structural Protocol — functions that take
`(search_string, quiet_mode)` and return a `list[Result]` implicitly match
it without any declaration or subclassing. Keeps the split minimal.
"""
from __future__ import annotations

from typing import Protocol, TypedDict


class Result(TypedDict):
    name: str
    link: str
    seeders: int
    leechers: int
    size: str
    ratio: str
    magnet: str


class Source(Protocol):
    """A torrent source. Implementations are plain functions registered in
    `sources/__init__.py`'s `_SOURCES` list as (display_name, search_fn).

    `quiet_mode` suppresses user-facing error prints for --quiet / --json runs.
    Returns [] on failure / no results; never raises.
    """
    def __call__(
        self, search_string: str, quiet_mode: bool = False
    ) -> list[Result]: ...


def removeAndReplaceSpaces(string: str) -> str:
    if string[0] == " ":
        string = string[1:]
    return string.replace(" ", "+")


def _format_bytes(n) -> str:
    """Human-readable size from a byte count."""
    n = float(n)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
