"""Google Gemini LLM provider."""
from __future__ import annotations
import os
from .base import BaseLLMProvider, LLMResponse


class GeminiProvider(BaseLLMProvider):
    def __init__(self, model: str):
        self.model = model
        try:
            import google.generativeai as genai
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
            self._genai = genai
            self._model_obj = genai.GenerativeModel(model)
        except ImportError:
            raise ImportError(
                "google-generativeai package required: pip install google-generativeai"
            )

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def complete(
        self,
        user_prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> LLMResponse:
        full_prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt

        # Gemini's async generate
        generation_config = self._genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        response = await self._model_obj.generate_content_async(
            full_prompt, generation_config=generation_config
        )
        return LLMResponse(
            text=response.text,
            provider="gemini",
            model=self.model,
        )
