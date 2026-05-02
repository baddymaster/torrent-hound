"""Tests for the TPB fallback domain chain: first dead mirror shouldn't
break the search as long as any mirror in the list is reachable."""
from unittest.mock import MagicMock, patch

import requests


def _make_response(text):
    """Build a fake requests.Response-ish object carrying HTML bytes."""
    resp = MagicMock()
    resp.content = text.encode() if isinstance(text, str) else text
    return resp


def test_fallback_tries_next_domain_on_connection_error(th, tpb_ubuntu_html):
    """If the first mirror raises ConnectionError, the second should be tried
    and its results returned."""

    def fake_get(url, **kwargs):
        if "dead.invalid" in url:
            raise requests.ConnectionError("nope")
        return _make_response(tpb_ubuntu_html)

    with patch.object(th.sources.tpb, "TPB_DOMAINS", ["dead.invalid", "thepiratebay.zone"]):
        with patch.object(th.state, "tpb_working_domain", "dead.invalid"):
            with patch.object(th.requests, "get", side_effect=fake_get):
                results = th.searchPirateBayCondensed("ubuntu", timeout=1)
                assert len(results) > 0
                assert th.state.tpb_working_domain == "thepiratebay.zone"


def test_fallback_tries_next_domain_on_empty_response(th, tpb_ubuntu_html):
    """If the first mirror returns a 200 but no results table (a common CF/
    splash-page scenario), fallback should advance to the next mirror."""

    def fake_get(url, **kwargs):
        if "dead.invalid" in url:
            return _make_response("<html><body>Just a moment...</body></html>")
        return _make_response(tpb_ubuntu_html)

    with patch.object(th.sources.tpb, "TPB_DOMAINS", ["dead.invalid", "thepiratebay.zone"]):
        with patch.object(th.state, "tpb_working_domain", "dead.invalid"):
            with patch.object(th.requests, "get", side_effect=fake_get):
                results = th.searchPirateBayCondensed("ubuntu", timeout=1)
                assert len(results) > 0
                assert th.state.tpb_working_domain == "thepiratebay.zone"


def test_fallback_returns_empty_when_all_domains_fail(th, capsys):
    """If every mirror is unreachable, return [] and emit a clear message."""

    def always_fail(url, **kwargs):
        raise requests.ConnectionError("all dead")

    with patch.object(th.sources.tpb, "TPB_DOMAINS", ["a.invalid", "b.invalid"]):
        with patch.object(th.state, "tpb_working_domain", "a.invalid"):
            with patch.object(th.requests, "get", side_effect=always_fail):
                results = th.searchPirateBayCondensed("ubuntu", timeout=1)
                assert results == []
                assert "unreachable" in capsys.readouterr().out
