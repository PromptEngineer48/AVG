"""OpenAI GPT LLM provider."""
from __future__ import annotations
import os
from .base import BaseLLMProvider, LLMResponse


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, model: str):
        self.model = model
        # Lazy import so openai package is optional
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        except ImportError:
            raise ImportError("openai package required: pip install openai")

    @property
    def provider_name(self) -> str:
        return "openai"

    async def complete(
        self,
        user_prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            text=choice.message.content or "",
            provider="openai",
            model=self.model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )
