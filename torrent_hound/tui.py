"""Terminal UI for torrent-hound's interactive mode.

Single-screen rich.live app. Replaces the old REPL `Enter command :` loop
with arrow-key navigation, mode-aware footer, live filtering, and inline
Real-Debrid integration.

Architecture overview
---------------------
* `_AppState` is the single source of truth for what's on screen. Render
  functions are pure: state in, renderable out. Key handlers mutate state.
* `cbreak()` puts stdin in non-canonical mode; `read_key()` reads via
  `os.read()` (bypassing Python's TextIOWrapper buffering — see the
  function's docstring) and decodes ESC sequences to symbolic names.
* `handle_key` dispatches to per-mode handlers (`_handle_filter_key`,
  `_handle_search_key`, `_handle_chord` for RESULTS).
* Vim-style chord buffer (`c`/`r` are prefixes for `cs`/`rd`) — the
  pending prefix is surfaced in the footer so the timeout window feels
  like a menu rather than a freeze.
* `searchAllSites` runs in a worker thread (`_kick_off_fetch`); per-source
  progress events flow through a callback into `_SourceStatus` instances.
* The persistent `_AppState._verb_spinner` instance is critical — see
  the field's comment for why we can't recreate it per render.
"""

import os
import random
import re
import select
import sys
import termios
import threading
import time
import tty
import webbrowser
from contextlib import contextmanager
from dataclasses import dataclass, field

import pyperclip
from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from torrent_hound import state as _state
from torrent_hound.realdebrid import _cmd_rd
from torrent_hound.sources import searchAllSites
from torrent_hound.ui import console as _console

# ── modes ──────────────────────────────────────────────────────────────
LOADING = "loading"
RESULTS = "results"
FILTER = "filter"
SEARCH = "search"      # new-query prompt
MAGNET_VIEW = "magnet_view"  # full magnet displayed in the body, any key returns
RD_PICKER = "rd_picker"
RD_WAITING = "rd_waiting"
HELP = "help"


# N3 — palette. One place to tune the entire look. Inline color strings
# elsewhere should reference these rather than redefining them.
PALETTE = {
    "accent":   "bold #ffb84d",   # selected row, primary action
    "headline": "bold",           # headline / column headers
    "metadata": "dim",            # secondary info, separators
    "ok":       "green",          # success markers (toast, source ✓)
    "warn":     "yellow",         # cache hit, partial state
    "err":      "red",            # failed source, hard error
    "blink":    "bold #ffb84d blink",
}

# Per-source accent colours used by the selected-row header line. Picked to
# be visibly distant from the amber selection accent so the eye doesn't
# conflate "selected source name" with "selected row".
SOURCE_COLOURS = {
    "TPB":   "deep_sky_blue1",
    "YTS":   "spring_green2",
    "EZTV":  "medium_purple1",
    "1337x": "hot_pink2",
}

# N1 — toasts. Auto-dismiss after this many seconds.
TOAST_TTL_SECONDS = 3.0

# Multi-char (chord) commands. After a CHORD_PREFIX key is pressed, the
# dispatcher waits CHORD_TIMEOUT_SECONDS for an extension. If a complete
# COMPLETE_CHORDS entry is matched (e.g. "rd"), it dispatches the chord;
# otherwise the prefix dispatches alone (e.g. "r" → repeat search).
CHORD_TIMEOUT_SECONDS = 1
CHORD_PREFIXES = {"c", "r"}
COMPLETE_CHORDS = {"c", "cs", "r", "rd"}


# Rotating-verb pool, search-phase only. Torrent-themed by design — every
# phrase maps to something a multi-source torrent search might be doing.
# RD-phase verbs land in step 8.
SEARCH_VERBS = [
    "Sniffing the trackers", "Catching a whiff of seeders", "Scenting magnets",
    "Picking up tracks", "Nosing the swarm", "Following the announce trail",
    "Combing the DHT", "Pawing through mirrors", "Canvassing seeders",
    "Scenting fresh torrents", "Nosing for peers", "Sniffing bencode",
    "Hunting seeders", "Stalking peers", "Prowling for trackers",
    "Chasing hashes", "Baying at trackers", "Treeing the torrent",
    "Hot on the scrape", "Cornering the swarm", "Running down leechers",
    "Closing on the infohash", "Dogging the announce",
    "Fetching magnets", "Hauling bitfields", "Dragging home the .torrent",
    "Bringing back the payload", "Scooping up seeders", "Wrangling peers",
    "Carting off chunks", "Lugging the swarm home", "Reeling in hashes",
    "Sieving peers", "Peeling packets", "Decoding magnets",
    "Unweaving trackers", "Stitching chunks", "Parsing the bitfield",
    "Shaking the DHT", "Rattling trackers", "Waking the swarm",
    "Herding peers", "Polling announces", "Unchoking peers",
    "Walking the DHT", "Hashing chunks", "Reticulating pieces",
    "Verifying infohash", "Handshaking", "Fanning out", "Merging swarms",
    "Scraping trackers", "Announcing to swarm", "Resolving peers",
    "Parsing bencode", "Tallying seeders", "Sieving leechers",
]
VERB_ROTATE_SECONDS = 1


