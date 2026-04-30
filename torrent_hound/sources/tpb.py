"""The Pirate Bay source: multi-domain fallback + HTML parser."""

import re

import requests
from bs4 import BeautifulSoup

from torrent_hound import state
from torrent_hound.ui import colored

from .base import _extract_release_tags, _fmt_date, _fmt_runtime, _normalise_codec, removeAndReplaceSpaces

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
# Single-line `Label: value` patterns (GalaxyRG-style descriptions).
_GENRE_RE    = re.compile(r'^\s*Genre:\s*(.+)', re.MULTILINE)
_DIRECTOR_RE = re.compile(r'^\s*Directors?:\s*(.+)', re.MULTILINE)
_STARS_RE    = re.compile(r'^\s*Stars?:\s*(.+)', re.MULTILINE)
_PLOT_RE     = re.compile(r'^\s*Plot:\s*(.+?)(?=\n\s*\n|\n\s*[A-Z]+:|\Z)', re.MULTILINE | re.DOTALL)
# Multi-line block format used by IMDB-style scrapes:
#   Directors
#   Name One
#   Name Two
#   <blank>
_DIRECTOR_BLOCK_RE = re.compile(
    r'^\s*Directors?\s*$\n((?:^\s*[^\s:][^\n:]*$\n?)+?)(?=^\s*$|\Z)',
    re.MULTILINE,
)
_STARS_BLOCK_RE = re.compile(
    r'^\s*Stars?\s*$\n((?:^\s*[^\s:][^\n:]*$\n?)+?)(?=^\s*$|\Z)',
    re.MULTILINE,
)
# Slash-separated genre line on its own (no `Genre:` prefix). Conservative —
# require ≥ 3 segments to avoid false positives on "I/O" or "and/or" prose.
_SLASH_GENRE_RE = re.compile(
    r'^\s*([A-Z][a-z]+(?:\s*/\s*[A-Z][a-z]+){2,})\s*$',
    re.MULTILINE,
)
# Multiple duration formats — try each in order:
#   `Duration = HH:MM:SS` (GalaxyRG MEDIAINFO)
#   `Duration : 1 h 32 min` (R8 aligned-row format)
#   `Duration.....: 1h 34mn` (R4 dot-padded label, `mn` minute alias)
#   `Length..............: 1h30mn` (R7 — `Length` label alias, no internal space)
#   `[RUNTIME]:.[ 1Hr 32Min` (R3 bracketed format)
_DURATION_HMS_RE = re.compile(
    r'(?:Duration|Runtime|Length|RUNTIME\b[^\n]*)[\s=:.]+\s*(\d{1,2}):(\d{2}):(\d{2})',
    re.IGNORECASE,
)
_DURATION_HM_RE = re.compile(
    r'(?:Duration|Runtime|Length|\[\s*RUNTIME\s*\][^\n]*?)[\s=:.]+\s*\[?\s*'
    r'(\d+)\s*(?:h|hr|hour)s?\.?\s*(\d+)\s*(?:m|mn|min|minute)s?\.?',
    re.IGNORECASE,
)
# Misc-line patterns (broader). Three shapes the parser recognises:
#   `[LABEL]:....[ value`        — bracketed label + bracketed value (R3, R10)
#   `Label.......: value`        — aligned `Label : value` with optional dot
#                                   padding between label and colon (R4, R7, R8)
#   `LABEL: value`               — uppercase-only label (GalaxyRG)
_MISC_BRACKETED_RE = re.compile(
    r'^\s*\[([A-Z][A-Z0-9 _-]{1,30})\][:.\s]+\[\s*(.+?)\s*\]?\s*$',
    re.MULTILINE,
)
_MISC_ALIGNED_RE = re.compile(
    r'^\s*\.?([A-Z][A-Za-z0-9 _()-]{1,40}?)[.\s]*:\s+(.+?)\s*$',
    re.MULTILINE,
)
_MISC_UPPER_RE = re.compile(
    r'^\s*([A-Z][A-Z0-9 _-]{1,30}):\s*(.+)',
    re.MULTILINE,
)
# Bracketed [GENRE] — extract structured genre when no `Genre:` line exists.
_BRACKETED_GENRE_RE = re.compile(
    r'^\s*\[\s*GENRE\s*\][:.\s]+\[\s*(.+?)\s*\]?\s*$',
    re.MULTILINE,
)
# Video codec — pick the first recognised codec mention anywhere in
# the description. AVC / HEVC are the underlying H.264 / H.265 specs;
# x264 / x265 are encoder names. Both forms appear in the wild.
_VIDEO_CODEC_RE = re.compile(
    r'\b(x265|x264|h\.?265|h\.?264|HEVC|AVC|XviD|DivX|VP9|AV1)\b',
    re.IGNORECASE,
)
# Audio channels — common surround configurations (5.1, 7.1, 2.0).
# Anchored to a digit boundary so dates like 5.12.2024 don't match.
_AUDIO_CHANNELS_RE = re.compile(
    r'\b([1-9](?:\.[0-9])?)\s*(?:channels?|surround|stereo)\b',
    re.IGNORECASE,
)
# Audio codec — first recognised audio format in the description.
_AUDIO_CODEC_RE = re.compile(
    r'\b(AAC|FLAC|MP3|Opus|TrueHD|Atmos|DTS(?:-HD)?|E-?AC-?3|AC-?3|DDP?\d?(?:\.\d)?)\b',
    re.IGNORECASE,
)
# Subtitles — bracketed `[SUBTITLES]:` (R3, R10), aligned `Subtitle(s) : list`
# (R7, R8), or single-line `Subtitles: list`.
_SUBTITLES_RE = re.compile(
    r'(?:^\s*\[\s*SUBTITLES?\s*\][:.\s]+\[\s*|'
    r'^\s*Subtitles?\s*\(?s?\)?[.\s]*:\s+|'
    r'^\s*Included subtitles\s*=\s*)'
    r'(.+?)(?:\s*\(SRT File\))?\s*\]?\s*$',
    re.MULTILINE | re.IGNORECASE,
)
# Labels we already capture as structured fields — exclude from misc.
_KNOWN_LABELS = frozenset({
    "GENRE", "DIRECTOR", "DIRECTORS", "STAR", "STARS", "PLOT",
    "RUNTIME", "DURATION", "IMDB",
})


