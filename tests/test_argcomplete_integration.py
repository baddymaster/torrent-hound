"""Regression tests for argcomplete shell-completion integration.

The integration is two lines of code (a marker comment and a call to
argcomplete.autocomplete), but both have subtle failure modes that are
silent — completion just stops working, the CLI keeps running fine.
These tests catch the two realistic regressions.
"""
import re  # noqa: F401  # used by tests added in Task 3
from pathlib import Path  # noqa: F401  # used by tests added in Task 3


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
