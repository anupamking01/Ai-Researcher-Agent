"""Fail-fast preflight for the live research pilot.

This script intentionally makes no OpenAI API calls. It verifies the two
external runtime layers that previously caused invalid green workflow runs:
metasearch availability and concurrent Selenium/Chrome page extraction.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scrape.web_scrape import add_header, close_browser, scrape_text_with_selenium
from scrape.web_search import web_search


SEARCH_QUERY = "Python 3.14 official documentation"
BROWSER_URLS = (
    "https://example.com/",
    "https://example.org/",
)
MIN_TEXT_WORDS = 4


def _check_search() -> None:
    raw = web_search(SEARCH_QUERY, num_results=3)
    results = json.loads(raw)
    urls = [
        item.get("href")
        for item in results
        if isinstance(item, dict) and item.get("href")
    ]
    if not urls:
        raise RuntimeError("Metasearch preflight returned no usable URLs")
    print(f"PRECHECK search=ok results={len(urls)} first={urls[0]}", flush=True)


def _browse_one(url: str) -> tuple[str, int]:
    driver = None
    try:
        driver, text = scrape_text_with_selenium(url)
        # The overlay is optional in research mode. Calling add_header here
        # explicitly protects against regressions where a missing legacy
        # js/overlay.js file would again invalidate otherwise-good browsing.
        add_header(driver)
        word_count = len((text or "").split())
        if word_count < MIN_TEXT_WORDS:
            raise RuntimeError(
                f"Browser preflight extracted only {word_count} words from {url}"
            )
        return url, word_count
    finally:
        if driver is not None:
            close_browser(driver)


def _check_browser_concurrency() -> None:
    failures = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_browse_one, url): url for url in BROWSER_URLS}
        for future in as_completed(futures):
            url = futures[future]
            try:
                checked_url, words = future.result()
                print(
                    f"PRECHECK browser=ok url={checked_url} words={words}",
                    flush=True,
                )
            except Exception as exc:
                failures.append(f"{url}: {type(exc).__name__}: {exc}")

    if failures:
        raise RuntimeError(
            "Concurrent browser preflight failed: " + " | ".join(failures)
        )


def main() -> int:
    print("Starting live-pilot preflight with zero model/API calls.", flush=True)
    _check_search()
    _check_browser_concurrency()
    print("PRECHECK RESULT: PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
