"""Tests for the TUI's read_key parser and handle_key state machine.

`read_key` tests mock os.read + select.select to feed synthetic byte streams
through the parser. `handle_key` tests construct fresh _AppState instances
and assert state mutations after each key.

Why the tests exist: the read_key path has been bitten three times during
development (timing window too tight, Python TextIOWrapper buffering, missing
arrow handling in filter mode). These tests pin all of those down.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from torrent_hound import state as state_module
from torrent_hound.tui import (
    FILTER,
    HELP,
    LOADING,
    MAGNET_VIEW,
    RESULTS,
    SEARCH,
    _AppState,
    handle_key,
    read_key,
)

# ── read_key infrastructure ────────────────────────────────────────────

class _FakeStdin:
    """Replays the given byte chunks via os.read; reports "data available"
    on select.select if any chunks remain."""
    def __init__(self, chunks):
        self.chunks = deque(chunks)

    def os_read(self, fd, n):
        if not self.chunks:
            raise BlockingIOError("no chunks left — read_key called more reads than expected")
        chunk = self.chunks.popleft()
        return chunk[:n]

    def select(self, rlist, wlist, xlist, timeout):
        if self.chunks:
            return (rlist, [], [])
        return ([], [], [])


@contextmanager
def _patched_input(fake):
    """Patch sys.stdin (pytest replaces it with a non-tty mock that has no
    fileno()), os.read, and select.select for the duration of the block."""
    mock_stdin = MagicMock()
    mock_stdin.fileno.return_value = 0
    with patch("sys.stdin", mock_stdin), \
         patch("os.read", fake.os_read), \
         patch("select.select", fake.select):
        yield


# ── read_key tests ─────────────────────────────────────────────────────

def test_read_key_single_ascii_char():
    fake = _FakeStdin([b"c"])
    with _patched_input(fake):
        assert read_key() == "c"


def test_read_key_carriage_return():
    fake = _FakeStdin([b"\r"])
    with _patched_input(fake):
        assert read_key() == "\r"


def test_read_key_backspace():
    fake = _FakeStdin([b"\x7f"])
    with _patched_input(fake):
        assert read_key() == "\x7f"


def test_read_key_arrow_up():
    fake = _FakeStdin([b"\x1b", b"[A"])
    with _patched_input(fake):
        assert read_key() == "UP"


def test_read_key_arrow_down():
    fake = _FakeStdin([b"\x1b", b"[B"])
    with _patched_input(fake):
        assert read_key() == "DOWN"


def test_read_key_arrow_left():
    fake = _FakeStdin([b"\x1b", b"[D"])
    with _patched_input(fake):
        assert read_key() == "LEFT"


def test_read_key_arrow_right():
    fake = _FakeStdin([b"\x1b", b"[C"])
    with _patched_input(fake):
        assert read_key() == "RIGHT"


def test_read_key_bare_esc_returns_esc_without_blocking():
    """The original bug: bare ESC blocked because we tried to read more bytes."""
    fake = _FakeStdin([b"\x1b"])
    with _patched_input(fake):
        assert read_key() == "ESC"


def test_read_key_alt_letter_resolves_to_esc():
    """`\\x1b` followed by a letter (Alt+A) isn't a recognised mapping."""
    fake = _FakeStdin([b"\x1b", b"a"])
    with _patched_input(fake):
        assert read_key() == "ESC"


def test_read_key_unknown_csi_resolves_to_esc():
    """`\\x1b[X` — looks like CSI but X isn't one of UP/DOWN/LEFT/RIGHT/HOME/END."""
    fake = _FakeStdin([b"\x1b", b"[X"])
    with _patched_input(fake):
        assert read_key() == "ESC"


def test_read_key_arrow_sequence_arrives_in_one_burst():
    """Some terminals deliver `\\x1b[A` as a single 3-byte read."""
    fake = _FakeStdin([b"\x1b", b"[A"])
    with _patched_input(fake):
        assert read_key() == "UP"


# ── handle_key fixture: keep state-module mutations test-isolated ─────

@pytest.fixture
def reset_state():
    saved_results = state_module.results
    saved_query = state_module.query
    yield
    state_module.results = saved_results
    state_module.query = saved_query


def _populate_results(n: int) -> None:
    state_module.results = [
        {
            "name": f"row-{i}",
            "magnet": f"magnet:?xt=urn:btih:{i:040x}",
            "link": f"https://example.test/{i}",
            "source": "TPB",
            "size": "1 GB",
            "seeders": i,
            "leechers": i,
            "ratio": "1.0",
        }
        for i in range(n)
    ]


# ── handle_key — RESULTS mode navigation ──────────────────────────────

def test_handle_key_q_returns_false(reset_state):
    state = _AppState(mode=RESULTS)
    assert handle_key(state, "q") is False


