"""
LLM Provider Base Interface
────────────────────────────
All LLM providers implement this interface.
Services call cfg.llm.complete() — never import a specific SDK directly.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class BaseLLMProvider(ABC):
    """Unified interface for any LLM provider."""

    @abstractmethod
    async def complete(
        self,
        user_prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Send a prompt and return a response."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...
