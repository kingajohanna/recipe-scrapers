import re
from typing import NamedTuple

from bs4 import Comment, NavigableString

from ._abstract import AbstractScraper
from ._exceptions import ElementNotFoundInHtml, StaticValueException
from ._grouping_utils import IngredientGroup
from ._utils import get_yields, normalize_string

# The posts have no schema.org recipe: they're free-form WordPress content. Since 2017
# the ingredients are in boxes of this class, and the steps follow them. Older posts
# only head their ingredients with "Hozzávalók" ("Ingredients").
_INGREDIENTS_BOX = "lilafuge-recept-hozzavalok"

# Elements that start a new line, as the browser shows them; anything else is inline
_BLOCKS = {
    "blockquote",
    "div",
    "figure",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "ol",
    "p",
    "pre",
    "table",
    "tr",
    "ul",
}
_SKIP = {"figcaption", "iframe", "noscript", "script", "style"}

# "Hozzávalók 4 személynek:" ("Ingredients for 4 people:") heads the ingredients. It
# can give a dish size instead ("Hozzávalók 24 cm-es piteformához:", for a 24 cm pie
# dish), so only people, portions or pieces count as the yield.
_INGREDIENTS_HEADING = re.compile(r"^hozzávalók\b\s*(?P<rest>.*?)\s*:?$", re.IGNORECASE)
_SERVINGS = re.compile(r"(\d+(?:\s*[-–]\s*\d+)?)\s*(?:személy|adag|fő)", re.IGNORECASE)
_PIECES = re.compile(r"(\d+(?:\s*[-–]\s*\d+)?)\s*(?:db|darab)\b", re.IGNORECASE)
# "Hozzávalók a joghurt fagylalthoz:" ("Ingredients for the frozen yoghurt:") heads a
# group of a recipe in parts
_FOR_THE = re.compile(r"^az?\s", re.IGNORECASE)
# A group heading, such as "A tésztához:" ("For the dough:")
_GROUP_HEADING = re.compile(r"^(?P<purpose>[^:]{1,60}):$")
# A one-ingredient group on one line: "Az összeállításhoz: kb. 6 evőkanál kakaópor"
# ("For assembling: ..."). Only "for ..." words (-hoz/-hez/-höz) count, so that
# "opcionális: brandy vagy whisky" stays an ingredient.
_INLINE_GROUP = re.compile(
    r"^(?P<purpose>[^:]{1,40}(?:hoz|hez|höz))\s*:\s*(?P<ingredient>\S.*)$",
    re.IGNORECASE,
)
# "Eszköz:" ("Tools:") lists equipment, not ingredients
_EQUIPMENT_HEADING = re.compile(r"^eszköz(?:ök)?$", re.IGNORECASE)
# "Elkészítés:" ("Method:") heads the steps
_STEPS_HEADING = re.compile(r"^elkészítés\s*:?$", re.IGNORECASE)
# Some posts number their steps ("1. A vizet a sóval felforraljuk")
_STEP_NUMBER = re.compile(r"^\d{1,2}[.)]\s+")
# After the steps: tips ("Tipp:"), the sponsor ("A receptet az Alpro támogatta.") or
# where the recipe was published ("A recept megtalálható a Lila füge Magazin ...")
_STEPS_END = re.compile(
    r"^(?:(?:pro\s+)?tipp\b|a recept(?:et)?\b.*\b(?:támogatta|megtalálható))",
    re.IGNORECASE,
)
_SENTENCE_END = (".", "!", "?")


class LilaFuge(AbstractScraper):
    @classmethod
    def host(cls):
        return "lilafuge.hu"

    def site_name(self):
        raise StaticValueException(return_value="Lila füge")

    def title(self):
        # Recipe posts use one template, video posts another
        h1 = self.soup.select_one("h1.lilafuge_post_page__title, h1.entry-title")
        if not h1:
            raise ElementNotFoundInHtml("title")
        return normalize_string(h1.get_text())

    def author(self):
        author = self.soup.select_one(
            "a.lilafuge_post_page__author, .author-box-wrap .td-author-name a"
        )
        if not author:
            raise ElementNotFoundInHtml("author")
        return normalize_string(author.get_text())

    def description(self):
        subtitle = self.soup.select_one(
            ".lilafuge_post_page__subtitle, .td-post-sub-title"
        )
        description = normalize_string(subtitle.get_text()) if subtitle else ""
        if not description:
            raise ElementNotFoundInHtml("description")
        return description

    def image(self):
        return self.opengraph.image()

    def keywords(self):
        # The class name is misspelled on the site ("lilaguge"). Video posts show no tags.
        tags = [
            normalize_string(link.get_text())
            for link in self.soup.select(".lilaguge_post_page__tags a")
        ]
        if not tags:
            raise ElementNotFoundInHtml("keywords")
        return tags

    def yields(self):
        heading = self._recipe().heading
        if heading:
            servings = _SERVINGS.search(heading)
            if servings:
                return get_yields(f"{servings.group(1)} servings")
            pieces = _PIECES.search(heading)
            if pieces:
                return get_yields(f"{pieces.group(1)} items")
        raise ElementNotFoundInHtml("yields")

    def ingredients(self):
        return [
            ingredient
            for group in self.ingredient_groups()
            for ingredient in group.ingredients
        ]

    def ingredient_groups(self):
        groups = self._recipe().groups()
        if not groups:
            raise ElementNotFoundInHtml("ingredients")
        return groups

    def equipment(self):
        equipment = self._recipe().equipment
        if not equipment:
            raise ElementNotFoundInHtml("equipment")
        return equipment

    def instructions(self):
        steps = self._recipe().steps
        if not steps:
            raise ElementNotFoundInHtml("instructions")
        return "\n".join(steps)

    def _recipe(self):
        """The post's ingredients and steps, read once per page."""
        if not hasattr(self, "_read"):
            self._read = _Reader()
            content = self.soup.select_one(
                ".lilafuge_post_page__content, .td-post-content"
            )
            for line in _lines(content) if content else []:
                self._read.read(line)
        return self._read


