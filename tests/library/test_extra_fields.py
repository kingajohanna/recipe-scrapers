import json
import pathlib
import unittest

from recipe_scrapers import scrape_html
from recipe_scrapers._exceptions import RecipeScrapersExceptions


def scrape(recipe=None, graph=(), head="", body=""):
    """A page with a schema.org Recipe (plus other @graph nodes) and the given HTML."""
    recipe = {"@type": "Recipe", "name": "Soup", **(recipe or {})}
    data = {"@context": "https://schema.org", "@graph": [recipe, *graph]}
    html = (
        f'<html><head><script type="application/ld+json">{json.dumps(data)}</script>'
        f"{head}</head><body>{body}</body></html>"
    )
    return scrape_html(html, org_url="https://example.com/soup", supported_only=False)


class TestVideo(unittest.TestCase):
    def test_prefers_a_media_file_over_an_embed_page(self):
        scraper = scrape(
            {
                "video": {
                    "@type": "VideoObject",
                    "embedUrl": "https://player.example.com/v/1",
                    "contentUrl": "https://cdn.example.com/v/1.mp4",
                }
            }
        )
        self.assertEqual("https://cdn.example.com/v/1.mp4", scraper.video())

    def test_youtube_urls_become_watch_urls(self):
        scraper = scrape(
            {
                "video": {
                    "@type": "VideoObject",
                    "embedUrl": "https://www.youtube-nocookie.com/embed/ytQ4UfQ-yOw?rel=0",
                }
            }
        )
        self.assertEqual("https://www.youtube.com/watch?v=ytQ4UfQ-yOw", scraper.video())

    def test_resolves_references_to_other_nodes(self):
        scraper = scrape(
            {"video": {"@id": "#video"}},
            graph=[
                {
                    "@type": "VideoObject",
                    "@id": "#video",
                    "contentUrl": "https://cdn.example.com/v/2.m3u8",
                }
            ],
        )
        self.assertEqual("https://cdn.example.com/v/2.m3u8", scraper.video())

    def test_accepts_lists_and_plain_urls(self):
        scraper = scrape(
            {"video": ["https://cdn.example.com/a.mp4", "https://youtu.be/ytQ4UfQ-yOw"]}
        )
        self.assertEqual("https://cdn.example.com/a.mp4", scraper.video())
        self.assertEqual(2, len(scraper.videos()))

    def test_the_recipes_own_video_beats_others_on_the_page(self):
        scraper = scrape(
            {
                "video": {
                    "@type": "VideoObject",
                    "embedUrl": "https://player.vimeo.com/video/1",
                }
            },
            graph=[
                {
                    "@type": "VideoObject",
                    "contentUrl": "https://cdn.example.com/other.mp4",
                }
            ],
        )
        self.assertEqual("https://player.vimeo.com/video/1", scraper.video())
        self.assertEqual(
            ["https://player.vimeo.com/video/1", "https://cdn.example.com/other.mp4"],
            [video["url"] for video in scraper.videos()],
        )

    def test_falls_back_to_opengraph(self):
        scraper = scrape(
            head='<meta property="og:video" content="https://cdn.example.com/og.mp4">'
        )
        self.assertEqual("https://cdn.example.com/og.mp4", scraper.video())

    def test_falls_back_to_embedded_players(self):
        scraper = scrape(
            body='<iframe data-lazy-src="//www.youtube.com/embed/ytQ4UfQ-yOw"></iframe>'
            '<video poster="/poster.jpg"><source src="/clip.mp4"></video>'
            '<lite-youtube videoid="abcdefghijk"></lite-youtube>'
        )
        self.assertEqual("https://www.youtube.com/watch?v=ytQ4UfQ-yOw", scraper.video())
        self.assertEqual(
            [
                "https://www.youtube.com/watch?v=ytQ4UfQ-yOw",
                "https://www.youtube.com/watch?v=abcdefghijk",
                "https://example.com/clip.mp4",
            ],
            [video["url"] for video in scraper.videos()],
        )
        self.assertEqual(
            "https://example.com/poster.jpg", scraper.videos()[2]["thumbnail_url"]
        )

    def test_the_same_video_is_listed_once(self):
        scraper = scrape(
            {
                "video": {
                    "@type": "VideoObject",
                    "embedUrl": "https://www.youtube.com/embed/ytQ4UfQ-yOw",
                }
            },
            body='<iframe src="https://www.youtube.com/embed/ytQ4UfQ-yOw?autoplay=1"></iframe>',
        )
        self.assertEqual(1, len(scraper.videos()))

    def test_describes_each_video(self):
        scraper = scrape(
            {
                "video": {
                    "@type": "VideoObject",
                    "name": "How to make soup",
                    "contentUrl": "https://cdn.example.com/soup.mp4",
                    "thumbnailUrl": ["https://cdn.example.com/soup.jpg"],
                    "duration": "PT1M30S",
                    "uploadDate": "2024-01-02",
                }
            }
        )
        self.assertEqual(
            [
                {
                    "url": "https://cdn.example.com/soup.mp4",
                    "content_url": "https://cdn.example.com/soup.mp4",
                    "embed_url": None,
                    "thumbnail_url": "https://cdn.example.com/soup.jpg",
                    "name": "How to make soup",
                    "duration": 90,
                    "upload_date": "2024-01-02",
                }
            ],
            scraper.videos(),
        )

    def test_ignores_placeholders_and_stray_quotes(self):
        scraper = scrape(
            {
                "video": [
                    {"@type": "VideoObject", "contentUrl": "https://example.com/"},
                    {
                        "@type": "VideoObject",
                        "contentUrl": "https://cdn.example.com/&rdquo;abc&rdquo;.mp4",
                    },
                ]
            }
        )
        self.assertEqual(
            ["https://cdn.example.com/abc.mp4"], [v["url"] for v in scraper.videos()]
        )

    def test_none_without_a_video(self):
        scraper = scrape()
        self.assertIsNone(scraper.video())
        self.assertEqual([], scraper.videos())


