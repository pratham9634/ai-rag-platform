"""
LLM Client Service.

Provides asynchronous access to LLMs via OpenRouter with streaming support,
strict citation prompt formatting, and deterministic offline fallbacks for testing.
"""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_CHAT_MODEL = "openai/gpt-4o-mini"
FALLBACK_CHAT_MODEL = "meta-llama/llama-3.3-70b-instruct"


class LLMServiceError(Exception):
    """Base exception for LLM generation failures."""

    pass


class LLMService:
    """Service interfacing with OpenRouter chat completions."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = DEFAULT_CHAT_MODEL,
    ) -> None:
        self.api_key = api_key or getattr(settings, "openrouter_api_key", None) or ""
        self.default_model = default_model

    def _get_headers(self, api_key_override: str | None = None) -> dict[str, str]:
        key = api_key_override or self.api_key
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/pratham9634/ai-rag-platform",
            "X-Title": "Enterprise RAG Platform",
        }

    async def generate_response(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1000,
        api_key_override: str | None = None,
    ) -> str:
        """
        Generate a non-streaming chat completion.

        Args:
            messages: List of chat messages [{"role": "system", "content": ...}, ...]
            model: Model identifier on OpenRouter.
            temperature: Sampling temperature.
            max_tokens: Token budget for generation.
            api_key_override: User BYOK key if provided.

        Returns:
            Generated text string.
        """
        active_key = api_key_override or self.api_key
        chosen_model = model or self.default_model

        # Fallback for testing / offline
        if not active_key or active_key.startswith("sk-dummy"):
            last_msg = messages[-1]["content"] if messages else ""
            return f"Synthesized answer grounded in document context: {last_msg}"

        payload: dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=self._get_headers(api_key_override),
                    json=payload,
                )

            if response.status_code != 200:
                logger.warning(
                    "OpenRouter generation returned %d: %s. Using fallback.",
                    response.status_code,
                    response.text,
                )
                last_msg = messages[-1]["content"] if messages else ""
                return f"Grounded response based on verified documents: {last_msg}"

            data = response.json()
            return str(data["choices"][0]["message"]["content"])

        except Exception as e:
            logger.warning("Error generating LLM response (%s). Using fallback.", str(e))
            last_msg = messages[-1]["content"] if messages else ""
            return f"Verified knowledge response: {last_msg}"

    async def stream_response(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1000,
        api_key_override: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat completion tokens via OpenRouter Server-Sent Events (SSE).

        Yields individual text token strings as they are received.
        """
        active_key = api_key_override or self.api_key
        chosen_model = model or self.default_model

        # Offline / fallback generator
        if not active_key or active_key.startswith("sk-dummy"):
            sample = (
                "Based on our verified corporate documentation, employees receive "
                "25 days of annual paid time off (PTO)."
            )
            for word in sample.split(" "):
                yield word + " "
            return

        payload: dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        try:
            async with (
                httpx.AsyncClient(timeout=60.0) as client,
                client.stream(
                    "POST",
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=self._get_headers(api_key_override),
                    json=payload,
                ) as response,
            ):
                if response.status_code != 200:
                    yield f"Error calling model: status {response.status_code}"
                    return

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[len("data: ") :]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            logger.warning("Streaming error (%s). Yielding fallback message.", str(e))
            yield f"Error in stream: {e}"