class _Line(NamedTuple):
    text: str
    in_box: bool  # inside an ingredients box
    after_br: bool  # follows a <br>, not the start of a block


class _Reader:
    """Reads a post's lines, in order, into its ingredients and steps.

    Before the first ingredients heading or box is the intro, which is skipped. Lines
    in a box are ingredients, and the lines after a box are steps. Without a box,
    ingredients follow a "Hozzávalók" heading until "Elkészítés" or a full sentence.
    The steps end at a tip or at the recipe's source. A recipe in parts can start
    another box or "Hozzávalók a ...hoz:" heading among the steps.
    """

    def __init__(self):
        self.heading = None  # the first "Hozzávalók ..." heading, for the yield
        self.equipment = []
        self.steps = []
        self._groups = []
        self._state = "intro"  # then "ingredients", "steps", and "end"
        self._in_box = False
        self._in_equipment = False
        self._after_heading = False

    def groups(self):
        groups = [group for group in self._groups if group.ingredients]
        if len(groups) == 1:
            groups[0].purpose = None
        return groups

    def read(self, line):
        after_heading, self._after_heading = self._after_heading, False
        heading = _INGREDIENTS_HEADING.match(line.text)
        if heading and (len(line.text) > 80 or line.text.endswith(_SENTENCE_END)):
            heading = None  # a sentence that starts with the word, not a heading

        if line.in_box or (heading and self._state != "end"):
            self._state, self._in_box = "ingredients", line.in_box
            if heading:
                self._start_ingredients(heading)
            else:
                self._ingredient(line.text)
            return

        if self._state == "ingredients":
            if self._in_box or _STEPS_HEADING.match(line.text):
                self._state = "steps"
            elif line.text.endswith(_SENTENCE_END):
                self._state = "steps"
            elif after_heading and line.text.startswith("("):
                # "Hozzávalók:" then "(kb. 50 db-hoz)" ("for about 50 pieces")
                self.heading = f"{self.heading} {line.text}"
                return
            else:
                self._ingredient(line.text)
                return

        if self._state == "steps":
            if _STEPS_HEADING.match(line.text):
                return
            if _STEPS_END.match(line.text):
                self._state = "end"
                return
            self._step(line)

    def _start_ingredients(self, heading):
        self._in_equipment = False
        rest = heading.group("rest")
        if _FOR_THE.match(rest):
            self._groups.append(
                IngredientGroup(ingredients=[], purpose=rest[0].upper() + rest[1:])
            )
        if self.heading is None:
            self.heading = heading.group(0)
            self._after_heading = True

    def _ingredient(self, text):
        group_heading = _GROUP_HEADING.match(text)
        if group_heading:
            purpose = group_heading.group("purpose").strip()
            self._in_equipment = bool(_EQUIPMENT_HEADING.match(purpose))
            if not self._in_equipment:
                self._groups.append(IngredientGroup(ingredients=[], purpose=purpose))
            return
        # Some lists end their lines with commas
        text = text.rstrip(",;").strip()
        inline_group = _INLINE_GROUP.match(text)
        if inline_group:
            self._in_equipment = False
            purpose = inline_group.group("purpose").strip()
            self._groups.append(IngredientGroup(ingredients=[], purpose=purpose))
            text = inline_group.group("ingredient")
        if self._in_equipment:
            self.equipment.append(text)
            return
        if not self._groups:
            self._groups.append(IngredientGroup(ingredients=[], purpose=None))
        self._groups[-1].ingredients.append(text)

    def _step(self, line):
        text = _STEP_NUMBER.sub("", line.text)
        last = self.steps[-1] if self.steps else None
        # A heading such as "A szeletek összeállítása:" ("Assembling the bars:") goes
        # with its step. A <br> only wraps a sentence unless the sentence ended, and a
        # few posts break a sentence across two <p>s.
        if last and (
            last.endswith(":")
            or (
                not last.endswith(_SENTENCE_END)
                and (line.after_br or text[:1].islower())
            )
        ):
            self.steps[-1] = f"{last} {text}"
        else:
            self.steps.append(text)


def _lines(element):
    """The element's text as lines, as the browser shows them.

    Lines break at <br>s and block elements; the posts mix <p>s, <div>s and <br>s
    freely, and the steps often aren't siblings of the box. In a box, a bold text
    ending in ":" ("A tésztához:") ends its line too, as an ingredient may follow it.
    """
    lines, words = [], []
    after_br = False

    def end_line(in_box, by_br=False):
        nonlocal after_br
        text = normalize_string("".join(words))
        words.clear()
        if text:
            lines.append(_Line(text, in_box, after_br))
        if text or not by_br:
            after_br = by_br

    def walk(node, in_box):
        for child in node.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                words.append(str(child))
                continue
            if child.name in _SKIP:
                continue
            if child.name == "br":
                end_line(in_box, by_br=True)
                continue
            inside = in_box or _INGREDIENTS_BOX in (child.get("class") or [])
            if child.name in _BLOCKS:
                end_line(in_box)
                walk(child, inside)
                end_line(inside)
            elif (
                inside
                and child.name in ("b", "strong")
                and child.get_text(strip=True).endswith(":")
            ):
                # The heading may start in an earlier bold ("Hozzávalók (", "30 db):")
                walk(child, inside)
                end_line(inside)
            else:
                walk(child, inside)

    walk(element, False)
    return lines
