from __future__ import annotations

from openai import OpenAI

from .config import Settings

class LocalProvider:
    """OpenAI-compatible transport for local Ollama, LM Studio, or a custom endpoint."""
    def __init__(self, settings: Settings):
        self.settings = settings
        key = settings.resolved_api_key() or "local-no-key"
        self.client = OpenAI(base_url=settings.base_url.rstrip("/"), api_key=key,
                             timeout=settings.request_timeout_seconds, max_retries=1)

    def list_models(self) -> list[str]:
        result = self.client.models.list()
        return [model.id for model in result.data]

    def chat(self, messages: list[dict], tools: list[dict]):
        return self.client.chat.completions.create(
            model=self.settings.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_output_tokens,
        )
