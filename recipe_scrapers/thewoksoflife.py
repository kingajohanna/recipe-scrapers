# mypy: disallow_untyped_defs=False
from ._abstract import AbstractScraper


class Thewoksoflife(AbstractScraper):
    @classmethod
    def host(cls):
        return "thewoksoflife.com"

    def title(self):
        return self.schema.title()

    def description(self):
        return self.schema.description()

    def total_time(self):
        return self.schema.total_time()

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
