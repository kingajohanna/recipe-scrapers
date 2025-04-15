from ._abstract import AbstractScraper
from ._grouping_utils import IngredientGroup, group_ingredients
from ._utils import get_minutes, get_yields, normalize_string
import re


class StreetKitchen(AbstractScraper):
    @classmethod
    def host(cls):
        return "streetkitchen.hu"

    def title(self):
        return self.soup.find("h1", {"class": "entry-title"}).text

    def total_time(self):
        items = self.soup.select(".the-content-div li")
        total_time = 0
        for item in items:
            total_time += get_minutes(item.text) or 0
        return total_time or None

    def image(self):
        return (
            self.soup.find("div", {"class": "article-featured-image-bg"})
            .find("noscript")
            .find("img")["src"]
        )

    def ingredients(self):
        ingredients_raw = self.soup.find("div", class_="ingredients-main").findAll("dd")
        ingredients = []
        for ingredient in ingredients_raw:
            ingredients.append(normalize_string(ingredient.text))
        # ingredient_groups = self.soup.findAll("div", {"class": "ingredient-group"})
        # ingredients = []
        # # There are separate sets of ingredients for desktop and mobile view
        # for ingredient_group_raw in ingredient_groups:
        #     ingredient_group = ingredient_group_raw.findAll("dd")
        #     for ingredient in ingredient_group:
        #         ingredients.append(normalize_string(ingredient.get_text()).strip())
        # ingredients = list(set(ingredients))
        return ingredients

    def instructions(self):
        def is_valid_paragraph(tag):
            return 'Ha tetszett' not in tag.text and not tag.find('a')

        content_div = self.soup.find("div", {"class": "the-content-div"})
        content_p = content_div.find_all("p", recursive=False)
        instructions = [p for p in content_p if is_valid_paragraph(p)]

        instructions_arr = []
        for instruction in instructions:
            text = instruction.text
            # From the point we encounter "If you liked..." it's just ads.
            if text.startswith("Ha tetszett a"):
                break
            instructions_arr.append(normalize_string(text))

        return "\n".join(instructions_arr)

    def yields(self):
        return get_yields(self.soup.find("span", {"class": "quantity-number"}).text)

    def category(self):
        return self.soup.find("div", {"class": "entry-category"}).find("a").text

    def description(self):
        return normalize_string(self.soup.find("div", {"class": "entry-lead"}).text)

    def author(self):
        return normalize_string(
            self.soup.find("a", {"rel": "author"}).find("img")["alt"]
        )

    def ingredient_groups(self) -> list[IngredientGroup]:
        return group_ingredients(
            self.ingredients(),
            self.soup,
            ".ingredients-main div.ingredient-group h3",
            ".ingredients-main div.ingredient-group dd",
        )

    def prep_time(self):
        items = self.soup.find("div", {"class": "the-content-div"}).find_all("li")

        for item in items:
            text = normalize_string(item.get_text())
            if "Elkészítési idő" in text:
                return get_minutes(text)

    def cook_time(self):
        items = self.soup.find("div", {"class": "the-content-div"}).find_all("li")

        for item in items:
            text = normalize_string(item.get_text())
            if "Sütési idő" in text:
                return get_minutes(text)
        return 0

    def keywords(self):
        items = self.soup.find("ul", {"class": "tags-list"}).find_all("li")
        return [item.text for item in items]
    
    def calories(self):
        return self.schema.calories()

    def difficulty(self):
        return self.schema.difficulty()
    
    def video(self):
        iframe_tags = self.soup.find_all('iframe', {'frameborder': '0'})
        video = None
        for iframe in iframe_tags:
            if 'youtube' in iframe.get('src'):
                print(iframe.get('src'))
                video = iframe.get('src')
        return video
