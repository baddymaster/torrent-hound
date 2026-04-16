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


def test_save_config_creates_dir_and_writes_toml(th, tmp_path):
    path = tmp_path / "sub" / "dir" / "config.toml"  # parent dirs don't exist yet
    with patch.object(th, "_config_path", lambda: path):
        th._save_config({"real_debrid": {"token": "abc", "action": "downie"}})
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert 'token = "abc"' in content
    assert 'action = "downie"' in content


def test_save_config_uses_restrictive_permissions(th, tmp_path):
    import stat
    import sys as _sys
    if _sys.platform == "win32":
        pytest.skip("POSIX permission semantics don't apply on Windows")
    path = tmp_path / "subdir" / "config.toml"
    with patch.object(th, "_config_path", lambda: path):
        th._save_config({"real_debrid": {"token": "secret"}})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_save_config_hardens_existing_loose_permissions(th, tmp_path):
    # Simulates an older config file left with 0644 — must be tightened on overwrite.
    import stat
    import sys as _sys
    if _sys.platform == "win32":
        pytest.skip("POSIX permission semantics don't apply on Windows")
    path = tmp_path / "config.toml"
    path.write_text('[real_debrid]\ntoken = "old"\n', encoding="utf-8")
    path.chmod(0o644)
    path.parent.chmod(0o755)
    with patch.object(th, "_config_path", lambda: path):
        th._save_config({"real_debrid": {"token": "new"}})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_save_config_preserves_existing_action(th, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[real_debrid]\naction = "print"\n', encoding="utf-8")
    with patch.object(th, "_config_path", lambda: path):
        cfg = th._load_config()
        cfg["real_debrid"]["token"] = "new-token"
        th._save_config(cfg)
    # Re-load and verify both keys present
    with patch.object(th, "_config_path", lambda: path):
        reloaded = th._load_config()
    assert reloaded["real_debrid"]["token"] == "new-token"
    assert reloaded["real_debrid"]["action"] == "print"


def test_set_rd_token_writes_token(th, tmp_path, capsys):
    path = tmp_path / "config.toml"
    with patch.object(th, "_config_path", lambda: path), \
         patch.object(th, "_prompt_rd_token", return_value="my-token"):
        rc = th._set_rd_token()
    assert rc == 0
    out = capsys.readouterr().out
    assert "token saved" in out.lower()
    assert "my-token" not in out  # MUST not echo the token
    with patch.object(th, "_config_path", lambda: path):
        cfg = th._load_config()
    assert cfg["real_debrid"]["token"] == "my-token"


def test_set_rd_token_preserves_existing_action(th, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[real_debrid]\naction = "browser"\n', encoding="utf-8")
    with patch.object(th, "_config_path", lambda: path), \
         patch.object(th, "_prompt_rd_token", return_value="tok"):
        rc = th._set_rd_token()
    assert rc == 0
    with patch.object(th, "_config_path", lambda: path):
        cfg = th._load_config()
    assert cfg["real_debrid"]["token"] == "tok"
    assert cfg["real_debrid"]["action"] == "browser"


def test_set_rd_token_empty_aborts(th, tmp_path, capsys):
    path = tmp_path / "config.toml"
    with patch.object(th, "_config_path", lambda: path), \
         patch.object(th, "_prompt_rd_token", return_value=""):
        rc = th._set_rd_token()
    assert rc == 1
    assert "aborting" in capsys.readouterr().out.lower()
    assert not path.exists()  # no file created on abort


def test_set_rd_token_write_failure(th, tmp_path, capsys):
    def fail_save(_):
        raise OSError("disk full")
    with patch.object(th, "_prompt_rd_token", return_value="tok"), \
         patch.object(th, "_save_config", side_effect=fail_save):
        rc = th._set_rd_token()
    assert rc == 1
    assert "failed to write" in capsys.readouterr().out.lower()


def test_print_config_path_prints_path(th, tmp_path, capsys):
    fake = tmp_path / "config.toml"
    with patch.object(th, "_config_path", lambda: fake):
        rc = th._print_config_path()
    assert rc == 0
    assert str(fake) in capsys.readouterr().out


def test_prompt_rd_token_tty_uses_getpass(th):
    with patch.object(th.sys.stdin, "isatty", return_value=True), \
         patch.object(th.getpass, "getpass", return_value="tty-token") as m_gp:
        result = th._prompt_rd_token()
    assert result == "tty-token"
    m_gp.assert_called_once()


def test_prompt_rd_token_piped_reads_stdin(th):
    class FakeStdin:
        def isatty(self): return False
        def readline(self): return "piped-token\n"
    with patch.object(th.sys, "stdin", FakeStdin()):
        result = th._prompt_rd_token()
    assert result == "piped-token"