def _extract_director(desc: str) -> str | None:
    """Try `Director:` single-line first, fall back to `Directors\\n<block>`."""
    if (m := _DIRECTOR_RE.search(desc)):
        return m.group(1).strip()
    if (m := _DIRECTOR_BLOCK_RE.search(desc)):
        names = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
        if names:
            return ", ".join(names)
    return None


def _extract_cast(desc: str) -> str | None:
    """Try `Stars:` single-line first, fall back to `Stars\\n<block>`. Cap at 5."""
    if (m := _STARS_RE.search(desc)):
        names = [n.strip() for n in m.group(1).split(",") if n.strip()]
    elif (m := _STARS_BLOCK_RE.search(desc)):
        names = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
    else:
        return None
    return ", ".join(names[:5]) if names else None


def _extract_genre(desc: str) -> str | None:
    """Try `Genre:` single-line first, then a bare slash-separated line,
    then bracketed `[GENRE]:....[ value` (R10/YIFY format)."""
    if (m := _GENRE_RE.search(desc)):
        return m.group(1).strip()
    if (m := _SLASH_GENRE_RE.search(desc)):
        return m.group(1).strip()
    if (m := _BRACKETED_GENRE_RE.search(desc)):
        return m.group(1).strip()
    return None


def _extract_video_codec(desc: str) -> str | None:
    """First recognised video codec mention in the description (used by
    the lazy-fetch path; eager extraction from the torrent name lives in
    `_extract_release_tags`). Conventionally cased — `x264` lowercase,
    `AVC` / `HEVC` uppercase, etc."""
    if (m := _VIDEO_CODEC_RE.search(desc)):
        return _normalise_codec(m.group(1))
    return None


