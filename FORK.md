# mealo fork of recipe-scrapers

This fork of [hhursev/recipe-scrapers](https://github.com/hhursev/recipe-scrapers)
backs mealo's scraper service (`mealo/scraper/scraper_service`). It adds:

- **An async API**, `recipe_scrapers.aio`. It fetches pages with aiohttp and
  parses them off the event loop. Install it with `pip install "recipe-scrapers[async]"`.
- **More fields on every scraper:** `video()`, `videos()`, `calories()`,
  `difficulty()` and `reviews()`. They also appear in `to_json()`.
- **Fixes for Hungarian sites:** streetkitchen.hu (clean titles, no related-recipe
  links in the instructions) and mindmegette.hu (rewritten for the redesigned site).

## Using it from asyncio

```python
from recipe_scrapers import aio

recipe = await aio.scrape_recipe(url, session=session)  # dict, as to_json() gives it
```

- **Errors:** `aio.FetchError` means the page couldn't be loaded, which is worth
  retrying later. Its `.status` is the HTTP status, or `None` for a network error.
  Any other exception means the page has no recipe that could be scraped.
- **Unsupported sites:** they are read from their schema.org data, unless you pass
  `supported_only=True`.
- **Process pool:** parsing takes 40–110 ms of CPU per page. By default it runs on
  a thread, which still competes with the event loop for the GIL. For heavy load,
  create a `concurrent.futures.ProcessPoolExecutor` once (in the app's lifespan)
  and pass it as `executor=`.

## Videos

`video()` returns one URL to play, or `None`, picked in this order:

1. A YouTube watch URL.
2. A media file (`.mp4`, `.m3u8`, ...).
3. The site's embed page, such as a Vimeo or JW Player iframe. Apps can't play
   these directly; they need a WebView.

It looks at the recipe's schema.org video first, then other VideoObjects on the
page and `og:video`, then iframes and `<video>` tags. `videos()` lists every
video found, with its thumbnail, name, duration in seconds and upload date.

## Syncing with upstream

```sh
git remote add upstream https://github.com/hhursev/recipe-scrapers.git  # once
git fetch upstream
git merge upstream/main
python -m unittest_parallel --level test
```

Upstream history is merged in (last at e7892149, October 2026), so this is a
normal merge. Conflicts can only come from the files the fork changes.
`git diff upstream/main -- recipe_scrapers tests pyproject.toml` lists them.