@dataclass
class _SourceStatus:
    """Per-source state that drives the trail line. Populated by callback
    events from `searchAllSites`."""
    name: str
    in_flight: bool = True
    current_mirror: str = ""
    failed_mirrors_count: int = 0
    final_state: str | None = None  # "ok" | "cached" | "failed" | "empty"
    result_count: int = 0
    elapsed_ms: int = 0
    cache_age: str = ""

    def apply(self, event: dict) -> None:
        et = event.get("type")
        if et == "start":
            self.in_flight = True
        elif et == "mirror_attempt":
            self.in_flight = True
            self.current_mirror = event.get("mirror", "")
        elif et == "mirror_failed":
            self.failed_mirrors_count += 1
        elif et == "ok":
            self.in_flight = False
            self.final_state = "ok"
            self.result_count = event.get("count", 0)
            self.elapsed_ms = event.get("elapsed_ms", 0)
            if event.get("mirror"):
                self.current_mirror = event["mirror"]
        elif et == "cached":
            self.in_flight = False
            self.final_state = "cached"
            self.result_count = event.get("count", 0)
            self.cache_age = event.get("age", "")
        elif et == "failed":
            self.in_flight = False
            self.final_state = "failed"
            self.elapsed_ms = event.get("elapsed_ms", 0)
        elif et == "empty":
            self.in_flight = False
            self.final_state = "empty"
            self.elapsed_ms = event.get("elapsed_ms", 0)


@dataclass
class _AppState:
    """All TUI state in one place. Render is a pure function of this."""
    mode: str = LOADING
    selected_idx: int = 0
    filter_text: str = ""
    toast: str | None = None
    # Per-source rich status: {source_name: _SourceStatus}. Insertion order
    # determines display order in the trail line.
    source_status: dict = field(default_factory=dict)
    # Rotating verb shown during LOADING. Swap every ~VERB_ROTATE_SECONDS.
    current_verb: str = "Sniffing the trackers"
    verb_set_at: float = 0.0
    # Fetch timing for the run-summary line (M5).
    fetch_started_at: float = 0.0
    fetch_elapsed: float = 0.0
    # Set when the user requests RD on a row; main loop suspends Live and
    # runs _cmd_rd then clears this. None at rest.
    rd_request_entry: dict | None = None
    # Wall-clock when toast was set; loop expires after TOAST_TTL_SECONDS.
    toast_set_at: float = 0.0
    # SEARCH mode buffer (typed new-query string) and the refetch trigger.
    search_text: str = ""
    refetch_request: bool = False
    # First visible row in the results table. Scrolling only happens when the
    # selection goes off the visible window — like ls/less, not centered.
    view_top: int = 0
    # Chord-prefix buffer (vim-style). When set, the next key extends or
    # disambiguates: e.g. `c` → wait → `s` extends to `cs` (seedr); `c` alone
    # times out to `c` (copy). See CHORD_TIMEOUT_SECONDS / CHORD_PREFIXES.
    chord_buffer: str = ""
    chord_started_at: float = 0.0
    # Persistent Spinner instance for the loading-phase verb. Recreating the
    # Spinner on each render would reset its internal frame counter to zero,
    # freezing the animation. We update its `text` attribute instead.
    _verb_spinner: Spinner | None = field(default=None, init=False, repr=False, compare=False)
    # MAGNET_VIEW: the full magnet of the row that triggered `m` is stashed
    # here so the body renderer can show it as an overlay panel.
    magnet_view_text: str = ""
    magnet_view_name: str = ""


def _set_toast(state: _AppState, message: str) -> None:
    state.toast = message
    state.toast_set_at = time.monotonic()


