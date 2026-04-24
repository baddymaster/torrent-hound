"""Regression tests for argcomplete shell-completion integration.

The integration is two lines of code (a marker comment and a call to
argcomplete.autocomplete), but both have subtle failure modes that are
silent — completion just stops working, the CLI keeps running fine.
These tests catch the two realistic regressions.
"""
import re
from pathlib import Path


def test_build_parser_parses_known_flags(th):
    """_build_parser() returns a parser that handles all documented flags."""
    parser = th._build_parser()

    args = parser.parse_args(["--quiet", "ubuntu"])
    assert args.quiet is True
    assert args.query == ["ubuntu"]

    args = parser.parse_args(["--json", "debian"])
    assert args.as_json is True

    args = parser.parse_args(["--config-path"])
    assert args.config_path is True

    args = parser.parse_args(["--configure-rd"])
    assert args.configure_rd is True

    args = parser.parse_args(["--user-status"])
    assert args.user_status is True

    args = parser.parse_args(["--revoke-rd-token"])
    assert args.revoke_rd_token is True


def test_marker_comment_present_near_top():
    """argcomplete requires the # PYTHON_ARGCOMPLETE_OK marker within the first
    ~1024 bytes of the script it loads. For the package, that's __init__.py
    — which is what `import torrent_hound` resolves to. If the marker is
    missing or pushed past the scan window, shell completion silently stops
    working.
    """
    source = Path(__file__).parent.parent / "torrent_hound" / "__init__.py"
    head = source.read_bytes()[:1024]
    assert b"# PYTHON_ARGCOMPLETE_OK" in head, (
        "argcomplete marker missing from the first 1024 bytes of torrent_hound/__init__.py"
    )


def test_autocomplete_called_before_parse_args_in_main(th):
    """Within main(), argcomplete.autocomplete(...) must be called before
    parser.parse_args(). If the order flips, completion silently stops firing.
    (The 'after all add_argument' half of the ordering is enforced structurally
    by the _build_parser() refactor — the helper returns a fully-built parser
    before main() touches it.)
    """
    import inspect
    source = inspect.getsource(th.main)

    m_autocomplete = re.search(r"argcomplete\.autocomplete\(", source)
    m_parse = re.search(r"parser\.parse_args\(", source)

    assert m_autocomplete is not None, "argcomplete.autocomplete() not called in main()"
    assert m_parse is not None, "parser.parse_args() not called in main()"
    assert m_autocomplete.start() < m_parse.start(), (
        "argcomplete.autocomplete() must be called before parser.parse_args()"
    )
