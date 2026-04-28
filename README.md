# Torrent Hound

[![CI](https://github.com/baddymaster/torrent-hound/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/baddymaster/torrent-hound/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/torrent-hound.svg)](https://pypi.org/project/torrent-hound/)
[![Python versions](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://github.com/baddymaster/torrent-hound/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)

A terminal-first torrent search CLI. Type a query, get ranked results from
multiple trackers in one live table, then act on a row with a single keystroke
— copy magnet, open page, send to your default torrent client, or hand off
to Real-Debrid.

```
$ torrent-hound ubuntu

3 sources  ·  23 results  ·  0.92s  —  'ubuntu'
trail: TPB ✓ 10 (180ms)  ·  YTS ✓ 8 (420ms · 1 retry)  ·  EZTV ⚡ 5 cached 3m
selected: TPB · ubuntu-24.04.1-desktop-amd64.iso

┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━┳━━━━┳━━━━━━┓
┃ No ┃ Name                                                 ┃      Size ┃  S ┃  L ┃  S/L ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━╇━━━━╇━━━━━━┩
│ 1  │ ubuntu-24.04.1-desktop-amd64.iso                     │   5.8 GB  │ 40 │  2 │ 20.0 │ ← amber
│ 2  │ Ubuntu 22.04 LTS                                     │   3.4 GB  │ 32 │  1 │ 32.0 │
│ …  │                                                      │           │    │    │      │
└────┴──────────────────────────────────────────────────────┴───────────┴────┴────┴──────┘

Magnet copied to clipboard
↑↓ move · ⏎/c copy · cs seedr · o open page · d download · r repeat · rd real-debrid · s search · / filter · q quit
```

## Sources

| Source         | Content   | Method                      |
|----------------|-----------|-----------------------------|
| The Pirate Bay | General   | HTML scrape, mirror chain   |
| YTS            | Movies    | JSON API, mirror chain      |
| EZTV           | TV shows  | JSON API via IMDB lookup    |

All sources are searched in parallel. Each source has a multi-mirror fallback
chain — if one mirror is down, the next is tried automatically. Results are
cached for the session (5-minute TTL).

## Requirements

- Python 3.10+
- Runtime dependencies: `beautifulsoup4`, `requests`, `pyperclip`, `rich`,
  `platformdirs`, `tomli_w`, `argcomplete`

## Install

```bash
pipx install torrent-hound          # recommended — isolated venv, on PATH
pip install torrent-hound           # plain pip
```

Pre-built standalone binaries (no Python required) for Linux / macOS / Windows
are on the [Releases page](https://github.com/baddymaster/torrent-hound/releases/latest).

From source:

```bash
git clone https://github.com/baddymaster/torrent-hound.git
cd torrent-hound
pip install -e ".[dev]"             # installs deps + pytest + ruff
```

### Shell completion

Tab-completion is provided by [`argcomplete`](https://github.com/kislyuk/argcomplete).
Add one line to your shell config:

**bash** (`~/.bashrc`):
```bash
eval "$(torrent-hound --print-completion bash)"
```

**zsh** (`~/.zshrc`):
```zsh
autoload -U compinit && compinit
eval "$(torrent-hound --print-completion zsh)"
```

Restart your shell, then `torrent-hound --<TAB>` cycles through flags.

> **Note:** Completion only works when installed via `pip` / `pipx`. The
> standalone binary doesn't expose the Python entry point that argcomplete
> hooks into.

## Usage

```
torrent-hound ubuntu
```

Drops you into a single-screen TUI. Three header rows, results table below,
mode-aware footer of keystroke hints at the bottom.

### Header

- **Top:** rotating verb spinner (during fetch) → run summary
  (`3 sources · 23 results · 0.92s — 'ubuntu'`) once results land.
- **Middle:** `trail:` line — per-source pip with mirror retry detail and
  inline timing. Persists above the table after fetch completes:
  ```
  trail: TPB ✓ 10 (180ms) · YTS ✓ 8 (420ms · 1 retry) · EZTV ⚡ 5 cached 3m
  ```
- **Bottom:** `selected: <source> · <name>` of the highlighted row.

### Keystrokes

#### Navigation

| Key     | Action                                                |
|---------|-------------------------------------------------------|
| `↑` / `↓` | Move selection (table scrolls when selection goes off-screen) |
| `?`     | Show / hide the keystroke help overlay                |
| `q`     | Quit                                                  |

#### Acting on the highlighted row

| Key       | Action                                                              |
|-----------|---------------------------------------------------------------------|
| `c` / `⏎` | Copy magnet to clipboard                                            |
| `cs`      | Copy magnet **and** open Seedr.cc                                   |
| `m`       | Show the full magnet in an overlay panel (any key returns)          |
| `o`       | Open the torrent page in your default browser                       |
| `d`       | Hand the magnet to your default torrent client                      |
| `rd`      | Real-Debrid: submit, fetch hoster links, dispatch via configured action |

`cs` and `rd` are chord commands — press the prefix (`c` or `r`) and the footer
shows the available extensions plus the standalone meaning. After ~1 second
without a follow-up, the standalone meaning fires (so `c` alone copies, `r`
alone repeats the last search).

#### Search & filter

| Key | Action                                                                     |
|-----|----------------------------------------------------------------------------|
| `/` | Enter live filter mode — type to narrow visible results, arrows still nav  |
| `s` | Enter new-search mode — type a new query, `⏎` to fetch                     |
| `r` | Repeat the current search (cached sources reused; failed sources retry)    |

In filter mode, `⏎` accepts the filter and exits to the results table; `Esc`
clears it.

### Scripting mode

```bash
torrent-hound --json ubuntu | jq '.tpb.results["0"].magnet'
torrent-hound --quiet ubuntu                     # plain Python repr to stdout
```

Either flag bypasses the TUI entirely and exits after printing.

## Real-Debrid integration

Send the highlighted torrent to [Real-Debrid](https://real-debrid.com) and
hand the resulting direct link to your download manager.

### Setup

```bash
torrent-hound --configure-rd
```

Prompts for your API token (get one at
[real-debrid.com/apitoken](https://real-debrid.com/apitoken)) and the action
to run against returned direct links, then writes them to a config file
with restrictive permissions (0600 on the file, 0700 on the parent).

For ad-hoc use without saving anything:

```bash
export RD_TOKEN="..."
```

### Action modes

| Mode        | What happens with the direct link(s)                                                    |
|-------------|-----------------------------------------------------------------------------------------|
| `clipboard` | *(default)* Copied to clipboard. Multiple links are joined with newlines.               |
| `print`     | Printed to stdout.                                                                      |
| `browser`   | Opened in your default browser (works without a separate download manager).             |
| `downie`    | Sent to [Downie 4](https://software.charliemonroe.net/downie/) via its `downie://` URL scheme (macOS). |

### Convenience flags

```bash
torrent-hound --configure-rd      # interactive setup (token + action)
torrent-hound --config-path       # print the resolved config file path
torrent-hound --user-status       # show RD account info (premium, expiration, points)
torrent-hound --revoke-rd-token   # invalidate the current token on RD
```

### Config file

Path:
- macOS: `~/Library/Application Support/torrent-hound/config.toml`
- Linux: `~/.config/torrent-hound/config.toml`
- Windows: `%APPDATA%\torrent-hound\config.toml`

Managed by `--configure-rd`, but plain TOML if you ever want to edit directly:

```toml
[real_debrid]
token  = "XXXXXXXXXXXXXXXXXXXXXXXXXXXX"
action = "downie"
```

### Usage

After a search, navigate to a row, press `rd`. The flow submits the torrent
to RD, waits for hoster links, and runs your configured action. Multi-file
torrents drop into an interactive picker on first invocation.

If RD is still processing (common for larger uncached torrents), you'll see
a "run again in a moment" message — re-running `rd` picks up where it left
off without re-prompting the picker.

### Troubleshooting

- `Real-Debrid rejected the token` — run `torrent-hound --configure-rd`.
- Connectivity errors (`DNS lookup failed`, `block page`, geo-block) — your
  ISP / network / proxy is filtering the RD API. Try a VPN or DoH resolver
  (`1.1.1.1`, `8.8.8.8`).
- Anything else — `torrent-hound --user-status` to check account state.
  Specific error messages reference RD's documented `error_code` values.

## Development

```bash
pip install -e ".[dev]"
pytest tests/
ruff check .
```

Tests run fully offline — parser fixtures are captured HTML, network calls
are mocked. The TUI is unit-tested at the `read_key` and `handle_key` layers
(see `tests/test_tui.py`); the rich.live event loop is manual-tested only.

### Package layout

```
torrent_hound/
  cli.py         — argparse + main() entry point
  tui.py         — rich.live TUI (single-screen app)
  state.py       — shared mutable state (results, urls, should_exit)
  cache.py       — per-session result cache
  config.py      — TOML config + Real-Debrid setup commands
  realdebrid.py  — RD API client + the rd flow
  ui.py          — rich Console singleton + table builders + JSON output
  sources/
    __init__.py  — _SOURCES registry + searchAllSites orchestrator
    base.py      — Source Protocol + shared helpers
    tpb.py       — The Pirate Bay
    yts.py       — YTS
    eztv.py      — EZTV
    legacy_1337x.py — dormant; kept for re-enable when CF landscape changes
```

### Adding a source

1. Create `torrent_hound/sources/foo.py` — implement `searchFoo(search_string,
   quiet_mode, limit, timeout, progress)` returning a list of result dicts
   with keys `name`, `link`, `seeders`, `leechers`, `size`, `ratio`, `magnet`.
   Call `progress({"type": "mirror_attempt", "mirror": ...})` etc. so the
   trail line lights up.
2. Register in `sources/__init__.py._SOURCES`.
3. Add a parser test in `tests/test_foo_parser.py`.

## Troubleshooting

- **SSL handshake errors:** see [these Stack Overflow answers](https://stackoverflow.com/questions/31649390/python-requests-ssl-handshake-failure)
  for common fixes.
- **`[PirateBay] Error : All known mirrors returned no results or were
  unreachable`:** every TPB domain in the fallback chain is blocked or down.
  Add a known-working mirror to `TPB_DOMAINS` in `torrent_hound/sources/tpb.py`.
- **Blocked by Cloudflare captcha:** some sources serve a CF challenge that
  requires a real browser. 1337x is currently dormant for this reason.
- **Arrow keys not working / ESC press doesn't cancel filter:** your terminal
  may be delivering escape sequences slowly. The TUI probes for 50ms after
  `\x1b` to distinguish bare ESC from arrow keys; if your terminal is slower
  than that, bump `_ESC_PROBE_SECONDS` at the top of `torrent_hound/tui.py`.

## Disclaimer

This software is provided as-is, with no warranty of any kind. It is intended
for discovering legally-distributable content and is **not** intended to be
used for downloading, distributing, or facilitating access to copyrighted
material without authorisation. You are responsible for complying with the
laws of your jurisdiction.

## License

AGPL-3.0 — see [LICENSE](LICENSE).
