from ._abstract import AbstractScraper
from ._utils import normalize_string


class Mindmegette(AbstractScraper):
    @classmethod
    def host(cls):
        return "mindmegette.hu"

    def title(self):
        # The schema.org name carries an SEO suffix ("... | Mindmegette.hu")
        h1 = self.soup.find("h1")
        if h1:
            return normalize_string(h1.get_text())
        return self.schema.title().removesuffix(" | Mindmegette.hu")

    def instructions(self):
        # Each HowToStep is named "1. lépés" (step 1), which isn't an instruction
        steps = self.schema.data.get("recipeInstructions") or []
        return "\n".join(
            normalize_string(step.get("text", ""))
            for step in steps
            if isinstance(step, dict) and step.get("text")
        )
