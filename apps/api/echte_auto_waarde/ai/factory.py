"""Provider selection.

One place decides which local engine the application talks to, so routes and
services never branch on configuration.
"""

from __future__ import annotations

from functools import lru_cache

from echte_auto_waarde.ai.ollama import OllamaProvider
from echte_auto_waarde.ai.provider import AIProvider, DisabledProvider
from echte_auto_waarde.config import get_settings


@lru_cache
def get_ai_provider() -> AIProvider:
    """The configured local provider, or a disabled stand-in.

    Constructing this never contacts the engine: startup must not depend on
    Ollama running, and availability is checked per request instead.
    """
    settings = get_settings()
    if not settings.ai_enabled:
        return DisabledProvider()
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
