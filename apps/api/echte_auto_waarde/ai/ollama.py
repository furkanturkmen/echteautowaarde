"""Ollama provider.

Talks to a locally running Ollama over its HTTP API. No SDK: the two calls this
needs are a model list and a chat completion, and a direct client keeps the
dependency surface and the failure modes obvious.

Generation is deliberately dull. This product values saying the same true thing
twice over saying it creatively, so temperature is low and the reply length is
capped.
"""

from __future__ import annotations

import logging

import httpx

from echte_auto_waarde.ai.provider import (
    AIResponseError,
    AITimeoutError,
    AIUnavailableError,
)

logger = logging.getLogger(__name__)

# Low but not zero: greedy decoding on small models tends to loop.
TEMPERATURE = 0.2
TOP_P = 0.9
# An explanation, not an essay. Also bounds the worst-case response time.
MAX_OUTPUT_TOKENS = 700
# Availability is a fast check; it must never hold up a page.
AVAILABILITY_TIMEOUT_SECONDS = 2.0


class OllamaProvider:
    """Local inference through Ollama. Implements `AIProvider`."""

    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        """True only when Ollama answers and actually has the configured model.

        A running engine without the model is not available: pulling one is a
        deliberate act by the developer, never something the app does silently
        while someone waits for a page.
        """
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=AVAILABILITY_TIMEOUT_SECONDS)
            response.raise_for_status()
            installed = {entry.get("name", "") for entry in response.json().get("models", [])}
        except Exception:
            return False

        # Ollama reports "qwen2.5:7b-instruct"; a configured bare name should
        # still match the tagged model it resolves to.
        return any(
            name == self.model or name.split(":")[0] == self.model.split(":")[0]
            for name in installed
        )

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": TEMPERATURE,
                "top_p": TOP_P,
                "num_predict": MAX_OUTPUT_TOKENS,
            },
        }

        try:
            response = httpx.post(
                f"{self.base_url}/api/chat", json=payload, timeout=self.timeout_seconds
            )
        except httpx.TimeoutException as error:
            raise AITimeoutError("Het lokale model reageerde niet op tijd.") from error
        except httpx.HTTPError as error:
            raise AIUnavailableError("Ollama is niet bereikbaar.") from error

        if response.status_code == 404:
            # Ollama returns 404 for an unknown model.
            raise AIUnavailableError(f"Model '{self.model}' is niet geïnstalleerd.")
        if response.status_code >= 400:
            raise AIUnavailableError(f"Ollama antwoordde met status {response.status_code}.")

        try:
            body = response.json()
        except ValueError as error:
            raise AIResponseError("Ollama gaf geen geldige JSON terug.") from error

        message = body.get("message")
        if not isinstance(message, dict):
            raise AIResponseError("Antwoord van Ollama mist het message-veld.")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise AIResponseError("Antwoord van Ollama bevat geen tekst.")

        return content.strip()
