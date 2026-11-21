"""Text processing functions"""
import urllib
from typing import Dict, Generator, Optional

from selenium.webdriver.remote.webdriver import WebDriver

from settings import Config
from agent.llm_utils import UsageTracker, create_chat_completion
import os
from md2pdf.core import md2pdf

CFG = Config()

# Fixed source-condensation guardrails for the research pipeline. A webpage can
# contain hundreds of thousands of characters; the legacy implementation made
# one LLM call per 8K-character chunk, so page length silently changed compute
# budget and timed-out calls kept running in executor threads. The pilot now
# uses exactly one fast-model call per successfully extracted source with a
# deterministic head/middle/tail sample of the page text.
SOURCE_TEXT_MAX_CHARS = 18_000
SOURCE_SUMMARY_REQUEST_TIMEOUT_SECONDS = 50
SOURCE_SUMMARY_MAX_WORDS = 450
NO_RELEVANT_EVIDENCE = "NO_RELEVANT_EVIDENCE"


def split_text(text: str, max_length: int = 8192) -> Generator[str, None, None]:
    """Split text into chunks of a maximum length."""
    paragraphs = text.split("\n")
    current_length = 0
    current_chunk = []

    for paragraph in paragraphs:
        if current_length + len(paragraph) + 1 <= max_length:
            current_chunk.append(paragraph)
            current_length += len(paragraph) + 1
        else:
            yield "\n".join(current_chunk)
            current_chunk = [paragraph]
            current_length = len(paragraph) + 1

    if current_chunk:
        yield "\n".join(current_chunk)


def select_source_text(text: str, max_chars: int = SOURCE_TEXT_MAX_CHARS) -> str:
    """Return a deterministic bounded sample spanning a long source.

    Short pages are retained verbatim. Long pages contribute equal-sized
    samples from the beginning, middle, and end so a fixed input cap does not
    systematically discard later sections such as migration notes or caveats.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if len(text) <= max_chars:
        return text

    separator = "\n\n[...source text omitted...]\n\n"
    separator_budget = 2 * len(separator)
    if max_chars <= separator_budget + 3:
        return text[:max_chars]

    content_budget = max_chars - separator_budget
    base, remainder = divmod(content_budget, 3)
    lengths = [base + (1 if index < remainder else 0) for index in range(3)]
    head_len, middle_len, tail_len = lengths

    head = text[:head_len]
    middle_start = max((len(text) - middle_len) // 2, head_len)
    middle = text[middle_start : middle_start + middle_len]
    tail = text[-tail_len:] if tail_len else ""
    sampled = separator.join((head, middle, tail))
    return sampled[:max_chars]


def create_source_summary_message(chunk: str, question: str) -> Dict[str, str]:
    """Create the bounded, evidence-only prompt used for one web source."""
    return {
        "role": "user",
        "content": (
            f'"""{chunk}"""\n\n'
            "Using ONLY the source text above, extract and summarize the evidence "
            f'relevant to this research question: "{question}". '
            "Preserve concrete facts, numbers, dates, limitations, and contrary "
            f"evidence. Keep the response under {SOURCE_SUMMARY_MAX_WORDS} words. "
            "Do not add outside knowledge. If the source text contains no substantive "
            f"evidence relevant to the question (for example a block/error page), "
            f"respond exactly with {NO_RELEVANT_EVIDENCE}."
        ),
    }


def summarize_text(
    url: str,
    text: str,
    question: str,
    driver: Optional[WebDriver] = None,
    usage_tracker: Optional[UsageTracker] = None,
) -> str:
    """Condense one scraped source with one bounded fast-model call.

    The URL and optional driver are retained for compatibility with the legacy
    application. Research-mode callers release the browser before this function
    runs. Provider-reported usage is recorded when a UsageTracker is supplied.
    """
    if not text:
        return "Error: No text to summarize"

    selected_text = select_source_text(text)
    if driver:
        scroll_to_percentage(driver, 0.5)

    return create_chat_completion(
        model=CFG.fast_llm_model,
        messages=[create_source_summary_message(selected_text, question)],
        usage_tracker=usage_tracker,
        request_timeout_seconds=SOURCE_SUMMARY_REQUEST_TIMEOUT_SECONDS,
    )


def scroll_to_percentage(driver: WebDriver, ratio: float) -> None:
    """Scroll to a percentage of the rendered page."""
    if ratio < 0 or ratio > 1:
        raise ValueError("Percentage should be between 0 and 1")
    driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {ratio});")


def create_message(chunk: str, question: str) -> Dict[str, str]:
    """Create a legacy question-focused message for non-source call sites."""
    return {
        "role": "user",
        "content": f'"""{chunk}""" Using the above text, answer the following'
        f' question: "{question}" -- if the question cannot be answered using the text,'
        " simply summarize the text in depth. "
        "Include all factual information, numbers, stats etc if available.",
    }


def write_to_file(filename: str, text: str) -> None:
    """Write text to a file."""
    with open(filename, "w") as file:
        file.write(text)


async def write_md_to_pdf(task: str, directory_name: str, text: str) -> None:
    file_path = f"./outputs/{directory_name}/{task}"
    write_to_file(f"{file_path}.md", text)
    md_to_pdf(f"{file_path}.md", f"{file_path}.pdf")
    print(f"{task} written to {file_path}.pdf")

    encoded_file_path = urllib.parse.quote(f"{file_path}.pdf")
    return encoded_file_path


def read_txt_files(directory):
    all_text = ""
    for filename in sorted(os.listdir(directory)):
        if filename.endswith(".txt"):
            with open(os.path.join(directory, filename), "r") as file:
                all_text += file.read() + "\n"
    return all_text


def md_to_pdf(input_file, output_file):
    md2pdf(
        output_file,
        md_content=None,
        md_file_path=input_file,
        css_file_path=None,
        base_url=None,
    )
