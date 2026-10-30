"""Provider presets and API-key storage in the operating system keychain."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from kindle_vocab_app.llm import LLMError

KEYRING_SERVICE = "kindle-cards"
ENV_API_KEY = "KINDLE_CARDS_LLM_API_KEY"


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    label: str
    kind: str  # "openai_compatible" | "anthropic"
    base_url: str
    default_model: str
    needs_key: bool
    local: bool
    hint: str


PRESETS: dict[str, ProviderPreset] = {
    preset.id: preset
    for preset in [
        ProviderPreset(
            "anthropic", "Anthropic (Claude)", "anthropic", "", "claude-opus-5-5", True, False,
            "Ключ: console.anthropic.com",
        ),
        ProviderPreset(
            "openai", "OpenAI", "openai_compatible", "https://api.openai.com/v1", "", True, False,
            "Ключ: platform.openai.com",
        ),
        ProviderPreset(
            "deepseek", "DeepSeek", "openai_compatible", "https://api.deepseek.com/v1", "deepseek-chat", True, False,
            "Ключ: platform.deepseek.com",
        ),
        ProviderPreset(
            "openrouter", "OpenRouter", "openai_compatible", "https://openrouter.ai/api/v1", "", True, False,
            "Один ключ для многих моделей: openrouter.ai",
        ),
        ProviderPreset(
            "lmstudio", "LM Studio (локально)", "openai_compatible", "http://localhost:1234/v1", "", False, True,
            "Бесплатно, слова не покидают компьютер. Запустите сервер в LM Studio",
        ),
        ProviderPreset(
            "ollama", "Ollama (локально)", "openai_compatible", "http://localhost:11434/v1", "", False, True,
            "Бесплатно, слова не покидают компьютер",
        ),
        ProviderPreset(
            "custom", "Другой OpenAI-совместимый", "openai_compatible", "", "", True, False,
            "Укажите адрес API и модель",
        ),
    ]
}


def preset_for(provider: str) -> ProviderPreset:
    preset = PRESETS.get(provider)
    if preset is None:
        raise LLMError("Выберите провайдера ИИ в настройках", fatal=True)
    return preset


def presets_payload() -> list[dict[str, Any]]:
    return [asdict(preset) for preset in PRESETS.values()]


class _KeyringBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


def _keyring() -> _KeyringBackend:
    try:
        import keyring
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise LLMError("Пакет keyring не установлен", fatal=True) from exc
    return keyring


def get_api_key(provider: str) -> str:
    """Environment override first (for development), then the OS keychain."""
    from_env = os.environ.get(ENV_API_KEY, "").strip()
    if from_env:
        return from_env
    try:
        return (_keyring().get_password(KEYRING_SERVICE, provider) or "").strip()
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"Не удалось прочитать ключ из системного хранилища: {exc}", fatal=True) from exc


def set_api_key(provider: str, api_key: str) -> None:
    preset_for(provider)
    value = api_key.strip()
    if not value:
        raise LLMError("Пустой ключ не сохранён")
    try:
        _keyring().set_password(KEYRING_SERVICE, provider, value)
    except Exception as exc:
        raise LLMError(f"Не удалось сохранить ключ в системное хранилище: {exc}", fatal=True) from exc


def delete_api_key(provider: str) -> None:
    from keyring.errors import PasswordDeleteError

    try:
        _keyring().delete_password(KEYRING_SERVICE, provider)
    except PasswordDeleteError:
        return  # Already absent.


def has_api_key(provider: str) -> bool:
    try:
        return bool(get_api_key(provider))
    except LLMError:
        return False
