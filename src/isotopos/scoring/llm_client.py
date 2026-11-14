"""HTTP REST clients for AI model weight evaluation (Gemini & OpenAI-compatible)."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol

import httpx


class LLMConfigurationError(RuntimeError):
    """Raised when no AI model API key or endpoint is configured."""


class LLMProviderError(RuntimeError):
    """Raised when the upstream AI model API request fails or returns invalid JSON."""


class LLMClient(Protocol):
    """Minimal protocol for requesting structured parameter weights from an AI model."""

    def generate_weights_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Send prompts to the AI model and return the parsed JSON dictionary."""


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _extract_json_dict(raw_text: str) -> dict[str, Any]:
    cleaned = _FENCE_RE.sub("", raw_text.strip()).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMProviderError(f"AI model returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMProviderError("AI model JSON response must be an object mapping parameter IDs to weights.")
    return parsed


class GeminiRESTClient:
    """Google Gemini REST API client using httpx."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        timeout_s: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise LLMConfigurationError("Gemini API key cannot be empty.")
        self._api_key = api_key.strip()
        self._model = model.strip() or "gemini-2.5-flash"
        self._timeout_s = timeout_s
        self._transport = transport

    def generate_weights_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
                "responseSchema": json_schema,
            },
        }
        try:
            with httpx.Client(timeout=self._timeout_s, transport=self._transport) as client:
                resp = client.post(
                    url,
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": self._api_key,
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Gemini API request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise LLMProviderError(
                f"Gemini API returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("Unexpected Gemini API response structure.") from exc

        return _extract_json_dict(text)


class OpenAICompatibleRESTClient:
    """OpenAI-compatible Chat Completions REST client (OpenAI, OpenRouter, Ollama, vLLM)."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout_s: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._base_url = base_url.strip().rstrip("/") or "https://api.openai.com/v1"
        self._model = model.strip() or "gpt-4o-mini"
        self._timeout_s = timeout_s
        self._transport = transport

    def generate_weights_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        url = f"{self._base_url}/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": self._model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            with httpx.Client(timeout=self._timeout_s, transport=self._transport) as client:
                resp = client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"OpenAI-compatible API request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise LLMProviderError(
                f"OpenAI-compatible API returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("Unexpected OpenAI-compatible API response structure.") from exc

        return _extract_json_dict(text)


def resolve_llm_client() -> LLMClient:
    """Resolve the configured AI model client from environment variables."""
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key:
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
        return GeminiRESTClient(api_key=gemini_key, model=model)

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip() or os.getenv("OPENAI_BASE_URL", "").strip()
    if openai_key or base_url:
        model = (
            os.getenv("LLM_MODEL", "").strip()
            or os.getenv("OPENAI_MODEL", "").strip()
            or "gpt-4o-mini"
        )
        return OpenAICompatibleRESTClient(
            api_key=openai_key,
            base_url=base_url or "https://api.openai.com/v1",
            model=model,
        )

    raise LLMConfigurationError(
        "No AI API key configured. Set GEMINI_API_KEY or OPENAI_API_KEY (or LLM_BASE_URL) in the environment."
    )