def test_handle_key_down_advances_selection(reset_state):
    _populate_results(5)
    state = _AppState(mode=RESULTS, selected_idx=0)
    assert handle_key(state, "DOWN") is True
    assert state.selected_idx == 1


def test_handle_key_up_decrements_selection(reset_state):
    _populate_results(5)
    state = _AppState(mode=RESULTS, selected_idx=2)
    handle_key(state, "UP")
    assert state.selected_idx == 1


def test_handle_key_up_at_top_clamps_to_zero(reset_state):
    _populate_results(5)
    state = _AppState(mode=RESULTS, selected_idx=0)
    handle_key(state, "UP")
    assert state.selected_idx == 0


def test_handle_key_down_at_bottom_clamps(reset_state):
    _populate_results(5)
    state = _AppState(mode=RESULTS, selected_idx=4)
    handle_key(state, "DOWN")
    assert state.selected_idx == 4


def test_handle_key_down_on_empty_results_is_safe(reset_state):
    state_module.results = []
    state = _AppState(mode=RESULTS, selected_idx=0)
    handle_key(state, "DOWN")
    assert state.selected_idx == 0


def test_handle_key_slash_enters_filter_mode(reset_state):
    _populate_results(3)
    state = _AppState(mode=RESULTS, filter_text="leftover")
    handle_key(state, "/")
    assert state.mode == FILTER
    assert state.filter_text == ""    # cleared on entry


def test_handle_key_s_enters_search_mode(reset_state):
    state = _AppState(mode=RESULTS, search_text="leftover")
    handle_key(state, "s")
    assert state.mode == SEARCH
    assert state.search_text == ""    # cleared on entry


# ── handle_key — RESULTS mode chord (multi-char) ──────────────────────

def test_handle_key_c_alone_buffers_chord_prefix(reset_state):
    state = _AppState(mode=RESULTS)
    handle_key(state, "c")
    assert state.chord_buffer == "c"


def test_handle_key_cs_chord_dispatches_seedr(reset_state):
    _populate_results(3)
    state = _AppState(mode=RESULTS, selected_idx=0)
    with patch("torrent_hound.tui.pyperclip.copy") as m_copy, \
         patch("torrent_hound.tui.webbrowser.open") as m_open:
        handle_key(state, "c")
        handle_key(state, "s")
    assert state.chord_buffer == ""
    m_copy.assert_called_once()
    m_open.assert_called_once_with("https://www.seedr.cc", new=2)


def test_handle_key_rd_chord_sets_rd_request(reset_state):
    _populate_results(3)
    state = _AppState(mode=RESULTS, selected_idx=1)
    handle_key(state, "r")
    handle_key(state, "d")
    assert state.chord_buffer == ""
    assert state.rd_request_entry is not None
    assert state.rd_request_entry["name"] == "row-1"


def test_handle_key_r_then_unrelated_key_flushes_then_processes(reset_state):
    """`r` followed by `o` should: dispatch `r` (refetch), then `o` (open page)."""
    _populate_results(3)
    state = _AppState(mode=RESULTS, selected_idx=0)
    with patch("torrent_hound.tui.webbrowser.open") as m_open:
        handle_key(state, "r")
        handle_key(state, "o")
    assert state.chord_buffer == ""
    assert state.refetch_request is True            # 'r' was flushed
    assert m_open.call_count == 1                   # 'o' was processed after


def test_handle_key_esc_during_pending_chord_cancels_silently(reset_state):
    state = _AppState(mode=RESULTS, chord_buffer="r")
    handle_key(state, "ESC")
    assert state.chord_buffer == ""
    assert state.refetch_request is False            # NOT dispatched


def test_handle_key_c_alone_does_not_immediately_act(reset_state):
    """Pressing `c` should buffer, not act, until the chord resolves."""
    _populate_results(3)
    state = _AppState(mode=RESULTS, selected_idx=0)
    with patch("torrent_hound.tui.pyperclip.copy") as m_copy:
        handle_key(state, "c")
    m_copy.assert_not_called()


# ── handle_key — FILTER mode (the regression we're fixing) ────────────

def test_filter_printable_appends_to_filter_text(reset_state):
    state = _AppState(mode=FILTER, filter_text="ub")
    handle_key(state, "u")
    assert state.filter_text == "ubu"


def test_filter_backspace_removes_last_char(reset_state):
    state = _AppState(mode=FILTER, filter_text="ubu")
    handle_key(state, "\x7f")
    assert state.filter_text == "ub"


def test_filter_enter_exits_to_results_keeping_filter(reset_state):
    state = _AppState(mode=FILTER, filter_text="ubu")
    handle_key(state, "\r")
    assert state.mode == RESULTS
    assert state.filter_text == "ubu"


def test_filter_esc_exits_and_clears(reset_state):
    state = _AppState(mode=FILTER, filter_text="ubu")
    handle_key(state, "ESC")
    assert state.mode == RESULTS
    assert state.filter_text == ""