def _extract_audio(desc: str) -> str | None:
    """Audio info from the detail-page description. Combines audio codec
    (AAC/DTS/E-AC-3/...) and channel layout (5.1/7.1/2.0/6 channels) when
    both are nearby; falls back to whichever is found alone. A bare integer
    channel count (`6`) gets `' channels'` appended so it doesn't read as
    an isolated number."""
    codec = None
    channels = None
    if (m := _AUDIO_CODEC_RE.search(desc)):
        codec = m.group(1)
    if (m := _AUDIO_CHANNELS_RE.search(desc)):
        channels = m.group(1)
        # `6` → `6 channels`; `5.1` / `7.1` already self-describing.
        if "." not in channels:
            channels = f"{channels} channels"
    if codec and channels:
        return f"{codec} {channels}"
    return codec or channels


# Multi-line subtitle table (R4-style):
#   Subtitles
#
#   Codec...................... Language
#
#   srt ....................... English
#   srt ....................... Dutch
#   ...
_SRT_LANGUAGE_RE = re.compile(
    r'^\s*srt[\s.]+([A-Z][a-z]+)\s*$',
    re.MULTILINE,
)


def _extract_subtitles(desc: str) -> str | None:
    """Subtitle language list from the detail-page description.
    Handles bracketed `[SUBTITLES]:` (R3/R10), aligned `Subtitle(s) :`
    (R7/R8), `Included subtitles =` (GalaxyRG), and the multi-line
    `srt ....... <Language>` table format (R4).

    Rejects URL values — some uploaders point to subtitle download
    sites (e.g. `Subtitles : https://subscene.com/...`); that's not
    a language list."""
    if (m := _SUBTITLES_RE.search(desc)):
        text = m.group(1).strip().rstrip(",")
        text = re.sub(r'\s*\(SRT File\)\s*$', '', text, flags=re.IGNORECASE).strip()
        if text and not text.startswith(("http://", "https://", "www.")):
            return text
    # Multi-line `srt .... Language` rows (R4 / Subtitles section)
    langs = _SRT_LANGUAGE_RE.findall(desc)
    if langs:
        return ", ".join(langs)
    return None


