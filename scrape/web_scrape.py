"""Selenium web scraping module."""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from sys import platform

from bs4 import BeautifulSoup
from fastapi import WebSocket
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.safari.options import Options as SafariOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from webdriver_manager.firefox import GeckoDriverManager

from agent.llm_utils import UsageTracker
from settings import Config
import text_preprocess.text as summary
from text_preprocess.html import extract_hyperlinks, format_hyperlinks


executor = ThreadPoolExecutor()
FILE_DIR = Path(__file__).parent.parent
CFG = Config()


async def async_browse(
    url: str,
    question: str,
    websocket: WebSocket,
    usage_tracker: UsageTracker | None = None,
    raise_on_error: bool = False,
) -> str:
    """Browse one website and return a question-focused source summary.

    Research experiments set ``raise_on_error=True`` so failed scraping is
    represented as a failed source rather than a non-empty error string that
    could accidentally be counted as successful evidence.
    """
    loop = asyncio.get_event_loop()
    local_executor = ThreadPoolExecutor(max_workers=8)
    driver = None

    print(f"Scraping url {url} with question {question}")
    if websocket is not None and hasattr(websocket, "send_json"):
        await websocket.send_json(
            {
                "type": "logs",
                "output": f"🔎 Browsing the {url} for relevant about: {question}...",
            }
        )

    try:
        driver, text = await loop.run_in_executor(
            local_executor, scrape_text_with_selenium, url
        )
        await loop.run_in_executor(local_executor, add_header, driver)
        summary_text = await loop.run_in_executor(
            local_executor,
            summary.summarize_text,
            url,
            text,
            question,
            driver,
            usage_tracker,
        )

        if not summary_text or str(summary_text).startswith("Error:"):
            raise RuntimeError(str(summary_text) or "empty source summary")

        if websocket is not None and hasattr(websocket, "send_json"):
            await websocket.send_json(
                {
                    "type": "logs",
                    "output": f"📝 Information gathered from url {url}: {summary_text}",
                }
            )

        return f"Information gathered from url {url}: {summary_text}"
    except Exception as exc:
        print(f"An error occurred while processing the url {url}: {exc}")
        if raise_on_error:
            raise RuntimeError(f"Failed to browse {url}: {exc}") from exc
        return f"Error processing the url {url}: {exc}"
    finally:
        if driver is not None:
            try:
                await loop.run_in_executor(local_executor, close_browser, driver)
            except Exception:
                pass
        local_executor.shutdown(wait=False)


def browse_website(url: str, question: str) -> tuple[str, WebDriver]:
    """Browse a website and return a summary and its driver."""
    if not url:
        return "A URL was not specified, cancelling request to browse website.", None

    driver, text = scrape_text_with_selenium(url)
    add_header(driver)
    summary_text = summary.summarize_text(url, text, question, driver)
    links = scrape_links_with_selenium(driver, url)
    if len(links) > 5:
        links = links[:5]
    close_browser(driver)
    return f"Answer gathered from website: {summary_text} \n \n Links: {links}", driver


def scrape_text_with_selenium(url: str) -> tuple[WebDriver, str]:
    """Scrape visible textual content from a website using Selenium."""
    logging.getLogger("selenium").setLevel(logging.CRITICAL)

    options_available = {
        "chrome": ChromeOptions,
        "safari": SafariOptions,
        "firefox": FirefoxOptions,
    }
    options = options_available[CFG.selenium_web_browser]()
    options.add_argument(CFG.user_agent)
    options.add_argument("--headless")

    if CFG.selenium_web_browser == "firefox":
        service = FirefoxService(executable_path=GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)
    elif CFG.selenium_web_browser == "safari":
        driver = webdriver.Safari(options=options)
    else:
        if platform == "linux" or platform == "linux2":
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--remote-debugging-port=9222")
        options.add_argument("--no-sandbox")
        options.add_experimental_option("prefs", {"download_restrictions": 3})
        # Selenium Manager resolves a driver compatible with the installed
        # Chrome instead of relying on the repository's old ChromeDriver 119.
        driver = webdriver.Chrome(options=options)

    driver.get(url)
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )

    page_source = driver.execute_script("return document.body.outerHTML;")
    soup = BeautifulSoup(page_source, "html.parser")
    for script in soup(["script", "style"]):
        script.extract()

    text = get_text(soup)
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)
    return driver, text


def get_text(soup):
    """Extract headings and paragraphs from parsed HTML."""
    text = ""
    tags = ["h1", "h2", "h3", "h4", "h5", "p"]
    for element in soup.find_all(tags):
        text += element.text + "\n\n"
    return text


def scrape_links_with_selenium(driver: WebDriver, url: str) -> list[str]:
    """Scrape and normalize links from the current page."""
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, "html.parser")
    for script in soup(["script", "style"]):
        script.extract()
    hyperlinks = extract_hyperlinks(soup, url)
    return format_hyperlinks(hyperlinks)


def close_browser(driver: WebDriver) -> None:
    """Close a webdriver instance."""
    driver.quit()


def add_header(driver: WebDriver) -> None:
    """Add the existing in-browser overlay used by the application."""
    driver.execute_script(open(f"{FILE_DIR}/js/overlay.js", "r").read())
