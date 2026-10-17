"""Configuration class to store the state of bools for different scripts access."""
import os

import openai
from colorama import Fore
from dotenv import load_dotenv

from settings.singleton import Singleton

# Explicit process environment variables must win over values in a local .env.
# This is especially important for reproducible experiments that pin model IDs
# and temperature on the command line.
load_dotenv(override=False, verbose=True)


class Config(metaclass=Singleton):
    """Configuration shared by the application and research runner."""

    def __init__(self) -> None:
        self.debug_mode = False
        self.allow_downloads = False

        self.selenium_web_browser = os.getenv("USE_WEB_BROWSER", "chrome")
        self.fast_llm_model = os.getenv("FAST_LLM_MODEL", "gpt-3.5-turbo-16k")
        self.smart_llm_model = os.getenv("SMART_LLM_MODEL", "gpt-4")
        self.fast_token_limit = int(os.getenv("FAST_TOKEN_LIMIT", 4000))
        self.smart_token_limit = int(os.getenv("SMART_TOKEN_LIMIT", 8000))
        self.browse_chunk_max_length = int(os.getenv("BROWSE_CHUNK_MAX_LENGTH", 8192))

        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.temperature = float(os.getenv("TEMPERATURE", "1"))

        self.user_agent = os.getenv(
            "USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36",
        )

        self.memory_backend = os.getenv("MEMORY_BACKEND", "local")
        openai.api_key = self.openai_api_key

    def set_fast_llm_model(self, value: str) -> None:
        self.fast_llm_model = value

    def set_smart_llm_model(self, value: str) -> None:
        self.smart_llm_model = value

    def set_fast_token_limit(self, value: int) -> None:
        self.fast_token_limit = value

    def set_smart_token_limit(self, value: int) -> None:
        self.smart_token_limit = value

    def set_browse_chunk_max_length(self, value: int) -> None:
        self.browse_chunk_max_length = value

    def set_openai_api_key(self, value: str) -> None:
        self.openai_api_key = value

    def set_debug_mode(self, value: bool) -> None:
        self.debug_mode = value


def check_openai_api_key() -> None:
    """Check if the OpenAI API key is configured."""
    cfg = Config()
    if not cfg.openai_api_key:
        print(
            Fore.RED
            + "Please set your OpenAI API key in .env or as an environment variable."
        )
        print("You can get your key from https://platform.openai.com/account/api-keys")
        exit(1)
