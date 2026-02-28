from ._abstract import AbstractScraper
from ._grouping_utils import IngredientGroup


class StreetKitchen(AbstractScraper):
    @classmethod
    def host(cls):
        return "streetkitchen.hu"

    def title(self):
        h1 = (
            self.soup.select_one("h1.flex.flex-wrap")
            or self.soup.find("h1", {"class": "entry-title"})
            or self.soup.find("h1")
        )
        if not h1:
            return ""
        spans = h1.select("span.splitted-text")
        if spans:
            return " ".join(s.get_text(strip=True) for s in spans if s.get_text(strip=True))
        return h1.get_text(" ", strip=True)

    def ingredients(self):
        ingredients_list = []
        for item in self.soup.select(
            "div.w-full.rounded-b-md div.my-2.flex.items-center.gap-2.text-lg"
        ):
            inner = item.select_one("div.flex.items-center.gap-2")
            if not inner:
                continue
            # Quantity in first div, name in div.font-bold
            divs = inner.find_all("div", recursive=False)
            parts = []
            for div in divs:
                text = div.get_text(" ", strip=True)
                if text:
                    parts.append(text)
            if parts:
                text = " ".join(parts)
                text = text.replace("( ", "(").replace(" )", ")")
                ingredients_list.append(text)
        return ingredients_list

    def ingredient_groups(self):
        groups = []
        for group_block in self.soup.select("div.w-full.rounded-b-md > div > div"):
            heading_tag = group_block.select_one("h5.text-lg.font-bold")
            purpose = heading_tag.get_text(strip=True) if heading_tag else None

            if purpose == "":
                return [IngredientGroup(ingredients=self.ingredients())]

            ingredients = []
            for item in group_block.select("div.my-2.flex.items-center.gap-2.text-lg"):
                inner = item.select_one("div.flex.items-center.gap-2")
                if not inner:
                    continue
                divs = inner.find_all("div", recursive=False)
                parts = []
                for div in divs:
                    text = div.get_text(" ", strip=True)
                    if text:
                        parts.append(text)
                if parts:
                    text = " ".join(parts)
                    text = text.replace("( ", "(").replace(" )", ")")
                    ingredients.append(text)

            if ingredients:
                groups.append(IngredientGroup(ingredients=ingredients, purpose=purpose))

        if not groups:
            return [IngredientGroup(ingredients=self.ingredients())]
        return groups

    def instructions(self):
        container = (
            self.soup.select_one("article#Streetk_content_description_wrapper")
            or self.soup.select_one("article.recipe-article")
            or self.soup.select_one("div.recipe-article")
        )
        if not container:
            return ""

        instructions = []

        # Ordered list format: ol > li > div.list-content-wrapper > p
        ol = container.select_one("ol.list-decimal, ol")
        if ol:
            for li in ol.find_all("li", recursive=False):
                p = li.select_one(".list-content-wrapper p, p")
                text = (p or li).get_text(" ", strip=True).replace("\xa0", " ")
                if text:
                    instructions.append(text)
            if instructions:
                return "\n".join(instructions)

        # Paragraph format: article > p (figures skipped)
        for p in container.select("p"):
            text = p.get_text(" ", strip=True).replace("\xa0", " ")
            if text:
                instructions.append(text)
        return "\n".join(instructions)