class TestOtherFields(unittest.TestCase):
    def test_calories(self):
        scraper = scrape(
            {"nutrition": {"@type": "NutritionInformation", "calories": "250 kcal"}}
        )
        self.assertEqual("250 kcal", scraper.calories())
        with self.assertRaises(RecipeScrapersExceptions):
            scrape().calories()

    def test_difficulty(self):
        self.assertEqual("Easy", scrape({"difficulty": "Easy"}).difficulty())
        with self.assertRaises(RecipeScrapersExceptions):
            scrape().difficulty()

    def test_reviews(self):
        scraper = scrape(
            {
                "review": [
                    {
                        "@type": "Review",
                        "author": {"@type": "Person", "name": "Ann"},
                        "reviewRating": {"@type": "Rating", "ratingValue": 5},
                        "reviewBody": "Lovely &amp; easy",
                        "datePublished": "2024-01-02",
                    },
                    {"@type": "Review", "author": "Bob"},
                ]
            }
        )
        self.assertEqual(
            [
                {
                    "author": "Ann",
                    "rating": "5",
                    "body": "Lovely & easy",
                    "date": "2024-01-02",
                }
            ],
            scraper.reviews(),
        )

    def test_in_to_json(self):
        scraper = scrape(
            {
                "video": "https://youtu.be/ytQ4UfQ-yOw",
                "nutrition": {"calories": "250 kcal"},
                "review": {"reviewBody": "Nice"},
            }
        )
        recipe = scraper.to_json()
        self.assertEqual("https://www.youtube.com/watch?v=ytQ4UfQ-yOw", recipe["video"])
        self.assertEqual(1, len(recipe["videos"]))
        self.assertEqual("250 kcal", recipe["calories"])
        self.assertEqual([{"body": "Nice"}], recipe["reviews"])

    def test_site_specific_scraper(self):
        html = pathlib.Path(
            "tests/test_data/mindmegette.hu/mindmegette.testhtml"
        ).read_text(encoding="utf-8")
        scraper = scrape_html(
            html,
            org_url="https://www.mindmegette.hu/recept/almas-pite-a-hagyomanyos-recept",
        )
        self.assertEqual("https://www.youtube.com/watch?v=ytQ4UfQ-yOw", scraper.video())
        self.assertEqual("405.7 kcal", scraper.calories())
        self.assertEqual("Mester", scraper.difficulty())
