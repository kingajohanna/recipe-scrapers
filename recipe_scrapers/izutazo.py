import re

from ._abstract import AbstractScraper
from ._exceptions import ElementNotFoundInHtml, StaticValueException
from ._grouping_utils import IngredientGroup, group_ingredients
from ._utils import get_yields, normalize_string

# The recipe cards come from the WP Delicious Recipes plugin. Its schema.org data has
# no yield, the ingredients lack their notes ("(sárga színű)") and groups, and the
# author is the WordPress user "admin", so these are read from the card instead.
_INGREDIENTS = ".dr-ingredients-list li.recipe-ingredient"
_MAIN_HEADING = ".dr-ingredients-list h2.dr-title"
_GROUP_HEADINGS = ".dr-ingredients-list .recipe-ingredients h3, .dr-ingredients-list .recipe-ingredients h4"

# "Hozzávalók (4 adaghoz):" ("Ingredients for 4 portions:") or, for pieces,
# "(12-15 darabhoz)", "(kb. 6 db-hoz)" or "(10-12 db mini tortillához)"
_SERVINGS = re.compile(r"(\d+(?:\s*[-–]\s*\d+)?)\s*(?:személy|adag|fő)", re.IGNORECASE)
_PIECES = re.compile(r"(\d+(?:\s*[-–]\s*\d+)?)\s*(?:db\b|darab)", re.IGNORECASE)


class Izutazo(AbstractScraper):
    @classmethod
    def host(cls):
        return "izutazo.hu"

    def site_name(self):
        raise StaticValueException(return_value="Ízutazó")

    def author(self):
        raise StaticValueException(return_value="Ízutazó")

    def ingredients(self):
        ingredients = [
            normalize_string(item.get_text()) for item in self.soup.select(_INGREDIENTS)
        ]
        return ingredients or self.schema.ingredients()

    def ingredient_groups(self):
        groups = group_ingredients(
            self.ingredients(), self.soup, _GROUP_HEADINGS, _INGREDIENTS
        )
        if len(groups) < 2:
            return [IngredientGroup(self.ingredients())]
        return [
            IngredientGroup(
                ingredients=group.ingredients,
                purpose=group.purpose.rstrip(":").strip() if group.purpose else None,
            )
            for group in groups
        ]

    def yields(self):
        # A recipe in parts has no count in its main heading, only in its groups'
        headings = self.soup.select(f"{_MAIN_HEADING}, {_GROUP_HEADINGS}")
        for heading in headings:
            text = heading.get_text()
            servings = _SERVINGS.search(text)
            if servings:
                return get_yields(f"{servings.group(1)} servings")
            pieces = _PIECES.search(text)
            if pieces:
                return get_yields(f"{pieces.group(1)} items")
        raise ElementNotFoundInHtml("yields")

    def category(self):
        # The site's categories ("Levesek, főzelékek") are in cookingMethod
        methods = self.schema.data.get("cookingMethod")
        if isinstance(methods, list):
            methods = ", ".join(method for method in methods if method)
        if not methods:
            raise ElementNotFoundInHtml("category")
        return normalize_string(methods)
