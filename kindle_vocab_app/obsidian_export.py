"""Export standalone flashcards into a Kindle Cards-owned folder in an Obsidian vault."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kindle_vocab_app import study_details
from kindle_vocab_app.obsidian_sync import vault_operation_lock

_PLUGIN = "obsidian-spaced-repetition"
_FOLDER = "Kindle Cards"
_OWNER_FILE = ".kindle-cards-owner"
_OWNER = b"kindle-cards-obsidian-export-v1\n"
_ID = re.compile(r"(?m)^kindle_cards_id: ([0-9a-f]{64})$")
_DIGEST = re.compile(r"(?m)^kindle_cards_checksum: ([0-9a-f]{64})\n")
_FILE_ID = re.compile(r"(?:^|--)kc-([0-9a-f]{64})\.md\Z", re.IGNORECASE)
_DEVICE = re.compile(r"(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])\Z", re.IGNORECASE)
_SCHEDULE = re.compile(r"(?:\n> \[!sr\|card-metadata\][ \t]*\n>[ \t]*|\n|[ \t]+)<!--SR:[^\r\n]+?-->")
_TAG = re.compile(r"#[\w-]+(?:/[\w-]+)*\Z")
_NO_PLUGIN = "Включите Spaced Repetition в Obsidian, чтобы увидеть выгруженные карточки."
_EXTERNAL_SCHEDULE = "Для внешнего хранилища расписания доступны только новые карточки Kindle Cards."


@dataclass(slots=True)
class ObsidianExportResult:
    folder: Path
    written_ids: list[str] = field(default_factory=list)
    unchanged_ids: list[str] = field(default_factory=list)
    conflict_ids: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)


class ObsidianExportError(ValueError):
    """A reader-facing failure before export can safely continue."""


@dataclass(frozen=True, slots=True)
class _Settings:
    folder_decks: bool
    tags: tuple[str, ...]
    ignored_tags: tuple[str, ...]
    ignored_paths: tuple[str, ...]
    separator: str
    end: str
    inline: tuple[str, ...]
    reserved: tuple[str, ...]
    inline_schedule: bool
    plugin_enabled: bool


@dataclass(frozen=True, slots=True)
class _Note:
    lexeme_id: str
    stable_id: str
    preferred: Path
    text: str


def export_cards(
    vault: Path,
    entries: Iterable[Mapping[str, Any]],
    *,
    note_keys: Mapping[str, str],
    edits: Mapping[str, Mapping[str, Any]] | None = None,
    lock_held: bool = False,
) -> ObsidianExportResult:
    """Publish per-note updates. Set lock_held only inside vault_operation_lock(vault)."""
    vault = _vault_root(vault)
    config = _find_config(vault)
    if config is None:
        raise ObsidianExportError("Выберите папку хранилища Obsidian с папкой настроек")
    result = ObsidianExportResult(vault / _FOLDER)
    with nullcontext() if lock_held else vault_operation_lock(vault):
        settings = _read_settings(config)
        if not settings.plugin_enabled:
            result.notices.append(_NO_PLUGIN)
        if not settings.inline_schedule:
            result.notices.append(_EXTERNAL_SCHEDULE)
        notes = _prepare_notes(result.folder, entries, note_keys, edits or {}, settings)
        if not notes:
            return result
        _ensure_owned(result.folder)
        existing = _existing_notes(result.folder, {note.stable_id for note in notes})
        for note in notes:
            _publish_note(vault, note, existing.get(note.stable_id, ()), settings, result)
    return result


def managed_folder(vault: Path) -> Path:
    """Return the verified, existing export folder without creating any files."""
    vault = _vault_root(vault)
    if _find_config(vault) is None:
        raise ObsidianExportError("Выберите папку хранилища Obsidian с папкой настроек")
    folder = vault / _FOLDER
    if _checked(folder, directory=True) is None:
        raise ObsidianExportError("Папка экспорта Kindle Cards ещё не создана")
    _verify_owner(folder)
    return folder


def _vault_root(vault: Path) -> Path:
    if ".." in vault.parts:
        raise ObsidianExportError("Путь к хранилищу Obsidian не должен содержать переходы в родительские папки")
    vault = vault.absolute()
    for directory in [*reversed(vault.parents), vault]:
        _checked(directory, directory=True, missing=False)
    return vault


def _checked(path: Path, *, directory: bool = False, missing: bool = True) -> os.stat_result | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing:
            return None
        raise ObsidianExportError("Указанная папка хранилища Obsidian не найдена") from None
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT or not expected(info.st_mode):
        raise ObsidianExportError(f"Небезопасный путь в хранилище Obsidian: {path.name}")
    return info


def _read_json(path: Path) -> Any:
    if _checked(path) is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ObsidianExportError(f"Не удалось прочитать настройки Obsidian: {path.name}") from exc


def _find_config(vault: Path) -> Path | None:
    candidates = []
    for path in vault.iterdir():
        if not path.name.startswith("."):
            continue
        info = path.lstat()
        if path.name != ".obsidian" and (
            not stat.S_ISDIR(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            continue
        if path.name == ".obsidian" or any(_checked(path / marker) is not None for marker in (
            "community-plugins.json", "app.json",
        )):
            _checked(path, directory=True, missing=False)
            candidates.append(path)
    if len(candidates) > 1:
        raise ObsidianExportError("В хранилище несколько папок настроек Obsidian. Нельзя определить активную")
    return next(iter(candidates), None)


def _read_settings(config: Path) -> _Settings:
    _checked(config, directory=True, missing=False)
    values: dict[str, Any] = {}
    enabled = False
    installed = config / "plugins" / _PLUGIN
    enabled_list = _read_json(config / "community-plugins.json")
    if _checked(installed.parent, directory=True) and _checked(installed, directory=True):
        data = _read_json(installed / "data.json")
        if data is not None:
            settings = data.get("settings", {}) if isinstance(data, dict) else None
            if not isinstance(settings, dict):
                raise ObsidianExportError("Настройки Spaced Repetition имеют неизвестный формат")
            values = settings
        enabled = isinstance(enabled_list, list) and _PLUGIN in enabled_list

    def strings(key: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
        value = values.get(key)
        if key not in values:
            return default
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ObsidianExportError(f"Неподдерживаемое значение Spaced Repetition: {key}")
        return tuple(value)

    def marker(key: str, default: str) -> str:
        value = values.get(key, default)
        if not isinstance(value, str) or value != value.strip() or any(c in value for c in "\r\n\x00"):
            raise ObsidianExportError(f"Неподдерживаемый разделитель Spaced Repetition: {key}")
        return value

    separator = marker("multilineCardSeparator", "?")
    end = marker("multilineCardEndMarker", "")
    inline = tuple(filter(None, (
        marker("singleLineCardSeparator", "::"), marker("singleLineReversedCardSeparator", ":::"),
    )))
    reverse = marker("multilineReversedCardSeparator", "??")
    if (not separator or separator == end or any(item in separator for item in inline)
            or separator.startswith(("<!--", "```", "~~~")) or end.startswith("<!--")):
        raise ObsidianExportError("Разделитель многострочной карточки Spaced Repetition конфликтует с настройками")
    folder_decks = values.get("convertFoldersToDecks", False)
    if not isinstance(folder_decks, bool):
        raise ObsidianExportError("Неподдерживаемый режим колод Spaced Repetition")
    return _Settings(
        folder_decks, strings("flashcardTags", ("#flashcards",)), strings("flashcardTagsToIgnore"),
        strings("noteFoldersToIgnore", ("**/*.excalidraw.md",)), separator, end, inline,
        tuple(item for item in (*inline, separator, reverse, end) if item),
        values.get("dataStore", "NOTES") == "NOTES", enabled,
    )


def _matches_path(path: str, pattern: str) -> bool:
    if path.startswith(pattern):
        return True
    if pattern.startswith(("#", "!")) or any(token in pattern for token in ("{", "}", "\\", "(")):
        raise ObsidianExportError("Spaced Repetition использует сложное правило исключения папок")
    parts = path.split("/")

    def matches(patterns: list[str], names: list[str]) -> bool:
        if not patterns:
            return not names
        head, *tail = patterns
        if head == "**":
            return matches(tail, names) or bool(names and matches(patterns, names[1:]))
        return bool(names and fnmatch.fnmatchcase(names[0], head) and matches(tail, names[1:]))

    return matches(pattern.split("/"), parts)


def _is_ignored(path: Path, vault: Path, settings: _Settings) -> bool:
    name = path.relative_to(vault).as_posix()
    return any(_matches_path(name, pattern) for pattern in settings.ignored_paths)


def _deck_tag(settings: _Settings, level: int) -> str:
    if settings.folder_decks:
        return ""
    for root in settings.tags:
        if not _TAG.fullmatch(root) or not any(char.isalpha() for char in root):
            continue
        tag = f"{root}/kindle-cards/level-{level:02}"
        if not any(tag == ignored or tag.startswith(ignored + "/") for ignored in settings.ignored_tags):
            return tag
    raise ObsidianExportError("В настройках Spaced Repetition нет доступного тега для карточек Kindle Cards")


def _literal(value: str, settings: _Settings) -> str:
    value = " ".join(value.split())
    # Use entities so the SR parser never sees a tag, cloze, HTML comment or Markdown directive.
    sensitive = set("&<>#![]{}:=*`~_\\-+|%.") | {marker[0] for marker in settings.reserved}
    return "".join(f"&#{ord(char)};" if char in sensitive else char for char in value)


def _note_name(spelling: str, stable_id: str) -> str:
    label = "-".join(re.findall(r"[^\W_]+", spelling))[:40].rstrip("-") or "word"
    if _DEVICE.fullmatch(label):
        label = f"word-{label}"
    return f"{label}--kc-{stable_id}.md"


def _prepare_notes(
    folder: Path,
    entries: Iterable[Mapping[str, Any]],
    note_keys: Mapping[str, str],
    edits: Mapping[str, Mapping[str, Any]],
    settings: _Settings,
) -> list[_Note]:
    notes: list[_Note] = []
    seen: set[str] = set()
    for entry in entries:
        lexeme_id = str(entry.get("id") or "")
        key = note_keys.get(lexeme_id)
        level = (entry.get("study_priority") or {}).get("level")
        if not lexeme_id or not key or type(level) is not int or not 1 <= level <= 10:
            raise ObsidianExportError("Для карточки Obsidian отсутствует постоянный ID или уровень 1–10")
        stable_id = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if stable_id in seen:
            raise ObsidianExportError("Несколько выбранных слов имеют один постоянный ID карточки Obsidian")
        seen.add(stable_id)
        card, enrichment = study_details.resolve(entry, edits.get(lexeme_id))
        spelling = str(entry.get("display_form") or entry.get("lemma") or "—")
        front = _literal(spelling, settings)
        back = _literal(card.meaning_ru or "—", settings)
        if context := str(card.occurrence.get("context") or "").strip():
            back += "<br>" + _literal(context, settings)
        for detail in study_details.answer_details(enrichment, card):
            back += "<br>" + _literal(detail, settings)
        if any(marker in line for marker in settings.inline for line in (front, back)):
            raise ObsidianExportError("Разделитель Spaced Repetition встречается в тексте карточки Kindle Cards")
        if any(line in settings.reserved for line in (front, back)):
            raise ObsidianExportError("Текст карточки совпадает с разделителем Spaced Repetition")
        tag = _deck_tag(settings, level)
        tags = f"tags:\n  - {json.dumps(tag[1:], ensure_ascii=False)}\n" if tag else ""
        header = f"---\nkindle_cards_id: {stable_id}\nkindle_cards_level: {level}\n{tags}"
        body = f"---\n\n{front}\n{settings.separator}\n{back}\n"
        if settings.end:
            body += f"{settings.end}\n"
        digest = hashlib.sha256((header + body).encode("utf-8")).hexdigest()
        text = f"{header}kindle_cards_checksum: {digest}\n{body}"
        path = folder / f"{level:02}" / _note_name(spelling, stable_id)
        notes.append(_Note(lexeme_id, stable_id, path, text))
    return notes


def _ensure_owned(folder: Path) -> None:
    _checked(folder, directory=True)
    folder.mkdir(exist_ok=True)
    marker = folder / _OWNER_FILE
    if _checked(marker) is None:
        if any(folder.iterdir()):
            raise ObsidianExportError("Папка Kindle Cards уже занята. Её содержимое сохранено")
        _atomic_write(marker, _OWNER)
    _verify_owner(folder)


def _verify_owner(folder: Path) -> None:
    marker = folder / _OWNER_FILE
    if _checked(marker) is None or marker.read_bytes() != _OWNER:
        raise ObsidianExportError("Папка Kindle Cards не принадлежит этому формату выгрузки")


def _existing_notes(folder: Path, wanted: set[str]) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {}

    def cannot_read(error: OSError) -> None:
        raise ObsidianExportError("Не удалось проверить существующие карточки Kindle Cards") from error

    for directory, children, files in os.walk(folder, onerror=cannot_read, followlinks=False):
        parent = Path(directory)
        for name in children[:]:
            try:
                _checked(parent / name, directory=True, missing=False)
            except ObsidianExportError:
                children.remove(name)
        for name in files:
            if not name.lower().endswith(".md"):
                continue
            path = parent / name
            file_match = _FILE_ID.search(name)
            name_id = file_match[1].lower() if file_match else ""
            if name_id in wanted:
                result.setdefault(name_id, []).append(path)
            try:
                _checked(path, missing=False)
                with path.open(encoding="utf-8-sig") as stream:
                    frontmatter = stream.read(4096).split("\n---\n", 1)[0]
            except (ObsidianExportError, OSError, UnicodeError):
                continue
            identity = _ID.search(frontmatter) if frontmatter.startswith("---\n") else None
            if identity and identity[1] in wanted and identity[1] != name_id:
                result.setdefault(identity[1], []).append(path)
    return result


def _answer_end(text: str) -> int:
    _, marker, body = text.partition("\n---\n\n")
    if not marker or body.count("\n") < 3:
        return -1
    return len(text) - len(body) + len("\n".join(body.split("\n")[:3]))


def _generated_text(data: bytes, stable_id: str) -> tuple[str, str] | None:
    text = data.decode("utf-8").replace("\r\n", "\n")
    # A schedule, if present, must be the only addition to the generated answer.
    for match in _SCHEDULE.finditer(text):
        clean = text[:match.start()] + text[match.end():]
        if match.start() == _answer_end(clean):
            result = _verified_text(clean, stable_id)
            if result:
                return result, match[0]
    clean = _verified_text(text, stable_id)
    return (clean, "") if clean else None


def _verified_text(clean: str, stable_id: str) -> str | None:
    header = clean.split("\n---\n", 1)[0]
    identity, digest = _ID.search(header), _DIGEST.search(header + "\n")
    if not identity or identity[1] != stable_id or not digest or not header.startswith("---\n"):
        return None
    base = clean[:digest.start()] + clean[digest.end():]
    if hashlib.sha256(base.encode("utf-8")).hexdigest() != digest[1]:
        return None
    return clean


def _publish_note(
    vault: Path, note: _Note, paths: Iterable[Path], settings: _Settings, result: ObsidianExportResult,
) -> None:
    candidates = list(paths)
    if len(candidates) > 1:
        result.conflict_ids.append(note.lexeme_id)
        return
    path = candidates[0] if candidates else note.preferred
    if _is_ignored(path, vault, settings):
        result.conflict_ids.append(note.lexeme_id)
        message = "Некоторые карточки находятся в путях, исключённых настройками Spaced Repetition."
        if message not in result.notices:
            result.notices.append(message)
        return
    try:
        for parent in reversed(path.relative_to(vault).parents[:-1]):
            _checked(vault / parent, directory=True)
        info = _checked(path)
        if not candidates and info is not None:
            raise FileExistsError(path)
        if info is None:
            if candidates:
                raise FileNotFoundError(path)
            path.parent.mkdir(exist_ok=True)
            _atomic_write(path, note.text.encode("utf-8"))
        else:
            old = path.read_bytes()
            current = _generated_text(old, note.stable_id)
            if current is None:
                result.conflict_ids.append(note.lexeme_id)
                return
            if path.parent != note.preferred.parent:
                message = "Пути уже созданных карточек сохранены. Уровень в свойствах может отличаться от папки."
                if message not in result.notices:
                    result.notices.append(message)
            clean, schedule = current
            if clean == note.text:
                result.unchanged_ids.append(note.lexeme_id)
                return
            if not settings.inline_schedule:
                result.conflict_ids.append(note.lexeme_id)
                return
            text = note.text
            if schedule:
                answer_end = _answer_end(text)
                text = text[:answer_end] + schedule + text[answer_end:]
            if b"\r\n" in old:
                text = text.replace("\n", "\r\n")
            _atomic_write(path, text.encode("utf-8"), previous=old)
    except (ObsidianExportError, FileExistsError, FileNotFoundError, UnicodeError):
        result.conflict_ids.append(note.lexeme_id)
        return
    result.written_ids.append(note.lexeme_id)


def _atomic_write(path: Path, data: bytes, *, previous: bytes | None = None) -> None:
    _checked(path.parent, directory=True, missing=False)
    descriptor, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".kindle-cards-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _checked(path.parent, directory=True, missing=False)
        if previous is None:
            if os.name == "nt":
                tmp.rename(path)  # Windows rename fails if the destination already exists.
            else:
                os.link(tmp, path)
        else:
            _checked(path, missing=False)
            if path.read_bytes() != previous:
                raise FileExistsError(path)
            tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
