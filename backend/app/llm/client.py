"""Language-model access through the OpenAI-compatible gateway.

Layers:
- LlmBackend: one chat completion call (real gateway or a test double).
- StructuredLlm: EU data-zone guard, disk cache, retry, JSON extraction and Pydantic validation.
"""

from __future__ import annotations

import json
import random
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.llm.cache import LlmCache, cache_key
from app.logging import get_logger

log = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)

PROMPTS_DIR = Path(__file__).parent / "prompts"
EU_SUFFIX = "-dz-eu"
MAX_TRIES = 6


class LlmError(RuntimeError):
    pass


class LlmAuthError(LlmError):
    pass


class ExtractionFailed(LlmError):
    pass


class DataZoneViolation(LlmError):
    pass


class LlmBackend(ABC):
    @abstractmethod
    def complete(self, model: str, messages: list[dict], max_tokens: int, json_mode: bool) -> str:
        """Return the assistant message text."""


class GatewayBackend(LlmBackend):
    def __init__(self, settings: Settings | None = None, sleep: Callable[[float], None] = time.sleep):
        from openai import OpenAI

        s = settings or get_settings()
        if not s.api_key:
            raise LlmAuthError("API_KEY is not set in .env")
        self._client = OpenAI(
            base_url=s.llm_base_url,
            api_key="unused",
            default_headers={"api-key": s.api_key},
            max_retries=0,
        )
        self._sleep = sleep
        self._json_mode_rejected: set[str] = set()

    def complete(self, model: str, messages: list[dict], max_tokens: int, json_mode: bool) -> str:
        import openai

        use_json = json_mode and model not in self._json_mode_rejected
        for attempt in range(MAX_TRIES):
            kwargs: dict = {
                "model": model,
                "messages": messages,
                "max_completion_tokens": max_tokens,
            }
            if use_json:
                kwargs["response_format"] = {"type": "json_object"}
            try:
                resp = self._client.chat.completions.create(**kwargs)
                return resp.choices[0].message.content or ""
            except openai.RateLimitError:
                delay = min(60.0, 2.0**attempt) + random.uniform(0, 1)
                log.warning("rate limited, retrying", extra={"fields": {"attempt": attempt + 1}})
                self._sleep(delay)
            except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
                raise LlmAuthError(f"gateway rejected the credentials ({type(exc).__name__})") from exc
            except openai.BadRequestError as exc:
                if use_json:
                    self._json_mode_rejected.add(model)
                    use_json = False
                    continue
                raise LlmError(f"bad request to deployment {model}: {str(exc)[:200]}") from exc
            except (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError):
                self._sleep(min(30.0, 2.0**attempt))
        raise LlmError(f"gateway unavailable or rate limited after {MAX_TRIES} tries")


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> dict:
    """Parse a JSON object from a reply that may be wrapped in prose or code fences."""
    text = text.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_OBJECT.search(text)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise json.JSONDecodeError("expected a JSON object", text, 0)
    return value


def load_prompt(name: str) -> tuple[str, str]:
    """Return (version, body). The first line of a prompt file is 'version: <id>'."""
    raw = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    first, _, body = raw.partition("\n")
    if not first.lower().startswith("version:"):
        raise LlmError(f"prompt {name} has no version line")
    return first.split(":", 1)[1].strip(), body.strip()


class StructuredLlm:
    def __init__(
        self,
        backend: LlmBackend,
        cache: LlmCache | None = None,
        settings: Settings | None = None,
        enforce_eu: bool = True,
    ):
        self.backend = backend
        self.settings = settings or get_settings()
        self.cache = cache or LlmCache(self.settings.cache_dir)
        self.enforce_eu = enforce_eu

    def run(
        self,
        prompt_name: str,
        user_text: str,
        schema: type[T],
        *,
        model: str | None = None,
        contains_report_text: bool = True,
        max_tokens: int = 4000,
    ) -> T:
        model = model or self.settings.llm_model_extract
        if contains_report_text and self.enforce_eu and not model.endswith(EU_SUFFIX):
            raise DataZoneViolation(
                f"deployment {model} is not an EU data-zone deployment; report text must not be sent"
            )
        version, system = load_prompt(prompt_name)
        key = cache_key(model, version, system, user_text)
        cached = self.cache.get(version, key)
        if cached is not None:
            try:
                return schema.model_validate(cached)
            except ValidationError:
                pass

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ]
        last_error = ""
        for _ in range(2):
            reply = self.backend.complete(model, messages, max_tokens, json_mode=True)
            try:
                result = schema.model_validate(extract_json(reply))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = str(exc)[:400]
                messages = messages + [
                    {"role": "assistant", "content": reply[:2000]},
                    {
                        "role": "user",
                        "content": "The previous reply was invalid: "
                        f"{last_error}. Return only the corrected JSON object.",
                    },
                ]
                continue
            self.cache.put(version, key, result.model_dump(mode="json"))
            return result
        raise ExtractionFailed(f"model output failed validation: {last_error}")