def test_filter_down_navigates_without_leaving_filter_mode(reset_state):
    """The bug: arrows in FILTER mode were silently dropped."""
    _populate_results(5)
    state = _AppState(mode=FILTER, filter_text="row", selected_idx=0)
    handle_key(state, "DOWN")
    assert state.mode == FILTER          # stays in filter
    assert state.selected_idx == 1


def test_filter_up_navigates_without_leaving_filter_mode(reset_state):
    _populate_results(5)
    state = _AppState(mode=FILTER, filter_text="row", selected_idx=2)
    handle_key(state, "UP")
    assert state.mode == FILTER
    assert state.selected_idx == 1


def test_filter_typing_resets_selection(reset_state):
    """Changing the filter shifts the visible rows; selection resets to the top."""
    _populate_results(5)
    state = _AppState(mode=FILTER, filter_text="row", selected_idx=3)
    handle_key(state, "0")
    assert state.selected_idx == 0


def test_filter_arrow_does_not_reset_selection(reset_state):
    """Arrow nav inside filter mode must NOT reset selection (filter unchanged)."""
    _populate_results(5)
    state = _AppState(mode=FILTER, filter_text="row", selected_idx=3)
    handle_key(state, "UP")
    assert state.selected_idx == 2


def test_filter_arrow_at_boundary_clamps(reset_state):
    _populate_results(3)
    state = _AppState(mode=FILTER, filter_text="row", selected_idx=2)
    handle_key(state, "DOWN")
    assert state.selected_idx == 2  # clamped


def test_filter_arrow_with_empty_filter_navigates_full_list(reset_state):
    _populate_results(5)
    state = _AppState(mode=FILTER, filter_text="", selected_idx=0)
    handle_key(state, "DOWN")
    assert state.selected_idx == 1


# ── handle_key — SEARCH mode ──────────────────────────────────────────

def test_search_printable_appends(reset_state):
    state = _AppState(mode=SEARCH, search_text="ubu")
    handle_key(state, "n")
    assert state.search_text == "ubun"


def test_search_enter_with_text_triggers_refetch(reset_state):
    state = _AppState(mode=SEARCH, search_text="ubuntu")
    handle_key(state, "\r")
    assert state.mode == LOADING
    assert state.refetch_request is True
    assert state_module.query == "ubuntu"


def test_search_enter_empty_returns_to_results(reset_state):
    state = _AppState(mode=SEARCH, search_text="")
    handle_key(state, "\r")
    assert state.mode == RESULTS
    assert state.refetch_request is False


def test_search_esc_clears_and_exits(reset_state):
    state = _AppState(mode=SEARCH, search_text="ubun")
    handle_key(state, "ESC")
    assert state.mode == RESULTS
    assert state.search_text == ""


def test_search_backspace_removes_last_char(reset_state):
    state = _AppState(mode=SEARCH, search_text="ubuntu")
    handle_key(state, "\x7f")
    assert state.search_text == "ubunt"


# ── handle_key — MAGNET_VIEW mode ─────────────────────────────────────

def test_m_enters_magnet_view_with_selected_magnet(reset_state):
    _populate_results(3)
    state = _AppState(mode=RESULTS, selected_idx=1)
    handle_key(state, "m")
    assert state.mode == MAGNET_VIEW
    assert state.magnet_view_text == state_module.results[1]["magnet"]
    assert state.magnet_view_name == state_module.results[1]["name"]


def test_m_on_empty_results_does_not_change_mode(reset_state):
    state_module.results = []
    state = _AppState(mode=RESULTS)
    handle_key(state, "m")
    assert state.mode == RESULTS
    assert state.magnet_view_text == ""


def test_magnet_view_any_key_returns_to_results(reset_state):
    state = _AppState(mode=MAGNET_VIEW, magnet_view_text="magnet:?xt=...")
    handle_key(state, "x")
    assert state.mode == RESULTS


def test_magnet_view_q_quits(reset_state):
    state = _AppState(mode=MAGNET_VIEW)
    assert handle_key(state, "q") is False


# ── handle_key — HELP mode ────────────────────────────────────────────

def test_question_mark_enters_help_mode(reset_state):
    state = _AppState(mode=RESULTS)
    handle_key(state, "?")
    assert state.mode == HELP


def test_help_any_key_returns_to_results(reset_state):
    state = _AppState(mode=HELP)
    handle_key(state, "x")
    assert state.mode == RESULTS


def test_help_q_quits(reset_state):
    state = _AppState(mode=HELP)
    assert handle_key(state, "q") is False


# ── handle_key — LOADING mode ─────────────────────────────────────────

def test_loading_q_quits(reset_state):
    state = _AppState(mode=LOADING)
    assert handle_key(state, "q") is False


def test_loading_arrows_ignored(reset_state):
    _populate_results(5)
    state = _AppState(mode=LOADING, selected_idx=0)
    handle_key(state, "DOWN")
    assert state.selected_idx == 0    # ignored while loading
