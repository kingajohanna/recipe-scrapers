import asyncio
import concurrent.futures
import functools
import json
import multiprocessing
import unittest

from recipe_scrapers._exceptions import NoSchemaFoundInWildMode

try:
    import aiohttp
    from aiohttp import web
    from aiohttp.test_utils import TestServer

    from recipe_scrapers import aio
except ImportError:
    aio = None

RECIPE = {
    "@context": "https://schema.org",
    "@type": "Recipe",
    "name": "Töltött káposzta",
    "recipeIngredient": ["1 fej káposzta"],
    "recipeInstructions": "Megtöltjük.",
    "video": {"@type": "VideoObject", "contentUrl": "https://cdn.example.com/k.mp4"},
}
# Hungarian in a legacy charset that only the <meta> tag declares
RECIPE_PAGE = (
    '<html><head><meta charset="iso-8859-2">'
    f'<script type="application/ld+json">{json.dumps(RECIPE, ensure_ascii=False)}</script>'
    "</head><body></body></html>"
).encode("iso-8859-2")


def served(test):
    """Runs an async test with a local server up as self.server."""

    @functools.wraps(test)
    def run(self):
        async def main():
            self.server = TestServer(self.app())
            await self.server.start_server()
            try:
                await test(self)
            finally:
                await self.server.close()

        try:
            asyncio.run(main())
        finally:
            del self.server  # Test cases are pickled to run them in parallel

    return run


@unittest.skipIf(aio is None, "needs aiohttp")
class TestAio(unittest.TestCase):
    def setUp(self):
        self.user_agents = []

    def app(self):
        async def recipe(request):
            self.user_agents.append(request.headers.get("User-Agent"))
            return web.Response(body=RECIPE_PAGE, content_type="text/html")

        async def moved(request):
            raise web.HTTPFound("/recipe")

        async def missing(request):
            raise web.HTTPNotFound()

        async def no_recipe(request):
            return web.Response(text="<html><p>Hi</p></html>", content_type="text/html")

        app = web.Application()
        app.router.add_get("/recipe", recipe)
        app.router.add_get("/moved", moved)
        app.router.add_get("/missing", missing)
        app.router.add_get("/no-recipe", no_recipe)
        return app

    def url(self, path):
        return str(self.server.make_url(path))

    @served
    async def test_scrapes_the_page(self):
        scraper = await aio.scrape_url(self.url("/recipe"))
        self.assertEqual("Töltött káposzta", scraper.title())
        self.assertEqual("https://cdn.example.com/k.mp4", scraper.video())

    @served
    async def test_follows_redirects(self):
        scraper = await aio.scrape_url(self.url("/moved"))
        self.assertEqual(self.url("/recipe"), scraper.url)

    @served
    async def test_http_errors(self):
        with self.assertRaises(aio.FetchError) as caught:
            await aio.scrape_url(self.url("/missing"))
        self.assertEqual(404, caught.exception.status)

    @served
    async def test_network_errors(self):
        url = self.url("/recipe")
        await self.server.close()
        with self.assertRaises(aio.FetchError) as caught:
            await aio.scrape_url(url)
        self.assertIsNone(caught.exception.status)

    @served
    async def test_page_without_a_recipe(self):
        with self.assertRaises(NoSchemaFoundInWildMode):
            await aio.scrape_url(self.url("/no-recipe"))

    @served
    async def test_sends_a_browser_user_agent_unless_the_session_has_one(self):
        await aio.scrape_url(self.url("/recipe"))
        async with aiohttp.ClientSession() as session:
            await aio.scrape_url(self.url("/recipe"), session=session)
        async with aiohttp.ClientSession(headers={"User-Agent": "mealo"}) as session:
            await aio.scrape_url(self.url("/recipe"), session=session)
        await aio.scrape_url(self.url("/recipe"), headers={"User-Agent": "custom"})
        self.assertEqual(
            [aio.DEFAULT_HEADERS["User-Agent"]] * 2 + ["mealo", "custom"],
            self.user_agents,
        )

    @served
    async def test_scrapes_concurrently(self):
        scrapers = await asyncio.gather(
            *(aio.scrape_url(self.url("/recipe")) for _ in range(5))
        )
        self.assertEqual({"Töltött káposzta"}, {s.title() for s in scrapers})

    @served
    async def test_scrape_recipe(self):
        recipe = await aio.scrape_recipe(self.url("/recipe"))
        self.assertEqual("Töltött káposzta", recipe["title"])
        self.assertEqual("https://cdn.example.com/k.mp4", recipe["video"])

    @served
    async def test_scrape_recipe_in_other_processes(self):
        if multiprocessing.current_process().daemon:
            self.skipTest("unittest-parallel's workers can't start processes")
        with concurrent.futures.ProcessPoolExecutor(max_workers=1) as pool:
            recipe = await aio.scrape_recipe(self.url("/recipe"), executor=pool)
            self.assertEqual("Töltött káposzta", recipe["title"])
            with self.assertRaises(NoSchemaFoundInWildMode):
                await aio.scrape_recipe(self.url("/no-recipe"), executor=pool)

    @served
    async def test_scrape_html_and_to_json(self):
        scraper = await aio.scrape_html(
            RECIPE_PAGE.decode("iso-8859-2"), "https://example.com/k"
        )
        recipe = await aio.to_json(scraper)
        self.assertEqual("Töltött káposzta", recipe["title"])
        self.assertEqual(["1 fej káposzta"], recipe["ingredients"])
