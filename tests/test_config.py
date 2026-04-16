"""Tests for the TOML config loader."""
from unittest.mock import patch

import pytest


def test_load_config_missing_file_returns_empty(th, tmp_path):
    missing = tmp_path / "nope.toml"
    with patch.object(th, "_config_path", lambda: missing):
        assert th._load_config() == {}


def test_load_config_valid_toml_returns_parsed(th, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[real_debrid]\ntoken = "abc"\naction = "downie"\n')
    with patch.object(th, "_config_path", lambda: path):
        cfg = th._load_config()
    assert cfg == {"real_debrid": {"token": "abc", "action": "downie"}}


def test_load_config_malformed_toml_warns_and_returns_empty(th, tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text("this is not [ valid toml")
    with patch.object(th, "_config_path", lambda: path):
        cfg = th._load_config()
    assert cfg == {}
    out = capsys.readouterr().out
    assert "not valid TOML" in out
    assert str(path) in out


def test_load_config_binary_file_warns_and_returns_empty(th, tmp_path, capsys):
    path = tmp_path / "config.toml"
    # Non-UTF-8 bytes — mimics an accidental binary file at the config path.
    path.write_bytes(b"\xff\xfe\x00\x00binary\x00garbage\x80")
    with patch.object(th, "_config_path", lambda: path):
        cfg = th._load_config()
    assert cfg == {}
    out = capsys.readouterr().out
    assert "not valid TOML" in out
    assert str(path) in out


def test_resolve_rd_token_env_wins(th, monkeypatch):
    monkeypatch.setenv("RD_TOKEN", "from-env")
    assert th._resolve_rd_token({"real_debrid": {"token": "from-config"}}) == "from-env"


def test_resolve_rd_token_config_fallback(th, monkeypatch):
    monkeypatch.delenv("RD_TOKEN", raising=False)
    assert th._resolve_rd_token({"real_debrid": {"token": "from-config"}}) == "from-config"


def test_resolve_rd_token_neither_returns_none(th, monkeypatch):
    monkeypatch.delenv("RD_TOKEN", raising=False)
    assert th._resolve_rd_token({}) is None
    assert th._resolve_rd_token({"real_debrid": {}}) is None


def test_resolve_rd_token_env_empty_falls_through(th, monkeypatch):
    monkeypatch.setenv("RD_TOKEN", "")
    assert th._resolve_rd_token({"real_debrid": {"token": "from-config"}}) == "from-config"


def test_resolve_rd_action_default_when_missing(th):
    assert th._resolve_rd_action({}) == "clipboard"
    assert th._resolve_rd_action({"real_debrid": {}}) == "clipboard"


@pytest.mark.parametrize("value", ["clipboard", "print", "browser", "downie"])
def test_resolve_rd_action_valid_values(th, value):
    assert th._resolve_rd_action({"real_debrid": {"action": value}}) == value


def test_resolve_rd_action_unknown_warns_and_falls_back(th, capsys):
    result = th._resolve_rd_action({"real_debrid": {"action": "bogus"}})
    assert result == "clipboard"
    out = capsys.readouterr().out
    assert "Unknown rd action 'bogus'" in out
    assert "clipboard" in out
