# mypy: disallow_untyped_defs=False
from ._abstract import AbstractScraper
from ._utils import get_yields, normalize_string, get_minutes
import re


class StreetKitchen(AbstractScraper):
    @classmethod
    def host(cls):
        return "streetkitchen.hu"

    def title(self):
        return self.soup.find("h1", {"class": "entry-title"}).get_text()

    def total_time(self):
        try:
            time = self.soup.find(["li", "p"], text=re.compile('Elkészítési idő:.*|Elkészítés.*:.*')).get_text()
            return get_minutes(time)
        except AttributeError:
            pass

    def image(self):
        return (
            self.soup.find("div", {"class": "article-featured-image-bg"})
            .find("noscript")
            .find("img")["src"]
        )

    def ingredients(self):
        ingredient_groups = self.soup.findAll("div", {"class": "ingredient-group"})
        ingredients = []
        # There are separate sets of ingredients for desktop and mobile view
        for ingredient_group_raw in ingredient_groups:
            ingredient_group = ingredient_group_raw.findAll("dd")
            for ingredient in ingredient_group:
                ingredients.append(normalize_string(ingredient.get_text()).strip())
        ingredients = list(set(ingredients))
        return ingredients

    def instructions(self):
        def is_valid_paragraph(tag):
            return 'Ha tetszett' not in tag.text and not tag.find('a')

        content_div = self.soup.find("div", {"class": "the-content-div"})
        content_p = content_div.find_all("p", recursive=False)
        instructions = [p for p in content_p if is_valid_paragraph(p)]

        instructions_arr = []
        for instruction in instructions:
            text = instruction.get_text()
            # From the point we encounter "If you liked..." it's just ads.
            if text.startswith("Ha tetszett a"):
                break
            instructions_arr.append(normalize_string(text))

        return "\n".join(instructions_arr)

    def yields(self):
        return get_yields(
            self.soup.find("span", {"class": "quantity-number"}).get_text()
        )

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