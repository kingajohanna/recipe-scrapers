# mypy: disallow_untyped_defs=False
import inspect
from email import header
import imp
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin

import aiohttp
import ssl
import certifi
import asyncio
import logging
from bs4 import BeautifulSoup
from typing import Any

from recipe_scrapers.settings import settings

from ._grouping_utils import IngredientGroup
from ._schemaorg import SchemaOrg

# some sites close their content for 'bots', so user-agent must be supplied
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
}


class AbstractScraper:
    page_data: Union[str, bytes]

    @classmethod
    async def create(cls, url: Union[str, None], options: dict[str, Any]):
        self = cls()
        await self._scrape(url, **options)
        return self

    def __init__(self):
        self.logger = logging.getLogger("AbstractScraper")

    async def _scrape(self, 
        url: Union[str, None],
        proxies: Optional[
            Dict[str, str]
        ] = None,  # allows us to specify optional proxy server
        timeout: Optional[
            Union[float, Tuple[float, float], Tuple[float, None]]
        ] = None,  # allows us to specify optional timeout for request
        wild_mode: Optional[bool] = False,
        html: Union[str, bytes, None] = None,
    ):
        if html:
            self.page_data = html
            self.url = url
        else:
            try:
                assert url is not None, "url required for fetching recipe data"   
                ssl_context = ssl.create_default_context(cafile=certifi.where())
                conn = aiohttp.TCPConnector(ssl=ssl_context)         
                async with aiohttp.ClientSession(connector=conn) as client:
                    async with client.get(url, headers=HEADERS, proxy=proxies, timeout=timeout) as resp:
                        assert resp.status == 200
                        self.url = resp.url
                        self.page_data = await resp.read()
            except AssertionError as ae:
                self.logger.info(f'Invalid URL or unavailable')

        self.wild_mode = wild_mode
        self.soup = BeautifulSoup(self.page_data, "html.parser")
        self.schema = SchemaOrg(self.page_data)

        # attach the plugins as instructed in settings.PLUGINS
        if not hasattr(self.__class__, "plugins_initialized"):
            for name, _ in inspect.getmembers(self, inspect.ismethod):
                current_method = getattr(self.__class__, name)
                for plugin in reversed(settings.PLUGINS):
                    if plugin.should_run(self.host(), name):
                        current_method = plugin.run(current_method)
                setattr(self.__class__, name, current_method)
            setattr(self.__class__, "plugins_initialized", True)

    @classmethod
    def host(cls) -> str:
        """get the host of the url, so we can use the correct scraper"""
        raise NotImplementedError("This should be implemented.")

    def canonical_url(self):
        canonical_link = self.soup.find("link", {"rel": "canonical", "href": True})
        if canonical_link:
            return urljoin(str(self.url), canonical_link["href"])
        return self.url

    def title(self):
        raise NotImplementedError("This should be implemented.")

    def category(self):
        raise NotImplementedError("This should be implemented.")

    def total_time(self):
        """total time it takes to preparate and cook the recipe in minutes"""
        raise NotImplementedError("This should be implemented.")

    def cook_time(self):
        """cook time of the recipe in minutes"""
        raise NotImplementedError("This should be implemented.")

    def prep_time(self):
        """preparation time of the recipe in minutes"""
        raise NotImplementedError("This should be implemented.")

    def yields(self):
        """The number of servings or items in the recipe"""
        raise NotImplementedError("This should be implemented.")

    def image(self):
        raise NotImplementedError("This should be implemented.")

    def nutrients(self):
        raise NotImplementedError("This should be implemented.")

    def language(self):
        """
        Human language the recipe is written in.

        May be overridden by individual scrapers.
        """
        candidate_languages = OrderedDict()
        html = self.soup.find("html", {"lang": True})
        candidate_languages[html.get("lang")] = True

        # Deprecated: check for a meta http-equiv header
        # See: https://www.w3.org/International/questions/qa-http-and-lang
        meta_language = self.soup.find(
            "meta",
            {
                "http-equiv": lambda x: x and x.lower() == "content-language",
                "content": True,
            },
        )
        if meta_language:
            language = meta_language.get("content").split(",", 1)[0]
            if language:
                candidate_languages[language] = True

        # If other langs exist, remove 'en' commonly generated by HTML editors
        if len(candidate_languages) > 1:
            candidate_languages.pop("en", None)

        # Return the first candidate language
        return candidate_languages.popitem(last=False)[0]

    def ingredients(self):
        raise NotImplementedError("This should be implemented.")

    def ingredient_groups(self) -> List[IngredientGroup]:
        return [IngredientGroup(purpose=None, ingredients=self.ingredients())]

    def instructions(self) -> str:
        """instructions to prepare the recipe"""
        raise NotImplementedError("This should be implemented.")

    def instructions_list(self) -> List[str]:
        """instructions to prepare the recipe"""
        return [
            instruction
            for instruction in self.instructions().split("\n")
            if instruction
        ]

    def ratings(self):
        raise NotImplementedError("This should be implemented.")

    def author(self):
        raise NotImplementedError("This should be implemented.")

    def cuisine(self):
        raise NotImplementedError("This should be implemented.")

    def description(self):
        raise NotImplementedError("This should be implemented.")

    def reviews(self):
        raise NotImplementedError("This should be implemented.")

    def equipment(self):
        raise NotImplementedError("This should be implemented.")

    def links(self):
        invalid_href = {"#", ""}
        links_html = self.soup.findAll("a", href=True)

        return [link.attrs for link in links_html if link["href"] not in invalid_href]

    def site_name(self):
        meta = self.soup.find("meta", property="og:site_name")
        return meta.get("content") if meta else None

    def to_json(self):
        json_dict = {}
        public_method_names = [
            method
            for method in dir(self)
            if callable(getattr(self, method))
            if not method.startswith("_") and method not in ["soup", "links", "to_json"]
        ]
        for method in public_method_names:
            try:
                if method == "ingredient_groups":
                    json_dict[method] = [i.__dict__ for i in getattr(self, method)()]
                else:
                    json_dict[method] = getattr(self, method)()
            except Exception:
                pass
        return json_dict
