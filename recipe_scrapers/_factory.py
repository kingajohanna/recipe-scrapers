from ._abstract import AbstractScraper
from ._utils import get_host_name


class SchemaScraperFactory:
    class SchemaScraper(AbstractScraper):
        def host(self) -> str:  # type: ignore [override]
            return get_host_name(self.url) if self.url is not None else ""

        def title(self):
            return self.schema.title()

        def category(self):
            return self.schema.category()

        def total_time(self):
            return self.schema.total_time()

        def cook_time(self):
            return self.schema.cook_time()

        def prep_time(self):
            return self.schema.prep_time()

        def yields(self):
            return self.schema.yields()

        def image(self):
            return self.schema.image()

        def ingredients(self):
            return self.schema.ingredients()

        def instructions(self):
            return self.schema.instructions()

        def ratings(self):
            return self.schema.ratings()

        def author(self):
            return self.schema.author()

        def cuisine(self):
            return self.schema.cuisine()

        def description(self):
            return self.schema.description()
        
        def calories(self):
            return self.schema.calories()

        def difficulty(self):
            return self.schema.difficulty()
        
        def video(self):
            return self.schema.video()

    @classmethod
    def generate(cls, html, url):
        return cls.SchemaScraper(html=html, url=url)
