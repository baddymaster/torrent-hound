"""The Pirate Bay source: multi-domain fallback + HTML parser."""

import re

import requests
from bs4 import BeautifulSoup

from torrent_hound import state
from torrent_hound.ui import colored

from .base import _extract_release_tags, _fmt_date, _fmt_runtime, removeAndReplaceSpaces

_DEFAULT_QUERY = 'ubuntu'

# `Movie.Title.2024.1080p` or `Movie Title (2024) [...]` — pull the
# rightmost 19xx/20xx so episode-numeric tokens (e.g. `1984`) don't
# false-match for content that's actually from a different decade.
_YEAR_RE = re.compile(r'\b(19\d{2}|20\d{2})\b')

# TPB domains tried in order. Mirrors churn often; add new ones to the front
# when they come up, drop dead ones from the tail.
TPB_DOMAINS = [
    'thepiratebay.zone',
    'thepiratebay.org',
    'tpb.party',
    'piratebay.party',
    'pirateproxy.live',
]


def _tpb_page_is_empty_results(html) -> bool:
    """True if `html` is a successfully-served TPB results page that just has
    zero matches (the searchResult table is present but contains only the
    header row). Distinguishes from dead/blocked mirrors so the source can
    emit `empty` (genuine no-results, stop probing) vs `mirror_failed`
    (table missing, try the next mirror)."""
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find("table", {"id": "searchResult"})
    if table is None:
        return False
    return len(table.find_all("tr")) <= 1


def _parse_tpb_html(html, domain='thepiratebay.zone', limit=10):
    """Parse a TPB search-results HTML document. Returns [] if the expected
    results table isn't present (domain is dead / blocked / CAPTCHA)."""
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find("table", {"id": "searchResult"})
    if table is None:
        return []
    trs = table.find_all("tr")[1:]  # drop header row
    parsed = []
    base = f'https://{domain}'
    for tr in trs[:limit]:
        tds = tr.find_all("td")
        try:
            link_name = tds[1].find("a", {"class": "detLink"})
            href = link_name["href"]
            link = href if href.startswith("http") else f"{base}{href}"
            res = {
                'name': link_name.contents[0].strip(),
                'link': link,
                'seeders': int(tds[2].contents[0]),
                'leechers': int(tds[3].contents[0]),
                'magnet': tds[1].find("img", {"alt": "Magnet link"}).parent['href'],
                'size': str(tds[1].find("font").contents[0].split(',')[1].split(' ')[2].replace('\xa0', ' ')),
            }
            try:
                res['ratio'] = format(float(res['seeders']) / float(res['leechers']), '.1f')
            except ZeroDivisionError:
                res['ratio'] = 'inf'
            metadata: dict = {"name": res["name"]}
            metadata.update(_extract_release_tags(res["name"]))
            year_matches = _YEAR_RE.findall(res["name"])
            if year_matches:
                metadata["released"] = year_matches[-1]
            res['metadata'] = metadata
            parsed.append(res)
        except (AttributeError, IndexError, KeyError):
            continue  # malformed row; skip
    return parsed


def searchPirateBayCondensed(search_string=None, quiet_mode=False, limit=10, timeout=8, progress=None):
    """Search TPB, trying known mirrors in order until one returns results.
    On success, remembers the working domain for subsequent calls in this run.

    `progress`, if provided, receives `mirror_attempt`/`mirror_failed`/`ok`/
    `failed` events for the TUI's source-trail display.
    """
    if search_string is None:
        search_string = _DEFAULT_QUERY

    # Try last-known-good domain first, then the rest
    domains_to_try = [state.tpb_working_domain] + [d for d in TPB_DOMAINS if d != state.tpb_working_domain]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}

    for domain in domains_to_try:
        url = f'https://{domain}/s/?q={removeAndReplaceSpaces(search_string)}&page=0&orderby=99'
        if progress:
            progress({"type": "mirror_attempt", "mirror": domain})
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            parsed = _parse_tpb_html(r.content, domain=domain, limit=limit)
            if parsed:
                state.tpb_working_domain = domain
                state.tpb_url = url
                state.results_tpb_condensed = parsed
                if progress:
                    progress({"type": "ok", "count": len(parsed), "mirror": domain})
                return parsed
            # Empty parse: distinguish "mirror served us a real no-hits page"
            # from "mirror is dead / blocked / CAPTCHA". Probing more mirrors
            # only makes sense for the latter.
            if _tpb_page_is_empty_results(r.content):
                state.tpb_working_domain = domain
                state.results_tpb_condensed = []
                if progress:
                    progress({"type": "empty"})
                return []
            if progress:
                progress({"type": "mirror_failed", "mirror": domain})
        except requests.RequestException:
            if progress:
                progress({"type": "mirror_failed", "mirror": domain})
            continue

    if not quiet_mode:
        print(colored.magenta("[PirateBay] Error : All known mirrors returned no results or were unreachable"))
    state.results_tpb_condensed = []
    if progress:
        progress({"type": "failed"})
    return state.results_tpb_condensed


# ── lazy detail-page fetch ──────────────────────────────────────────────

