"""Client for OpenAI and OpenAI-compatible APIs (DeepSeek, OpenRouter, LM Studio, Ollama)."""

from __future__ import annotations

import json
import re
from typing import Any

from kindle_vocab_app.llm import LLMError
from kindle_vocab_app.logging_config import get_logger

logger = get_logger(__name__)

# Not every compatible server supports strict JSON schemas, so fall back
# gracefully and remember the first mode the server accepts.
_RESPONSE_MODES = ("json_schema", "json_object", "plain")


class OpenAICompatibleClient:
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: float = 120.0, max_retries: int = 2) -> None:
        if not base_url:
            raise LLMError("Укажите адрес API провайдера", fatal=True)
        if not model:
            raise LLMError("Выберите модель в настройках ИИ", fatal=True)
        from openai import OpenAI

        # Local servers ignore the key but the SDK requires a non-empty value.
        self._client = OpenAI(base_url=base_url, api_key=api_key or "not-needed", timeout=timeout, max_retries=max_retries)
        self.model = model
        self._mode_index = 0

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        import openai

        while True:
            mode = _RESPONSE_MODES[self._mode_index]
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    **_response_format(mode, schema),
                )
            except openai.BadRequestError as exc:
                if self._mode_index < len(_RESPONSE_MODES) - 1 and _mentions_response_format(exc):
                    logger.info("Provider rejected response mode=%s; trying a simpler one", mode)
                    self._mode_index += 1
                    continue
                raise LLMError(f"Провайдер отклонил запрос: {_short(exc)}") from exc
            except openai.AuthenticationError as exc:
                raise LLMError("Ключ API не подошёл. Проверьте его в настройках", fatal=True) from exc
            except openai.PermissionDeniedError as exc:
                raise LLMError(f"Нет доступа к модели: {_short(exc)}", fatal=True) from exc
            except openai.NotFoundError as exc:
                raise LLMError(f"Модель «{self.model}» не найдена у провайдера", fatal=True) from exc
            except openai.RateLimitError as exc:
                raise LLMError("Превышен лимит запросов или закончился баланс у провайдера", fatal=True) from exc
            except openai.APITimeoutError as exc:
                raise LLMError("Модель не ответила вовремя", transient=True) from exc
            except openai.APIConnectionError as exc:
                raise LLMError("Нет соединения с провайдером. Для локальной модели запустите сервер", fatal=True) from exc
            except openai.APIStatusError as exc:
                raise LLMError(f"Ошибка провайдера ({exc.status_code}): {_short(exc)}") from exc
            content = (response.choices[0].message.content or "") if response.choices else ""
            return parse_json_object(content)

    def list_models(self) -> list[str]:
        import openai

        try:
            return sorted(model.id for model in self._client.models.list())
        except openai.AuthenticationError as exc:
            raise LLMError("Ключ API не подошёл", fatal=True) from exc
        except openai.APIConnectionError as exc:
            raise LLMError("Нет соединения с провайдером", fatal=True) from exc
        except openai.APIError as exc:
            raise LLMError(f"Не удалось получить список моделей: {_short(exc)}") from exc


def _response_format(mode: str, schema: dict[str, Any]) -> dict[str, Any]:
    if mode == "json_schema":
        return {"response_format": {"type": "json_schema", "json_schema": {"name": "cards", "schema": schema, "strict": True}}}
    if mode == "json_object":
        return {"response_format": {"type": "json_object"}}
    return {}


def _mentions_response_format(exc: Exception) -> bool:
    text = str(exc).casefold()
    return any(marker in text for marker in ("response_format", "json_schema", "json_object", "structured"))


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating code fences and reasoning preambles."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise LLMError("Модель вернула ответ не в формате JSON")
    try:
        value = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError("Модель вернула повреждённый JSON") from exc
    if not isinstance(value, dict):
        raise LLMError("Модель вернула JSON не того вида")
    return value


def _short(exc: Exception) -> str:
    return " ".join(str(exc).split())[:240]
