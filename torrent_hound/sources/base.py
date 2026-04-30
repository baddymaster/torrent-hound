"""Shared source-layer contract and utilities.

`Source` is a structural Protocol — functions that take
`(search_string, quiet_mode)` and return a `list[Result]` implicitly match
it without any declaration or subclassing. Keeps the split minimal.
"""

import re as _re
from datetime import datetime, timezone
from typing import Protocol, TypedDict


class Metadata(TypedDict, total=False):
    """Normalised per-row metadata. All fields optional (`total=False`) —
    sources fill what they capture eagerly; lazy fetchers fill the rest.
    The TUI's `v` overlay iterates a fixed key order and dashes anything
    missing.

    Internal keys (prefixed `_`) drive the lazy-fetch worker and are
    never rendered."""
    # Item-level
    name: str
    released: str             # 'YYYY' or 'DD-MM-YYYY'
    season: int
    episode: int
    imdb_code: str            # 'tt0123456'
    imdb_rating: float
    genre: str
    runtime: str              # pre-formatted 'Xh Ym Zs'
    director: str
    cast: str
    summary: str
    # Release-level
    quality: str
    codec: str
    source_type: str
    audio: str
    subtitles: str
    repack: bool
    # Provenance
    uploader: str
    uploaded: str             # pre-formatted 'DD-MM-YYYY'
    files: int
    category: str
    misc: dict
    # Internal — never rendered, used only by the lazy-fetch worker
    _yts_movie_id: int
    _lazy_fetched: bool
    _lazy_fetching: bool


class Result(TypedDict):
    name: str
    link: str
    seeders: int
    leechers: int
    size: str
    ratio: str
    magnet: str
    # `metadata: Metadata` would be ideal here, but Python 3.10 doesn't
    # have `typing.NotRequired` for marking it optional, and TypedDicts
    # without `total=False` would force every Result construction site
    # to set it. Parsers attach `metadata` at runtime; readers use
    # `.get("metadata") or {}`.


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


def _fmt_date(value) -> str | None:
    """Normalise a date to DD-MM-YYYY. Accepts:
      - int (unix timestamp; 0 → None)
      - 'YYYY-MM-DD HH:MM:SS' (with optional timezone suffix like ' GMT')
      - bare 'YYYY-MM-DD'
    Returns None on any parse failure."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%d-%m-%Y")
        except (OSError, ValueError, OverflowError):
            return None
    if not isinstance(value, str):
        return None
    s = value.strip()
    # Strip a trailing timezone abbreviation (TPB sends 'GMT')
    s = _re.sub(r'\s+[A-Z]{2,5}$', '', s)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return None


def _fmt_runtime(seconds) -> str | None:
    """Format integer seconds as 'Xh Ym Zs'. Returns None for None or 0."""
    if not seconds:
        return None
    s = int(seconds)
    return f"{s // 3600}h {(s % 3600) // 60}m {s % 60}s"


_QUALITY_RE   = _re.compile(r'\b(480p|720p|1080p|2160p|4K)\b', _re.IGNORECASE)
_CODEC_RE     = _re.compile(r'\b(x265|x264|h\.?265|h\.?264|HEVC|AVC)\b', _re.IGNORECASE)
_SOURCE_RE    = _re.compile(r'\b(BluRay|BDRip|WEB-?DL|WEBRip|HDTV|DVDRip|REMUX)\b', _re.IGNORECASE)
_REPACK_RE    = _re.compile(r'\b(REPACK|PROPER)\b', _re.IGNORECASE)
_SEASON_EP_RE = _re.compile(r'\bS(\d{1,2})(?:E(\d{1,2}))?\b', _re.IGNORECASE)


def _extract_release_tags(name: str) -> dict:
    """Pull quality/codec/source_type/repack/season/episode from a torrent
    filename. Used by TPB-eager, EZTV-eager, and any future source. All
    fields case-insensitive; returns only the keys we matched."""
    out: dict = {}
    if (m := _QUALITY_RE.search(name)):
        out["quality"] = m.group(1).lower()
    if (m := _CODEC_RE.search(name)):
        out["codec"] = m.group(1).lower().replace(".", "")
    if (m := _SOURCE_RE.search(name)):
        out["source_type"] = m.group(1)
    if _REPACK_RE.search(name):
        out["repack"] = True
    if (m := _SEASON_EP_RE.search(name)):
        out["season"] = int(m.group(1))
        if m.group(2):
            out["episode"] = int(m.group(2))
    return out