# Map from `<dt>` label text on the detail page to our metadata field name.
_DT_LABEL_TO_FIELD = {
    'Type:': 'category',
    'Files:': 'files',
    'Uploaded:': 'uploaded',
    'By:': 'uploader',
}

_IMDB_URL_RE = re.compile(r'imdb\.com/title/(tt\d+)')
# TPB description lines often have a leading space (the .nfo block is
# indented). Allow `^\s*` before each label.
_GENRE_RE    = re.compile(r'^\s*Genre:\s*(.+)', re.MULTILINE)
_DIRECTOR_RE = re.compile(r'^\s*Director:\s*(.+)', re.MULTILINE)
_STARS_RE    = re.compile(r'^\s*Stars?:\s*(.+)', re.MULTILINE)
_PLOT_RE     = re.compile(r'^\s*Plot:\s*(.+?)(?=\n\s*\n|\n\s*[A-Z]+:|\Z)', re.MULTILINE | re.DOTALL)
_DURATION_RE = re.compile(r'Duration\s*=\s*(\d{1,2}):(\d{2}):(\d{2})')
# Lines of the form `LABEL: value` for the misc bucket. Allow leading
# whitespace; LABEL is uppercase letters/digits/underscore/dash/space (≥ 2 chars).
_MISC_LINE_RE = re.compile(r'^\s*([A-Z][A-Z0-9 _-]{1,30}):\s*(.+)', re.MULTILINE)
# Labels we capture as structured fields above — exclude from misc.
_KNOWN_LABELS = frozenset({"GENRE", "DIRECTOR", "DIRECTORS", "STAR", "STARS",
                            "PLOT", "RUNTIME", "DURATION", "IMDB"})


def _parse_tpb_detail_html(html_bytes) -> dict:
    """Parse a TPB torrent detail page. Returns a metadata-shaped dict
    with the subset of keys the page actually carried; never raises.

    Three sources of fields:
      1. Structured `<dl class="col1">` / `<dl class="col2">` (Type, Files,
         Uploaded, By) — present on every page.
      2. Description block (`<div class="nfo">` or `<pre>`) — uploader
         convention is `Genre:`, `Director:`, `Stars:`, `Plot:`, plus an
         IMDB URL and a MEDIAINFO Duration line.
      3. Anything else of the form `LABEL: value` in the description
         lands in `misc` so unstructured uploader notes don't disappear.
    """
    if not html_bytes:
        return {}
    try:
        soup = BeautifulSoup(html_bytes, 'html.parser')
    except Exception:
        return {}

    md: dict = {}

    # 1. Structured <dl> blocks
    for dl in soup.select('dl.col1, dl.col2'):
        dts = dl.find_all('dt')
        dds = dl.find_all('dd')
        for dt, dd in zip(dts, dds, strict=False):
            label = dt.get_text(strip=True)
            value = dd.get_text(strip=True)
            field = _DT_LABEL_TO_FIELD.get(label)
            if not field or not value:
                continue
            if field == 'files':
                try:
                    md['files'] = int(value)
                except ValueError:
                    pass
            elif field == 'uploaded':
                d = _fmt_date(value)
                if d:
                    md['uploaded'] = d
            else:
                md[field] = value

    # 2. Description block — .nfo div or top-level <pre>
    desc_node = soup.find('div', class_='nfo') or soup.find('pre')
    desc = desc_node.get_text() if desc_node else ''

    if (m := _IMDB_URL_RE.search(desc)):
        md['imdb_code'] = m.group(1)
    if (m := _GENRE_RE.search(desc)):
        md['genre'] = m.group(1).strip()
    if (m := _DIRECTOR_RE.search(desc)):
        md['director'] = m.group(1).strip()
    if (m := _STARS_RE.search(desc)):
        # Cap at 5 names so the panel row stays short
        names = [n.strip() for n in m.group(1).split(',')]
        md['cast'] = ', '.join(names[:5])
    if (m := _PLOT_RE.search(desc)):
        md['summary'] = m.group(1).strip()
    if (m := _DURATION_RE.search(desc)):
        h, mn, s = (int(x) for x in m.groups())
        runtime = _fmt_runtime(h * 3600 + mn * 60 + s)
        if runtime:
            md['runtime'] = runtime

    # 3. Misc — every `LABEL: value` line that didn't match a known field.
    misc: dict = {}
    for m in _MISC_LINE_RE.finditer(desc):
        label = m.group(1).strip()
        if label.upper() in _KNOWN_LABELS:
            continue
        misc[label] = m.group(2).strip()
    if misc:
        md['misc'] = misc

    return md


def _fetch_tpb_metadata(detail_url, timeout=8):
    """Lazy fetch + parse for a TPB detail page. Returns the metadata dict
    on success, or `{}` on any HTTP / parse failure (caller surfaces the
    error in the panel footer)."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    try:
        r = requests.get(detail_url, headers=headers, timeout=timeout)
    except requests.RequestException:
        return {}
    if r.status_code != 200:
        return {}
    return _parse_tpb_detail_html(r.content)
