from __future__ import annotations

import json
import logging
import time
from typing import Optional

from fastapi import WebSocket
import openai
from langchain.adapters import openai as lc_openai
from colorama import Fore, Style
from openai.error import APIError, RateLimitError

from logic.prompts import auto_agent_instructions
from settings import Config

CFG = Config()
openai.api_key = CFG.openai_api_key


def create_chat_completion(
    messages: list,  # type: ignore
    model: Optional[str] = None,
    temperature: float = CFG.temperature,
    max_tokens: Optional[int] = None,
    stream: Optional[bool] = False,
    websocket: WebSocket | None = None,
) -> str:
    """Create a chat completion using the configured OpenAI-compatible API.

    Transient API/rate-limit failures are retried with bounded exponential
    backoff. Non-transient exceptions are allowed to surface immediately so
    configuration and programming errors are not hidden.
    """
    if model is None:
        raise ValueError("Model cannot be None")
    if max_tokens is not None and max_tokens > 8001:
        raise ValueError(
            f"Max tokens cannot be more than 8001, but got {max_tokens}"
        )
    if stream and websocket is None:
        raise ValueError("Websocket cannot be None when stream is True")

    last_error: Exception | None = None
    max_attempts = 5

    for attempt in range(max_attempts):
        try:
            return send_chat_completion_request(
                messages,
                model,
                temperature,
                max_tokens,
                stream,
                websocket,
            )
        except (APIError, RateLimitError) as exc:
            last_error = exc
            if attempt == max_attempts - 1:
                break
            delay_seconds = min(2 ** attempt, 16)
            logging.warning(
                "Transient LLM API failure on attempt %s/%s; retrying in %ss: %s",
                attempt + 1,
                max_attempts,
                delay_seconds,
                type(exc).__name__,
            )
            time.sleep(delay_seconds)

    logging.error("Failed to get response from LLM API after retries")
    raise RuntimeError("Failed to get response from LLM API") from last_error


def send_chat_completion_request(
    messages, model, temperature, max_tokens, stream, websocket
):
    if not stream:
        result = lc_openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            provider="ChatOpenAI",
        )
        return result["choices"][0]["message"]["content"]

    return stream_response(
        model,
        messages,
        temperature,
        max_tokens,
        websocket,
    )


async def stream_response(model, messages, temperature, max_tokens, websocket):
    paragraph = ""
    response = ""
    print("streaming response...")

    for chunk in lc_openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        provider="ChatOpenAI",
        stream=True,
    ):
        content = chunk["choices"][0].get("delta", {}).get("content")
        if content is not None:
            response += content
            paragraph += content
            if "\n" in paragraph:
                await websocket.send_json({"type": "report", "output": paragraph})
                paragraph = ""

    if paragraph:
        await websocket.send_json({"type": "report", "output": paragraph})

    print("streaming response complete")
    return response


def choose_agent(task: str) -> dict:
    """Determine a task-specific agent role for the requested research task."""
    try:
        response = create_chat_completion(
            model=CFG.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{auto_agent_instructions()}"},
                {"role": "user", "content": f"task: {task}"},
            ],
            temperature=0,
        )
        return json.loads(response)
    except Exception as exc:
        print(
            f"{Fore.RED}Error in choose_agent: {exc}{Style.RESET_ALL}"
        )
        return {
            "agent": "Default Agent",
            "agent_role_prompt": (
                "You are an AI critical thinker research assistant. Your sole "
                "purpose is to write well written, critically acclaimed, objective "
                "and structured reports on given text."
            ),
        }