def _expire_toast(state: _AppState) -> None:
    if state.toast and (time.monotonic() - state.toast_set_at) >= TOAST_TTL_SECONDS:
        state.toast = None


# ── input ──────────────────────────────────────────────────────────────
@contextmanager
def cbreak():
    """Put stdin into cbreak mode so we can read single keys without Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# How long to wait after a bare ESC byte before deciding it's really a bare
# ESC vs the start of an escape sequence. Vim defaults to 25ms (ttimeoutlen);
# we use 50ms so terminals that emit `\x1b[A` with even a tiny gap don't get
# their arrow keys swallowed.
_ESC_PROBE_SECONDS = 0.05


def read_key() -> str:
    """Read one keypress (or escape sequence) from stdin in cbreak mode.

    Reads directly via os.read() against the FD, bypassing Python's
    TextIOWrapper buffering. The wrapper greedily pulls all available bytes
    into its own buffer on a read(1) call — that strands the rest of an
    escape sequence (e.g. the `[A` after `\\x1b`) in Python's buffer where
    select.select() can't see it, making `read_key()` falsely return "ESC"
    on every arrow press.

    A bare ESC press sends only `\\x1b`; arrow keys send `\\x1b[A`/B/C/D.
    Strategy: read first byte; if ESC, probe FD for more; if more, drain
    the rest of the burst in one os.read.
    """
    fd = sys.stdin.fileno()
    first = os.read(fd, 1).decode("utf-8", errors="replace")
    if first != "\x1b":
        return first
    if not select.select([fd], [], [], _ESC_PROBE_SECONDS)[0]:
        return "ESC"
    rest = os.read(fd, 32).decode("utf-8", errors="replace")
    return {
        "[A": "UP", "[B": "DOWN", "[C": "RIGHT", "[D": "LEFT",
        "[H": "HOME", "[F": "END",
    }.get(rest, "ESC")


# ── action handlers ────────────────────────────────────────────────────
# Each returns the toast message to surface; rendering is the loop's job.
def _action_copy(entry) -> str:
    pyperclip.copy(str(entry["magnet"]))
    return "Magnet copied to clipboard"


def _action_open_page(entry) -> str:
    webbrowser.open(entry["link"], new=2)
    return "Opened torrent page in browser"


def _action_send_to_client(entry) -> str:
    webbrowser.open(entry["magnet"], new=2)
    return "Magnet sent to default torrent client"


def _action_seedr(entry) -> str:
    pyperclip.copy(str(entry["magnet"]))
    webbrowser.open("https://www.seedr.cc", new=2)
    return "Magnet copied + Seedr opened"


# Entry-targeted commands (act on the highlighted row). Includes both single-
# char and multi-char (chord) commands. Chord prefixes are listed for the
# dispatcher; CHORD_PREFIXES + COMPLETE_CHORDS up top govern timing.
_ENTRY_ACTIONS = {
    "c":  _action_copy,
    "\r": _action_copy,
    "\n": _action_copy,
    "cs": _action_seedr,
    "o":  _action_open_page,
    "d":  _action_send_to_client,
}


# ── helpers ────────────────────────────────────────────────────────────
def _all_results() -> list[dict]:
    return _state.results or []


def _visible_results(state: _AppState) -> list[dict]:
    """Filter `_state.results` by `state.filter_text` (substring, case-insensitive)."""
    rows = _all_results()
    if not state.filter_text:
        return rows
    needle = state.filter_text.lower()
    return [r for r in rows if needle in r.get("name", "").lower()]


def _selected_entry(state: _AppState) -> dict | None:
    rows = _visible_results(state)
    if not rows:
        return None
    return rows[state.selected_idx]


def _handle_filter_key(state: _AppState, key: str) -> bool:
    """Filter-mode input: build state.filter_text; esc cancels, enter accepts.

    Arrow keys navigate the *currently filtered* results without leaving filter
    mode — selected_idx is NOT reset on UP/DOWN (only when the filter itself
    changes). This lets the user type to narrow, then arrow to pick.
    """
    if key == "ESC":
        state.filter_text = ""
        state.mode = RESULTS
        state.selected_idx = 0
        state.view_top = 0
    elif key in ("\r", "\n"):
        state.mode = RESULTS
        state.selected_idx = 0
        state.view_top = 0
    elif key == "UP":
        state.selected_idx = max(0, state.selected_idx - 1)
        _scroll_into_view(state)
    elif key == "DOWN":
        rows = _visible_results(state)
        state.selected_idx = min(max(0, len(rows) - 1), state.selected_idx + 1)
        _scroll_into_view(state)
    elif key == "\x7f":  # backspace
        state.filter_text = state.filter_text[:-1]
        state.selected_idx = 0
        state.view_top = 0
    elif len(key) == 1 and key.isprintable():
        state.filter_text += key
        state.selected_idx = 0
        state.view_top = 0
    return True


def _handle_search_key(state: _AppState, key: str) -> bool:
    """Search-mode input: build state.search_text; enter submits, esc cancels."""
    if key == "ESC":
        state.search_text = ""
        state.mode = RESULTS
    elif key in ("\r", "\n"):
        new_query = state.search_text.strip()
        if new_query:
            _state.query = new_query
            # Reset for fresh fetch
            state.filter_text = ""
            state.selected_idx = 0
            state.view_top = 0
            state.search_text = ""
            state.refetch_request = True
            state.mode = LOADING
        else:
            state.mode = RESULTS
    elif key == "\x7f":  # backspace
        state.search_text = state.search_text[:-1]
    elif len(key) == 1 and key.isprintable():
        state.search_text += key
    return True


def _dispatch_command(state: _AppState, cmd: str) -> bool:
    """Run one fully-resolved command (single-key or chord). Returns False to quit."""
    if cmd == "q":
        return False

    rows = _visible_results(state)
    if cmd == "UP":
        state.selected_idx = max(0, state.selected_idx - 1)
        _scroll_into_view(state)
    elif cmd == "DOWN":
        state.selected_idx = min(max(0, len(rows) - 1), state.selected_idx + 1)
        _scroll_into_view(state)
    elif cmd == "/":
        state.mode = FILTER
        state.filter_text = ""
        state.selected_idx = 0
    elif cmd == "s":
        state.mode = SEARCH
        state.search_text = ""
    elif cmd == "r":
        # Repeat the current search (refetch; failed sources retry).
        # source_status is reset by _kick_off_fetch on the next loop iteration.
        state.refetch_request = True
        state.mode = LOADING
    elif cmd == "rd":
        entry = _selected_entry(state)
        if entry is not None:
            # Main loop picks this up, suspends Live, runs _cmd_rd, restarts.
            state.rd_request_entry = entry
    elif cmd == "m":
        entry = _selected_entry(state)
        if entry is not None:
            state.magnet_view_text = entry.get("magnet", "")
            state.magnet_view_name = entry.get("name", "")
            state.mode = MAGNET_VIEW
    elif cmd == "?":
        state.mode = HELP
    elif cmd in _ENTRY_ACTIONS:
        entry = _selected_entry(state)
        if entry is not None:
            _set_toast(state, _ENTRY_ACTIONS[cmd](entry))
    return True


def _flush_chord(state: _AppState) -> bool:
    """Dispatch any pending chord prefix as a single-char command. Used both
    on timeout (from the main loop) and when a non-extending key arrives."""
    cmd = state.chord_buffer
    state.chord_buffer = ""
    if cmd:
        return _dispatch_command(state, cmd)
    return True


def _handle_chord(state: _AppState, key: str) -> bool:
    """Buffer chord prefixes; dispatch on completion, non-extending key, or ESC.

    Vim-style: pressing `c` enters a 250ms chord window. If `s` arrives, the
    `cs` chord fires. Any other key dispatches `c` alone first then processes
    the new key. ESC silently clears the buffer.
    """
    # ESC always cancels a pending chord without dispatching it.
    if state.chord_buffer and key == "ESC":
        state.chord_buffer = ""
        return True

    if state.chord_buffer:
        combined = state.chord_buffer + key
        if combined in COMPLETE_CHORDS:
            state.chord_buffer = ""
            return _dispatch_command(state, combined)
        # Extension didn't match — flush buffer first, then process key fresh.
        if not _flush_chord(state):
            return False
        # Fall through to handle `key` as a fresh input.

    if key in CHORD_PREFIXES:
        state.chord_buffer = key
        state.chord_started_at = time.monotonic()
        return True

    return _dispatch_command(state, key)


def _handle_magnet_view_key(state: _AppState, key: str) -> bool:
    """Magnet-view overlay: any key returns to RESULTS; q quits."""
    if key == "q":
        return False
    state.mode = RESULTS
    return True


def _handle_help_key(state: _AppState, key: str) -> bool:
    """Help overlay: any key returns to RESULTS; q quits."""
    if key == "q":
        return False
    state.mode = RESULTS
    return True


def handle_key(state: _AppState, key: str) -> bool:
    """Mutates state in-place. Returns False to break the event loop."""
    if state.mode == FILTER:
        return _handle_filter_key(state, key)
    if state.mode == SEARCH:
        return _handle_search_key(state, key)
    if state.mode == MAGNET_VIEW:
        return _handle_magnet_view_key(state, key)
    if state.mode == HELP:
        return _handle_help_key(state, key)
    if state.mode == RESULTS:
        return _handle_chord(state, key)
    # Other modes ignore keys for now (LOADING / RD_PICKER / RD_WAITING).
    if key == "q":
        return False
    return True


# ── render ─────────────────────────────────────────────────────────────
def _build_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="toast", size=1),
        Layout(name="footer", size=1),
    )
    return layout


def render_trail(state: _AppState) -> Text:
    """Single-line per-source trail with mirror retry + timing detail.

    In-flight examples:
        TPB ⠋
        YTS ⠋ retry yts.am
    Final examples:
        TPB ✓ 10 (180ms)
        YTS ✓ 8 (420ms · 1 retry)
        EZTV ⚡ 5 cached 3m
        EZTV ✗ all mirrors failed (300ms)
    Persists in the header both during loading and after results render.
    """
    if not state.source_status:
        return Text("(starting fetch…)", style=PALETTE["metadata"])
    parts = [("trail: ", PALETTE["metadata"])]
    statuses = list(state.source_status.values())
    for i, s in enumerate(statuses):
        if i:
            parts.append(("  ·  ", PALETTE["metadata"]))
        parts.append((s.name, PALETTE["headline"]))
        parts.append((" ", ""))

        if s.in_flight:
            parts.append(("⠋", PALETTE["accent"]))
            if s.failed_mirrors_count:
                parts.append((f" retry {s.current_mirror}", PALETTE["metadata"]))
        elif s.final_state == "ok":
            parts.append(("✓ ", PALETTE["ok"]))
            parts.append((str(s.result_count), PALETTE["headline"]))
            timing = f" ({s.elapsed_ms}ms"
            if s.failed_mirrors_count:
                timing += f" · {s.failed_mirrors_count} retry"
            timing += ")"
            parts.append((timing, PALETTE["metadata"]))
        elif s.final_state == "cached":
            parts.append(("⚡ ", PALETTE["warn"]))
            parts.append((str(s.result_count), PALETTE["headline"]))
            parts.append((f" cached {s.cache_age}", PALETTE["metadata"]))
        elif s.final_state == "failed":
            parts.append(("✗ ", PALETTE["err"]))
            parts.append(("all mirrors failed", PALETTE["err"]))
            parts.append((f" ({s.elapsed_ms}ms)", PALETTE["metadata"]))
        elif s.final_state == "empty":
            parts.append(("· no results", PALETTE["metadata"]))
            parts.append((f" ({s.elapsed_ms}ms)", PALETTE["metadata"]))
    return Text.assemble(*parts)


def _summary_line(state: _AppState) -> Text:
    """Run-summary after fetch completes — top header row.

    `2 of 3 sources · 47 results · 1.8s — 'ubuntu'` style. Failure detail is
    surfaced in the trail line below, not duplicated here.
    """
    statuses = list(state.source_status.values())
    n_total = len(statuses) or 0
    n_ok = sum(1 for s in statuses if s.final_state in ("ok", "cached"))
    n_results = len(_all_results())

    bits = []
    if n_ok == n_total:
        bits.append(f"{n_total} sources")
    else:
        bits.append(f"{n_ok} of {n_total} sources")
    bits.append(f"{n_results} results")
    bits.append(f"{state.fetch_elapsed:.1f}s")
    return Text("  ·  ".join(bits) + f"  —  '{_state.query}'", style=PALETTE["metadata"])


def _selected_info_line(state: _AppState) -> Text:
    """Option D — second header row showing the selected row's source + name.

    Source name is painted in its per-source colour (deep_sky_blue1 / spring_green2 /
    medium_purple1), deliberately distant from the amber selection accent so the
    eye doesn't conflate the two.
    """
    entry = _selected_entry(state)
    if entry is None:
        return Text("(no row selected)", style=PALETTE["metadata"])
    source = entry.get("source", "?")
    source_style = SOURCE_COLOURS.get(source, PALETTE["headline"])
    name = entry.get("name", "")
    return Text.assemble(
        ("selected: ", PALETTE["metadata"]),
        (source, source_style),
        ("  ·  ", PALETTE["metadata"]),
        (name, PALETTE["metadata"]),
    )


def render_header(state: _AppState):
    """Three-row header.

    LOADING:  verb spinner   ·  trail (in-flight)        ·  (blank)
    RESULTS:  summary line   ·  trail (final + timing)   ·  selected: <src> · <name>
    FILTER:   summary line   ·  trail                     ·  Filter: /text_
    SEARCH:   blank          ·  blank                     ·  New search: text_
    """
    if state.mode == LOADING:
        verb_text = Text(state.current_verb + "…", style=PALETTE["headline"])
        if state._verb_spinner is None:
            state._verb_spinner = Spinner("dots", text=verb_text)
        else:
            state._verb_spinner.update(text=verb_text)
        return Group(state._verb_spinner, render_trail(state), Text(""))
    if state.mode == FILTER:
        return Group(
            _summary_line(state),
            render_trail(state),
            Text.assemble(
                ("Filter: ", PALETTE["headline"]),
                (f"/{state.filter_text}", PALETTE["accent"]),
                ("_", PALETTE["blink"]),
            ),
        )
    if state.mode == SEARCH:
        return Group(
            Text(""),
            Text(""),
            Text.assemble(
                ("New search: ", PALETTE["headline"]),
                (state.search_text, PALETTE["accent"]),
                ("_", PALETTE["blink"]),
            ),
        )
    if state.mode == RESULTS:
        return Group(_summary_line(state), render_trail(state), _selected_info_line(state))
    if state.mode in (MAGNET_VIEW, HELP):
        # Reuse the results header so the user keeps context while in an overlay.
        return Group(_summary_line(state), render_trail(state), _selected_info_line(state))
    return Group(Text(f"torrent-hound — '{_state.query}'", style=PALETTE["headline"]), Text(""), Text(""))


def _visible_row_estimate() -> int:
    """Rough count of rows the body slot can show, after chrome reserves.

    Rich renders the table inside the body Layout slot; if we slice more rows
    than fit, rich silently truncates the bottom — and the viewport stops
    scrolling because our window doesn't shift. Be conservative here; the
    viewport scrolls on a strict less-than check, so undershooting is safer
    than overshooting.
    """
    # Layout slots: header(3) + toast(1) + footer(1) = 5
    # Table chrome inside body: top border(1) + header(1) + bottom border(1) = 3
    # Optional title row (1, only when scrolled) — already accounted for in
    # `if not first page` adjustments below.
    return max(1, _console.size.height - 9)


def _scroll_into_view(state: _AppState) -> None:
    """Adjust state.view_top so state.selected_idx is on screen.

    Called from handle_key after selected_idx changes. Mimics ls/less: viewport
    only shifts when the selection moves off the current window.
    """
    visible = _visible_row_estimate()
    if state.selected_idx < state.view_top:
        state.view_top = state.selected_idx
    elif state.selected_idx >= state.view_top + visible:
        state.view_top = state.selected_idx - visible + 1
    if state.view_top < 0:
        state.view_top = 0


def render_table(state: _AppState) -> Table:
    rows = _visible_results(state)
    visible = _visible_row_estimate()
    start = max(0, min(state.view_top, max(0, len(rows) - visible)))
    end = start + visible
    windowed = rows[start:end]
    total = len(rows)
    suffix = f" (showing {start + 1}-{start + len(windowed)} of {total})" if total > visible else ""
    table = Table(
        title=Text(f"results{suffix}", style=PALETTE["metadata"]) if suffix else None,
        header_style=PALETTE["err"],
        padding=(0, 1),
        show_lines=False,
        expand=True,
    )
    table.add_column("No", justify="left", width=4)
    # Source column intentionally absent — the selected row's source is shown
    # in the header (Option D). Per-row attribution lives in the header line.
    table.add_column("Name", justify="left", no_wrap=True)
    table.add_column("Size", justify="right", width=10)
    table.add_column("S", justify="right", width=6)
    table.add_column("L", justify="right", width=5)
    table.add_column("S/L", justify="right", width=5)
    for i, r in enumerate(windowed):
        absolute_idx = start + i
        style = PALETTE["accent"] if absolute_idx == state.selected_idx else ""
        table.add_row(
            str(absolute_idx + 1),
            re.sub(r'[^\x20-\x7E]', '', r.get("name", ""))[:80],
            r.get("size", ""),
            str(r.get("seeders", "")),
            str(r.get("leechers", "")),
            str(r.get("ratio", "")),
            style=style,
        )
    return table


def render_empty_state(state: _AppState) -> Text:
    """N2 — friendlier message than an empty table."""
    if not _all_results():
        return Text(
            "No scents on that trail. Try broader terms, or add quality (1080p, 720p).",
            style=PALETTE["metadata"],
        )
    # Filter narrowed everything away
    return Text(
        f"No matches for '{state.filter_text}'. Esc to clear filter.",
        style=PALETTE["metadata"],
    )


def render_magnet_panel(state: _AppState) -> Panel:
    """Full-magnet overlay shown when the user presses `m`."""
    body = Text(state.magnet_view_text, style=PALETTE["accent"], overflow="fold")
    title_name = state.magnet_view_name[:80]
    return Panel(
        body,
        title=Text(f"magnet · {title_name}", style=PALETTE["headline"]),
        border_style=PALETTE["metadata"],
        padding=(1, 2),
    )


# Help-overlay sections — keep aligned with _FOOTER_HINTS and _CHORD_FOOTER_HINTS.
_HELP_SECTIONS = [
    ("Navigation", [
        ("↑ ↓",       "move selection"),
        ("q",         "quit"),
    ]),
    ("Act on the highlighted row", [
        ("c · ⏎",    "copy magnet to clipboard"),
        ("cs",        "copy magnet + open Seedr.cc"),
        ("m",         "show full magnet in overlay"),
        ("o",         "open torrent page in browser"),
        ("d",         "send magnet to default torrent client"),
        ("rd",        "submit to Real-Debrid"),
    ]),
    ("Search & filter", [
        ("/",         "live filter (type to narrow · esc to clear)"),
        ("s",         "new search query"),
        ("r",         "repeat current search"),
    ]),
    ("Help", [
        ("?",         "show / hide this overlay"),
    ]),
]


def render_help_panel() -> Panel:
    """Keystroke cheatsheet, shown when the user presses `?`."""
    rows = []
    for i, (section_name, keys) in enumerate(_HELP_SECTIONS):
        if i:
            rows.append(Text(""))  # blank between sections
        rows.append(Text(section_name, style=PALETTE["headline"]))
        for key, action in keys:
            rows.append(Text.assemble(
                ("  ", ""),
                (f"{key:8}", PALETTE["accent"]),
                ("  ", ""),
                (action, PALETTE["metadata"]),
            ))
    return Panel(
        Group(*rows),
        title=Text("torrent-hound — keystrokes", style=PALETTE["headline"]),
        border_style=PALETTE["metadata"],
        padding=(1, 2),
    )


def render_body(state: _AppState):
    if state.mode == MAGNET_VIEW:
        return render_magnet_panel(state)
    if state.mode == HELP:
        return render_help_panel()
    if not _visible_results(state) and state.mode != LOADING:
        return render_empty_state(state)
    return render_table(state)


def render_toast(state: _AppState) -> Text:
    return Text(state.toast or "", style=PALETTE["ok"])


# Mode-aware footer key hints. M3 from the UX polish spec — the footer
# adapts to the screen the user is on rather than dumping a static legend.
_FOOTER_HINTS = {
    LOADING:    "q quit",
    RESULTS:    "↑↓ move · ⏎/c copy · cs seedr · m magnet · o open · d download · r repeat · rd real-debrid · s search · / filter · ? help · q quit",
    FILTER:     "type to narrow · enter accept · esc cancel",
    SEARCH:     "type query · enter search · esc cancel",
    MAGNET_VIEW: "any key to return to results · q quit",
    RD_PICKER:  "0-9 pick · a all · enter confirm · esc cancel",
    RD_WAITING: "⏳ waiting on Debrid · esc cancel",
    HELP:       "any key to dismiss · q quit",
}

# Footer overrides while a chord prefix is pending. Surfacing the available
# extensions immediately makes the chord-timeout window feel like a deliberate
# menu instead of an unresponsive UI.
_CHORD_FOOTER_HINTS = {
    "c": "c…  →  s seedr  ·  (wait) copy magnet  ·  esc cancel",
    "r": "r…  →  d real-debrid  ·  (wait) repeat search  ·  esc cancel",
}


def render_footer(state: _AppState) -> Text:
    if state.chord_buffer in _CHORD_FOOTER_HINTS:
        return Text(_CHORD_FOOTER_HINTS[state.chord_buffer], style=PALETTE["accent"])
    return Text(_FOOTER_HINTS.get(state.mode, ""), style=PALETTE["metadata"])


def render(state: _AppState) -> Layout:
    layout = _build_layout()
    layout["header"].update(render_header(state))
    layout["body"].update(render_body(state))
    layout["toast"].update(render_toast(state))
    layout["footer"].update(render_footer(state))
    return layout


# ── entry ──────────────────────────────────────────────────────────────
def _rotate_verb(state: _AppState) -> None:
    """Swap to a fresh random verb if the rotate window has elapsed."""
    now = time.monotonic()
    if now - state.verb_set_at >= VERB_ROTATE_SECONDS:
        state.current_verb = random.choice(SEARCH_VERBS)
        state.verb_set_at = now


def _kick_off_fetch(state: _AppState) -> threading.Thread:
    """Launch searchAllSites in a worker; flip mode to RESULTS when done."""
    def _on_progress(name: str, event: dict) -> None:
        # Dict get-or-create + apply: under the GIL each step is atomic.
        status = state.source_status.get(name)
        if status is None:
            status = _SourceStatus(name=name)
            state.source_status[name] = status
        status.apply(event)

    def _worker() -> None:
        try:
            searchAllSites(_state.query, quiet_mode=True, progress_callback=_on_progress)
        finally:
            state.fetch_elapsed = time.monotonic() - state.fetch_started_at
            state.mode = RESULTS

    state.fetch_started_at = time.monotonic()
    state.source_status = {}
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread


def run_app() -> None:
    """Entry point for interactive mode. Replaces the old REPL `while` loop."""
    if not sys.stdin.isatty():
        # Piped stdin can't drive cbreak. Fall back to a non-interactive
        # message — caller should use --quiet / --json for scriptable output.
        print(
            "torrent-hound interactive mode requires a TTY. "
            "Use --quiet or --json for scriptable output."
        )
        return

    state = _AppState()
    state.current_verb = random.choice(SEARCH_VERBS)
    state.verb_set_at = time.monotonic()

    with cbreak(), Live(render(state), refresh_per_second=20, screen=True) as live:
        _kick_off_fetch(state)
        while True:
            # Poll stdin with timeout so the verb can rotate even with no input.
            rlist, _w, _x = select.select([sys.stdin], [], [], 0.1)
            if rlist:
                key = read_key()
                if not handle_key(state, key):
                    break
            if state.rd_request_entry is not None:
                _run_rd_suspended(live, state)
            if state.refetch_request:
                state.refetch_request = False
                _kick_off_fetch(state)
            if state.mode == LOADING:
                _rotate_verb(state)
            # Vim-style chord timeout: if the buffer's been sitting too long,
            # dispatch the prefix alone so `r`/`c` aren't permanently blocked.
            if state.chord_buffer and (time.monotonic() - state.chord_started_at) >= CHORD_TIMEOUT_SECONDS:
                _flush_chord(state)
            _expire_toast(state)
            live.update(render(state))


def _run_rd_suspended(live: Live, state: _AppState) -> None:
    """Drop out of the Live render so _cmd_rd's prints/inputs can drive the
    terminal directly, then restore the Live screen on completion. First-ship
    integration; a fully-native RD picker lands in a later iteration."""
    entry = state.rd_request_entry
    state.rd_request_entry = None
    live.stop()
    # Restore the cbreak'd terminal to cooked mode so input() inside _cmd_rd
    # works normally; re-enter cbreak when Live restarts.
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        # cooked mode for _cmd_rd
        cooked = termios.tcgetattr(fd)
        # tcgetattr returns the current attrs; we want canonical mode + echo.
        # Easier: temporarily restore the attrs that were set BEFORE cbreak() —
        # we don't have those here, so ask termios for sane defaults.
        cooked[3] |= termios.ICANON | termios.ECHO  # lflag
        termios.tcsetattr(fd, termios.TCSADRAIN, cooked)
        try:
            _cmd_rd(entry)
        except Exception as e:  # noqa: BLE001 — defence; RD path has many failure modes
            print(f"Real-Debrid error: {e}")
        input("\n[press enter to return to torrent-hound]")
        _set_toast(state, "Real-Debrid action complete")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        live.start()