# Non-plot indicators — keywords whose presence in a paragraph rules it
# out as a movie summary. Covers technical / encoding / playback notes
# (R3's "Compliant with Xbox360/PS3..." paragraph) and torrent-site
# promotional / group-credit content (R5's "Big Shout Out to all who
# support our group, our fellow colleague Encoders / Remuxers..."
# paragraph; R10's "list of upcoming uploads, instant chat, account
# registration..." paragraph).
_NON_PLOT_KEYWORDS_RE = re.compile(
    r'\b('
    r'kHz|kb/?s|Mb/?s|Kbps|Mbps|AAC|AC-?3|MP3|FLAC|x264|x265|HEVC|BluRay|HDR|'
    r'Xbox|PS[345]|VLC|VBR|CBR|playback|audio stream|video format|'
    r'encoders?|remuxers?|remux|mkv|m2ts|nfo|'
    r'yify|yify-torrents|torrents?|uploads?|seeders?|leechers?|'
    r'registration|subtitles?|screenshots?'
    r')\b',
    re.IGNORECASE,
)
# Labeled summary blocks — before the bare-paragraph fallback, look
# for a 'Storyline'/'Synopsis'/'Plot'/'Description' header on its own
# line followed by paragraph content. Reliable when present (R4 uses
# 'Storyline'); falls through to bare-paragraph when missing (R1/R2/R10).
_LABELED_PLOT_BLOCK_RE = re.compile(
    r'^\s*(?:Storyline|Synopsis|Description|About\s+the\s+Movie)\s*$\n+'
    r'\s*(.+?)(?=\n\s*\n|\Z)',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


_HEADER_FIRST_LINE_RE = re.compile(r'^[A-Z][A-Z0-9 ]{3,29}\s*$')


def _extract_summary(desc: str) -> str | None:
    """Try `Plot:` label first; otherwise pick the longest plain-prose
    paragraph in the description that doesn't trip the
    non-plot-keyword filter (technical specs, playback notes, torrent-site
    promo text — none of which are movie plots).

    Also skip paragraphs whose first line is an ALL-CAPS label like
    `RELEASE NOTES`, `INFO`, `WARNING`, `DISCLAIMER` — those are
    uploader announcements, not movie plots."""
    if (m := _PLOT_RE.search(desc)):
        return m.group(1).strip()
    # Labeled-block second: 'Storyline\n\n<text>' / 'Synopsis\n\n<text>'
    if (m := _LABELED_PLOT_BLOCK_RE.search(desc)):
        return m.group(1).strip()
    candidates = []
    for para in re.split(r'\n\s*\n', desc):
        text = para.strip()
        if len(text) < 80:
            continue
        if text.startswith("[") or "~~~" in text or "---" in text:
            continue
        head = text[:100]
        if ":" in head or "=" in head:
            continue
        if _NON_PLOT_KEYWORDS_RE.search(text):
            continue
        # Skip paragraphs that lead with an ALL-CAPS header line
        # (e.g. "RELEASE NOTES\nDisc was fully supported by eac3to...").
        first_line = text.split("\n", 1)[0].strip()
        if _HEADER_FIRST_LINE_RE.fullmatch(first_line):
            continue
        candidates.append(text)
    if not candidates:
        return None
    return max(candidates, key=len)


def _extract_runtime(desc: str) -> str | None:
    """Try HH:MM:SS first, then 'X h Y min' / '[RUNTIME]:.[ XHr YMin'."""
    if (m := _DURATION_HMS_RE.search(desc)):
        h, mn, s = (int(x) for x in m.groups())
        return _fmt_runtime(h * 3600 + mn * 60 + s)
    if (m := _DURATION_HM_RE.search(desc)):
        h, mn = (int(x) for x in m.groups())
        return _fmt_runtime(h * 3600 + mn * 60)
    return None


def _extract_misc(desc: str) -> dict:
    """Collect any `LABEL: value`-shaped lines we didn't structure as a known
    field. Three line shapes are recognised; the first match wins per label
    so a bracketed line doesn't double-count as an aligned line."""
    misc: dict = {}

    def _add(label: str, value: str) -> None:
        label = label.strip()
        if not label or label.upper() in _KNOWN_LABELS:
            return
        # Don't overwrite an earlier capture for the same label.
        if label not in misc:
            misc[label] = value.strip()

    for m in _MISC_BRACKETED_RE.finditer(desc):
        _add(m.group(1), m.group(2))
    for m in _MISC_ALIGNED_RE.finditer(desc):
        _add(m.group(1), m.group(2))
    for m in _MISC_UPPER_RE.finditer(desc):
        _add(m.group(1), m.group(2))
    return misc


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
    if (val := _extract_genre(desc)):
        md['genre'] = val
    if (val := _extract_director(desc)):
        md['director'] = val
    if (val := _extract_cast(desc)):
        md['cast'] = val
    if (val := _extract_summary(desc)):
        md['summary'] = val
    if (val := _extract_video_codec(desc)):
        md['codec'] = val
    if (val := _extract_audio(desc)):
        md['audio'] = val
    if (val := _extract_subtitles(desc)):
        md['subtitles'] = val
    runtime = _extract_runtime(desc)
    if runtime:
        md['runtime'] = runtime

    # 3. Misc — bracketed/aligned/uppercase `LABEL: value` lines that
    # didn't match a known structured field.
    misc = _extract_misc(desc)
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
