"""AI provider abstraction.

The service layer talks to this interface only, so a second local engine could
be added without touching prompt construction, grounding or the API. There is
deliberately no hosted provider: the project runs at zero cost, offline.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class AIError(Exception):
    """Base class for every failure the AI layer can degrade from."""


class AIUnavailableError(AIError):
    """The engine could not be reached, or the configured model is missing."""


class AITimeoutError(AIError):
    """The engine accepted the request but did not answer in time."""


class AIResponseError(AIError):
    """The engine answered with something unusable."""


@runtime_checkable
class AIProvider(Protocol):
    """A local text generator.

    Implementations must translate their own transport failures into the three
    errors above; callers never see engine-specific exceptions.
    """

    name: str
    model: str

    def is_available(self) -> bool:
        """Whether the engine is reachable and the configured model is present."""
        ...

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Return the assistant's answer, or raise an AIError."""
        ...


class DisabledProvider:
    """Stands in when AI is switched off by configuration.

    Having an object here rather than None keeps the service free of
    "is AI configured" branching.
    """

    name = "disabled"
    model = ""

    def is_available(self) -> bool:
        return False

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise AIUnavailableError("AI is disabled by configuration.")
