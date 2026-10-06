"""Scraping from asyncio code, such as a web backend.

Pages are downloaded with aiohttp, and parsed on a worker thread: parsing takes
tens of milliseconds of CPU per page, which would otherwise stall the event loop.

    from recipe_scrapers import aio

    async with aiohttp.ClientSession() as session:
        recipe = await aio.scrape_recipe(url, session=session)  # a dict, or:
        scraper = await aio.scrape_url(url, session=session)
        recipe = await aio.to_json(scraper)

Needs aiohttp: pip install "recipe-scrapers[async]".
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import ssl

from bs4.dammit import UnicodeDammit

from . import scrape_html as _scrape_html
from ._abstract import AbstractScraper
from ._exceptions import RecipeScrapersExceptions

try:
    import aiohttp
except ImportError as e:
    raise ImportError(
        'recipe_scrapers.aio needs aiohttp: pip install "recipe-scrapers[async]"'
    ) from e

# Many recipe sites turn away clients that don't look like a browser
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class FetchError(RecipeScrapersExceptions):
    """The page couldn't be loaded: an HTTP error, a timeout or a network failure.

    Unlike a page without a recipe, this may pass, so it can be worth a retry.
    """

    def __init__(self, url: str, status: int | None = None, reason: str = ""):
        self.url = url
        self.status = status  # None when there was no HTTP response
        super().__init__(f"Could not fetch {url}: {status or reason}")


async def scrape_url(
    url: str,
    *,
    session: aiohttp.ClientSession | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
    supported_only: bool = False,
    best_image: bool | None = None,
) -> AbstractScraper:
    """Downloads the page at url and scrapes the recipe on it.

    Pass a session to reuse its connections across calls. Browser-like headers
    are sent for any the session doesn't set; headers adds to or overrides them.
    Sites without a scraper of their own are read from their schema.org data,
    unless supported_only.

    Raises FetchError when the page can't be loaded, and otherwise whatever
    scrape_html raises, e.g. NoSchemaFoundInWildMode for a page without a recipe.
    """
    body, charset, final_url = await _fetch(url, session, headers, timeout)
    return await asyncio.to_thread(
        _parse, body, charset, final_url, supported_only, best_image
    )


async def scrape_recipe(
    url: str,
    *,
    session: aiohttp.ClientSession | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
    supported_only: bool = False,
    best_image: bool | None = None,
    executor: concurrent.futures.Executor | None = None,
) -> dict:
    """Downloads the page at url and returns its recipe as scraper.to_json() would.

    The page is parsed on executor, by default the event loop's threads. Threads
    still take turns with the event loop for the GIL, so for a busy backend pass
    a ProcessPoolExecutor: pages are then parsed in parallel and the event loop
    is never held up. Otherwise the same as scrape_url.
    """
    body, charset, final_url = await _fetch(url, session, headers, timeout)
    return await asyncio.get_running_loop().run_in_executor(
        executor, _parse_to_json, body, charset, final_url, supported_only, best_image
    )


async def scrape_html(
    html: str,
    org_url: str,
    *,
    supported_only: bool = False,
    best_image: bool | None = None,
) -> AbstractScraper:
    """Scrapes HTML you already have, on a worker thread."""
    return await asyncio.to_thread(
        _scrape_html,
        html,
        org_url,
        supported_only=supported_only,
        best_image=best_image,
    )


async def to_json(scraper: AbstractScraper) -> dict:
    """scraper.to_json() on a worker thread, as it extracts every field."""
    return await asyncio.to_thread(scraper.to_json)


async def _fetch(url, session, headers, timeout) -> tuple[bytes, str | None, str]:
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=_ssl_context())
        )
    request_headers = {
        key: value
        for key, value in DEFAULT_HEADERS.items()
        if key not in session.headers
    }
    request_headers.update(headers or {})
    try:
        async with session.get(
            url, headers=request_headers, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            if response.status >= 400:
                raise FetchError(url, response.status)
            return await response.read(), response.charset, str(response.url)
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        raise FetchError(url, reason=str(e) or type(e).__name__) from e
    finally:
        if own_session:
            await session.close()


def _parse(body, charset, url, supported_only, best_image) -> AbstractScraper:
    # Many pages only declare their charset in a <meta> tag
    known = [charset] if charset else []
    html = UnicodeDammit(body, known_definite_encodings=known, is_html=True)
    return _scrape_html(
        html.unicode_markup or body.decode("utf-8", errors="replace"),
        url,
        supported_only=supported_only,
        best_image=best_image,
    )


def _parse_to_json(body, charset, url, supported_only, best_image) -> dict:
    return _parse(body, charset, url, supported_only, best_image).to_json()


@functools.cache
def _ssl_context() -> ssl.SSLContext | bool:
    # python.org builds on macOS ship without CA certificates; certifi has them
    try:
        import certifi
    except ImportError:
        return True
    return ssl.create_default_context(cafile=certifi.where())
