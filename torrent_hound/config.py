"""TOML config file: load, save, RD setup / revoke / status / path commands.

Path resolved via platformdirs:
    Linux   : ~/.config/torrent-hound/config.toml (XDG)
    macOS   : ~/Library/Application Support/torrent-hound/config.toml
    Windows : %APPDATA%\\torrent-hound\\config.toml

Missing file is non-fatal. Malformed TOML prints a one-line warning and
acts as if no config exists.

Functions that talk to Real-Debrid (`_revoke_rd_token`, `_user_status`)
import RD helpers lazily — see notes inside each function.
"""
from __future__ import annotations

import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import platformdirs
import tomli_w

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # backport; same API surface we use


def _config_path():
    return Path(platformdirs.user_config_dir("torrent-hound")) / "config.toml"


def _load_config():
    path = _config_path()
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as e:
        print(f"Config file {path} is not valid TOML: {e}")
        return {}


def _resolve_rd_token(config):
    env = os.environ.get("RD_TOKEN")
    if env:
        return env
    return (config.get("real_debrid") or {}).get("token") or None


_RD_VALID_ACTIONS = ("clipboard", "print", "browser", "downie")


def _resolve_rd_action(config):
    value = (config.get("real_debrid") or {}).get("action")
    if value is None:
        return "clipboard"
    if value in _RD_VALID_ACTIONS:
        return value
    print(f"Unknown rd action '{value}' in config; using clipboard")
    return "clipboard"


def _save_config(config):
    """Write config dict to the resolved config path. Creates parent dirs.

    The file contains a bearer token; force 0600 on the file and 0700 on the
    parent dir (re-apply on overwrite in case a prior version was more open).
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except (OSError, NotImplementedError):
        pass  # best-effort on platforms without POSIX perms (e.g. Windows)
    path.write_text(tomli_w.dumps(config), encoding="utf-8")
    try:
        path.chmod(0o600)
    except (OSError, NotImplementedError):
        pass


def _prompt_rd_token():
    if sys.stdin.isatty():
        return getpass.getpass("Real-Debrid token (input hidden): ").strip()
    return sys.stdin.readline().strip()


_RD_ACTION_DESCRIPTIONS = {
    "clipboard": "Copy to clipboard; multi-link joined with newlines",
    "print":     "Print to stdout",
    "browser":   "Open in default browser",
    "downie":    "Send to Downie 4 via downie:// URL scheme (macOS)",
}


def _prompt_rd_action(default):
    """Interactive numbered picker for the RD action. Returns a valid action string.

    `default` is pre-selected and used on empty input. Re-prompts on invalid input.
    """
    items = list(_RD_VALID_ACTIONS)
    default_idx = items.index(default) + 1 if default in items else 1
    pad = max(len(n) for n in items) + len(" (default)")
    print("\nAction — what to do with direct links after rd<n> unrestricts them:")
    for i, name in enumerate(items, start=1):
        marker = " (default)" if i == default_idx else ""
        display = f"{name}{marker}".ljust(pad)
        print(f"  {i}. {display}  {_RD_ACTION_DESCRIPTIONS[name]}")
    while True:
        choice = input(f"Select [1-{len(items)}, Enter for default]: ").strip()
        if not choice:
            return items[default_idx - 1]
        try:
            n = int(choice)
            if 1 <= n <= len(items):
                return items[n - 1]
        except ValueError:
            pass
        print("Invalid selection, try again.")


def _configure_rd():
    """Interactive RD setup: prompt for token + action, write both to config.

    Supersedes the old --set-rd-token flow. Piped stdin (non-TTY) reads the token
    from the first line and preserves the existing action (or clipboard default)
    — this keeps `echo $TOKEN | torrent-hound --configure-rd` scripting workable.
    """
    token = _prompt_rd_token()
    if not token:
        print("No token entered; aborting.")
        return 1

    config = _load_config()
    existing_action = (config.get("real_debrid") or {}).get("action") or "clipboard"
    if existing_action not in _RD_VALID_ACTIONS:
        existing_action = "clipboard"

    if sys.stdin.isatty():
        action = _prompt_rd_action(default=existing_action)
    else:
        action = existing_action

    config.setdefault("real_debrid", {})["token"] = token
    config["real_debrid"]["action"] = action

    try:
        _save_config(config)
    except OSError as e:
        print(f"Failed to write config: {e}")
        return 1
    print(f"Real-Debrid setup saved to {_config_path()}")
    return 0


def _print_config_path():
    print(_config_path())
    return 0


def _revoke_rd_token():
    """Invalidate the current RD token via GET /disable_access_token, then offer to wipe it from config."""
    # Lazy import: the RD helpers still live in the monolith during the
    # migration. By call time the package has fully loaded and these names
    # are accessible via `torrent_hound.<name>`.
    from torrent_hound import _rd_request, _RdError
    config = _load_config()
    env_token = os.environ.get("RD_TOKEN")
    config_token = (config.get("real_debrid") or {}).get("token")
    token = env_token or config_token
    if not token:
        print("No RD token configured to revoke.")
        return 1
    try:
        _rd_request("GET", "/disable_access_token", token=token)
    except _RdError as e:
        print(str(e))
        return 1
    print("Token invalidated on Real-Debrid's side.")

    if env_token:
        # Don't touch config — env var's token is distinct from whatever's saved.
        print("(Token came from RD_TOKEN env var; unset it in your shell to clear locally.)")
        return 0
    if config_token:
        ans = input(f"Remove the token from {_config_path()}? [y/N] ")
        if ans.strip().lower() == "y":
            config["real_debrid"].pop("token", None)
            try:
                _save_config(config)
            except OSError as e:
                print(f"Failed to update config: {e}")
                return 1
            print(f"Token removed from {_config_path()}.")
    return 0


def _user_status():
    """Print a terse RD account summary via GET /user. Exit 0 on success, 1 on error."""
    # Lazy import — see _revoke_rd_token for rationale.
    from torrent_hound import _rd_request, _RdError
    config = _load_config()
    token = _resolve_rd_token(config)
    if not token:
        print(
            "Real-Debrid token not configured. Set RD_TOKEN env var or run "
            "torrent-hound --configure-rd."
        )
        return 1
    try:
        user = _rd_request("GET", "/user", token=token)
    except _RdError as e:
        print(str(e))
        return 1

    expiration = user.get("expiration", "") or ""
    days_msg = ""
    if expiration:
        try:
            exp_dt = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
            delta = exp_dt - datetime.now(timezone.utc)
            days_msg = f" ({delta.days} days remaining)" if delta.total_seconds() > 0 else " (expired)"
        except ValueError:
            pass

    print("Real-Debrid account")
    print(f"  Username      : {user.get('username', '?')}")
    print(f"  Type          : {user.get('type', '?')}")
    print(f"  Premium until : {expiration or '(none)'}{days_msg}")
    print(f"  Points        : {user.get('points', '?')}")
    return 0
