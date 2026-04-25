# Torrent Hound

[![CI](https://github.com/baddymaster/torrent-hound/actions/workflows/ci.yml/badge.svg?branch=experimental)](https://github.com/baddymaster/torrent-hound/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/torrent-hound.svg)](https://pypi.org/project/torrent-hound/)
[![Python versions](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://github.com/baddymaster/torrent-hound/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)

A terminal-first torrent search CLI. Type a query, get ranked results from
multiple trackers in one table, then copy a magnet link or open the torrent
page with a single keystroke.

```
$ torrent-hound ubuntu
                                          PirateBay
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━┳━━━━┳━━━━━━┓
┃ No ┃ Torrent Name                                         ┃      Size ┃  S ┃  L ┃  S/L ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━╇━━━━╇━━━━━━┩
│ 1  │ ubuntu-24.04.1-desktop-amd64.iso                     │  5.78 GiB │ 40 │  2 │ 20.0 │
│ 2  │ Ubuntu 22.04 LTS                                     │   3.4 GiB │ 32 │  1 │ 32.0 │
│ …  │                                                      │           │    │    │      │
└────┴──────────────────────────────────────────────────────┴───────────┴────┴────┴──────┘

Enter command : c1
Magnet link copied to clipboard!
```

## Sources

| Source         | Content    | Method                          |
|----------------|------------|---------------------------------|
| The Pirate Bay | General    | HTML scrape, mirror fallback    |
| YTS            | Movies     | JSON API, mirror fallback       |
| EZTV           | TV shows   | JSON API via IMDB lookup        |

All sources are searched in parallel.

## Requirements

- Python 3.10+
- Runtime dependencies: `beautifulsoup4`, `requests`, `pyperclip`, `rich`, `platformdirs`, `tomli_w`, `argcomplete`

## Install

```bash
pipx install torrent-hound          # recommended — isolated venv, auto-PATH
pip install torrent-hound           # or plain pip
```

Pre-built standalone binaries (no Python required) for Linux / macOS / Windows are on the [Releases page](https://github.com/baddymaster/torrent-hound/releases/latest).

From source:

```bash
git clone https://github.com/baddymaster/torrent-hound.git
cd torrent-hound
pip install -e ".[dev]"             # installs deps + pytest + ruff
```

### Shell completion

Torrent Hound uses [`argcomplete`](https://github.com/kislyuk/argcomplete)
for tab-completion of top-level flags. To enable, add one line to your
shell config:

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
> standalone binary from the GitHub Releases page doesn't expose the
> Python entry point that argcomplete hooks into.

## Usage

```
torrent-hound ubuntu
```

Results render as a table; enter a command at the prompt.

| Command  | Action                                                                     |
|----------|----------------------------------------------------------------------------|
| `m<n>`   | Print the magnet link for result `<n>`                                     |
| `c<n>`   | Copy the magnet link to clipboard                                          |
| `cs<n>`  | Copy the magnet and open Seedr.cc                                          |
| `rd<n>`  | Debrid via Real-Debrid and dispatch via configured action (requires token) |
| `d<n>`   | Hand the magnet to your default torrent client                             |
| `o<n>`   | Open the torrent page in your default browser                              |
| `p`      | Re-print the results table                                                 |
| `s`      | Enter a new query and search again                                         |
| `r`      | Repeat the last search (cached sources reused; failed sources retry)       |
| `u`      | Show the source URLs used for the current results                          |
| `h`      | Show the help menu                                                         |
| `q`      | Quit                                                                       |

### Scripting mode

```bash
torrent-hound --json ubuntu | jq '.tpb.results["0"].magnet'
```

`--json` emits a single valid JSON document to stdout and exits.

## Development

```bash
pip install -e ".[dev]"
pytest tests/
```

Tests run fully offline — parser fixtures are captured HTML, network calls are mocked.

## Real-Debrid integration

Torrent Hound can send a selected torrent to [Real-Debrid](https://real-debrid.com) and hand the resulting direct link to your download manager.

### Setup

One-command interactive setup:

```bash
torrent-hound --configure-rd
```

Prompts for your API token (get one at [real-debrid.com/apitoken](https://real-debrid.com/apitoken)) and the action to run against returned direct links, then writes them to the config file with restrictive permissions.

Alternatively, set `RD_TOKEN` as an env var for ad-hoc use without saving anything:

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

Path: `~/Library/Application Support/torrent-hound/config.toml` (macOS) / `~/.config/torrent-hound/config.toml` (Linux) / `%APPDATA%\torrent-hound\config.toml` (Windows). Managed by `--configure-rd`, but the format is plain TOML if you ever want to edit it directly:

```toml
[real_debrid]
token  = "XXXXXXXXXXXXXXXXXXXXXXXXXXXX"
action = "downie"
```

### Usage

After a search, type `rd<n>` (e.g. `rd3`). The flow submits the torrent to RD, waits for the hoster links, then runs your configured action. Multi-file torrents open an interactive file picker on the first invocation so you can choose exactly what to debrid.

If RD is still processing (common for larger or uncached torrents), you'll see a short "run again in a moment" message — re-running `rd<n>` picks up where it left off without re-prompting the picker.

### Troubleshooting

- `Real-Debrid rejected the token` — run `torrent-hound --configure-rd` to enter a fresh one.
- Connectivity errors (`DNS lookup failed`, `block page`, geo-block) — your ISP / network / proxy is filtering the RD API. Try a VPN or a DoH resolver (`1.1.1.1`, `8.8.8.8`).
- Anything else — run `torrent-hound --user-status` to check your account. Specific error messages reference RD's documented `error_code` values and link to what to do.

## Troubleshooting

- **SSL handshake errors**: see [these Stack Overflow answers](https://stackoverflow.com/questions/31649390/python-requests-ssl-handshake-failure) for common fixes.

- **`[PirateBay] Error : All known mirrors returned no results or were unreachable`**: every TPB domain in the fallback chain is blocked or down. Add a known-working mirror to `TPB_DOMAINS` at the top of `torrent-hound.py`.

- **Blocked by Cloudflare captcha**: some sources serve a CF challenge that requires a real browser.

## Disclaimer

This software is provided as-is, with no warranty of any kind. It is intended
for discovering legally-distributable content and is **not** intended to be used for downloading, distributing, or
facilitating access to copyrighted material without authorisation. You are
responsible for complying with the laws of your jurisdiction.

## License

AGPL-3.0 — see [LICENSE](LICENSE).
