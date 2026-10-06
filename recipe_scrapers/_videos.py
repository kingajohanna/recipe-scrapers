"""Finds a recipe's videos in schema.org data, OpenGraph tags and the page's embeds.

Each video is a dict whose "url" is the one to play: a YouTube watch URL, else a
media file (.mp4, .m3u8, ...), else whatever embed or page URL the site gave.
"""

from __future__ import annotations

import html
import re
from urllib.parse import urljoin, urlparse

import isodate

from ._utils import normalize_string

YOUTUBE_ID = re.compile(
    r"(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:[^#]*&)?v=|embed/|shorts/|live/|v/)"
    r"|youtu\.be/)([\w-]{11})"
)
MEDIA_FILE = re.compile(r"\.(?:mp4|m4v|mov|webm|m3u8|mpd)(?:$|[?#])", re.IGNORECASE)
EMBED_HOSTS = re.compile(
    r"//(?:[\w-]+\.)*(?:youtube(?:-nocookie)?\.com|youtu\.be|vimeo\.com|dailymotion\.com"
    r"|jwplayer\.com|jwplatform\.com|wistia\.(?:com|net)|brightcove\.net)/"
)
# Some sites' JSON-LD wraps ids in (HTML escaped) smart quotes, which no URL contains
QUOTES = str.maketrans("", "", '"\u201c\u201d\u2018\u2019')


def youtube_url(url: str | None) -> str | None:
    """The watch URL of the YouTube video that url points at, if any."""
    match = YOUTUBE_ID.search(url or "")
    return f"https://www.youtube.com/watch?v={match.group(1)}" if match else None


def is_playable(url: str) -> bool:
    """Whether an app can play url as is: a YouTube video or a media file."""
    return bool(youtube_url(url) or MEDIA_FILE.search(url))


def find_videos(schema, opengraph, soup, base_url: str) -> list[list[dict]]:
    """The page's videos in tiers: the recipe's own, the page's other structured
    data, then the players embedded in its HTML."""
    seen: set[str] = set()

    def unseen(videos):
        kept = []
        for video in videos:
            if video is None:
                continue
            urls = {video[key] for key in ("url", "content_url", "embed_url")}
            urls = {youtube_url(url) or url for url in urls if url}
            if not urls & seen:
                seen.update(urls)
                kept.append(video)
        return kept

    recipe_videos = unseen(
        _from_video_object(item, base_url) for item in schema.recipe_videos()
    )
    page_videos = unseen(
        [_from_video_object(item, base_url) for item in schema.page_videos()]
        + [_from_url(opengraph.video(), base_url)]
    )
    html_videos = unseen(_from_html(soup, base_url))
    return [recipe_videos, page_videos, html_videos]


def best_video_url(tiers: list[list[dict]]) -> str | None:
    """The URL of the first playable video in the first tier that has any."""
    for videos in tiers:
        if videos:
            playable = [video for video in videos if is_playable(video["url"])]
            return (playable or videos)[0]["url"]
    return None


def _from_video_object(item: dict, base_url: str) -> dict | None:
    content_url = _url(item.get("contentUrl"), base_url)
    embed_url = _url(item.get("embedUrl"), base_url)
    page_url = _url(item.get("url"), base_url)
    candidates = [url for url in (content_url, embed_url, page_url) if url]
    if not candidates:
        return None

    url = next(filter(None, map(youtube_url, candidates)), None)
    if url is None:
        encoding = str(item.get("encodingFormat") or "")
        files = [
            url
            for url in candidates
            if MEDIA_FILE.search(url) or (url == content_url and "video/" in encoding)
        ]
        url = (files or candidates)[0]

    return {
        "url": url,
        "content_url": content_url,
        "embed_url": embed_url,
        "thumbnail_url": _url(
            item.get("thumbnailUrl") or item.get("thumbnail"), base_url
        ),
        "name": _text(item.get("name")),
        "duration": _seconds(item.get("duration")),
        "upload_date": _text(item.get("uploadDate")),
    }


def _from_url(url: str | None, base_url: str, thumbnail_url: str | None = None):
    url = _url(url, base_url)
    if not url:
        return None
    is_file = bool(MEDIA_FILE.search(url))
    return {
        "url": youtube_url(url) or url,
        "content_url": url if is_file else None,
        "embed_url": None if is_file else url,
        "thumbnail_url": thumbnail_url,
        "name": None,
        "duration": None,
        "upload_date": None,
    }


def _from_html(soup, base_url: str):
    for iframe in soup.find_all("iframe"):
        for attr in ("src", "data-src", "data-lazy-src"):
            src = iframe.get(attr) or ""
            if EMBED_HOSTS.search(urljoin("https://x/", src)):
                yield _from_url(src, base_url)
                break

    # Lazy-loaded YouTube players (lite-youtube, WP Rocket) only hold the video id
    for tag in soup.select(
        "lite-youtube[videoid], [data-youtube-id], .rll-youtube-player[data-id]"
    ):
        video_id = (
            tag.get("videoid") or tag.get("data-youtube-id") or tag.get("data-id")
        )
        yield _from_url(f"https://www.youtube.com/watch?v={video_id}", base_url)

    for video in soup.find_all("video"):
        sources = [video.get("src"), video.get("data-src")]
        sources += [source.get("src") for source in video.find_all("source")]
        src = next((s for s in sources if s and not s.startswith("blob:")), None)
        yield _from_url(src, base_url, _url(video.get("poster"), base_url))


def _url(value, base_url: str) -> str | None:
    if isinstance(value, list):
        value = next((v for v in value if v), None)
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl") or value.get("@id")
    if not isinstance(value, str):
        return None
    value = html.unescape(value).translate(QUOTES).strip()
    if not value:
        return None
    url = urljoin(base_url, value)
    parts = urlparse(url)
    if parts.path in ("", "/") and not parts.query:
        return None  # A site's home page, which placeholder VideoObjects point at
    return url


def _text(value) -> str | None:
    if isinstance(value, list):
        value = next((v for v in value if v), None)
    if not isinstance(value, str):
        return None
    return normalize_string(value) or None


def _seconds(value) -> int | None:
    try:
        return round(isodate.parse_duration(value).total_seconds())
    except (isodate.ISO8601Error, TypeError, ValueError, AttributeError):
        return None
