"""Client for the Anthropic Messages API (official Python SDK)."""

from __future__ import annotations

import json
from typing import Any

from kindle_vocab_app.llm import LLMError
from kindle_vocab_app.logging_config import get_logger

logger = get_logger(__name__)

# Models that accept the server-side refusal fallback ("default" routing).
_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicClient:
    def __init__(self, *, api_key: str, model: str, timeout: float = 180.0) -> None:
        if not api_key:
            raise LLMError("Добавьте ключ Anthropic в настройках ИИ", fatal=True)
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self.model = model or "claude-opus-5-5"

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        import anthropic

        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 16000,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            # Translation of a handful of words is a light task; low effort keeps
            # latency and cost down while thinking stays adaptive.
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        }
        if self.model in _FALLBACK_MODELS:
            request.update(betas=[_FALLBACK_BETA], fallbacks="default")
        try:
            response = self._client.beta.messages.create(**request)
        except anthropic.AuthenticationError as exc:
            raise LLMError("Ключ Anthropic не подошёл. Проверьте его в настройках", fatal=True) from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMError("У ключа нет доступа к этой модели", fatal=True) from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"Модель «{self.model}» не найдена", fatal=True) from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Превышен лимит запросов Anthropic. Попробуйте позже", fatal=True) from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"Anthropic отклонил запрос: {exc.message}") from exc
        except anthropic.APITimeoutError as exc:
            raise LLMError("Anthropic не ответил вовремя") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Нет соединения с Anthropic", fatal=True) from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Ошибка Anthropic ({exc.status_code})") from exc

        if response.stop_reason == "refusal":
            raise LLMError("Модель отказалась обрабатывать эту группу слов")
        if response.stop_reason == "max_tokens":
            raise LLMError("Ответ модели оборвался: слишком длинный")
        text = next((block.text for block in response.content if block.type == "text"), "")
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError("Anthropic вернул повреждённый JSON") from exc
        if not isinstance(value, dict):
            raise LLMError("Anthropic вернул JSON не того вида")
        return value

    def list_models(self) -> list[str]:
        import anthropic

        try:
            return [model.id for model in self._client.models.list()]
        except anthropic.AuthenticationError as exc:
            raise LLMError("Ключ Anthropic не подошёл", fatal=True) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Нет соединения с Anthropic", fatal=True) from exc
        except anthropic.APIError as exc:
            raise LLMError(f"Не удалось получить список моделей: {exc}") from exc
