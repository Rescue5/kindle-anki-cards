from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from kindle_vocab_app import obsidian_export
from kindle_vocab_app.obsidian_export import export_cards, managed_folder
from kindle_vocab_app.obsidian_sync import vault_operation_lock

PLUGIN = "obsidian-spaced-repetition"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / ".obsidian").mkdir()
    return tmp_path


def _settings(vault: Path, *, enabled: bool = True, **settings) -> Path:
    config = vault / ".obsidian"
    directory = config / "plugins" / PLUGIN
    directory.mkdir(parents=True, exist_ok=True)
    (config / "community-plugins.json").write_text(json.dumps([PLUGIN] if enabled else []), encoding="utf-8")
    path = directory / "data.json"
    path.write_text(json.dumps({"settings": settings, "scheduleData": {"version": 1}}), encoding="utf-8")
    return path


def _entry(lexeme: str = "alpha", level: int = 3) -> dict:
    return {
        "id": lexeme, "display_form": "glimpse", "study_priority": {"level": level},
        "dictionary": {"meaning_ru": "взгляд"},
        "occurrences": [
            {"id": "longest", "context": "This is the default and longer quotation."},
            {"id": "manual", "context": "My #no-sr :: [[quote]]."},
        ],
    }


def _single(vault: Path, entry: dict | None = None, **kwargs) -> obsidian_export.ObsidianExportResult:
    item = entry or _entry()
    return export_cards(vault, [item], note_keys={item["id"]: "stable-id"}, **kwargs)


def test_new_vault_repeat_and_open_folder(vault: Path) -> None:
    with pytest.raises(ValueError, match="ещё не создана"):
        managed_folder(vault)
    assert not (vault / "Kindle Cards").exists()
    result = _single(vault)
    assert result.written_ids == ["alpha"] and result.notices
    assert managed_folder(vault) == result.folder
    note, = result.folder.rglob("*.md")
    assert note.parent.name == "03" and note.name.startswith("glimpse--kc-")
    before = note.read_bytes()
    assert b"flashcards/kindle-cards/level-03" in before
    assert b"\nglimpse\n?\n" in before
    repeated = _single(vault)
    assert repeated.unchanged_ids == ["alpha"] and not repeated.written_ids
    assert note.read_bytes() == before


def test_disabled_plugin_keeps_custom_settings_and_resolves_manual_card(vault: Path) -> None:
    config = _settings(
        vault, enabled=False, flashcardTags=["#ignored", "#study/custom"],
        flashcardTagsToIgnore=["#ignored"], multilineCardSeparator="%%card%%", multilineCardEndMarker="%%end%%",
    )
    before = config.read_bytes()
    result = _single(vault, edits={"alpha": {"meaning_ru": "ручное значение", "example_occurrence_id": "manual"}})
    assert result.written_ids == ["alpha"] and result.notices
    note, = result.folder.rglob("*.md")
    text = note.read_text(encoding="utf-8")
    assert '"study/custom/kindle-cards/level-03"' in text
    assert "glimpse\n%%card%%\nручное значение<br>My " in text
    assert "::" not in text and "#no-sr" not in text and "[[quote]]" not in text
    assert "default" not in text and text.endswith("\n%%end%%\n")
    assert config.read_bytes() == before


@pytest.mark.parametrize("schedule", [
    " <!--SR:!2026-12-06,9,250-->",
    "\n<!--SR:!2026-12-06,9,250-->",
    "\n> [!sr|card-metadata] \n> <!--SR:!fsrs,2026-12-06,1,2,3,4,5,6,2.3-->",
])
def test_reexport_preserves_schedule_and_identity(vault: Path, schedule: str) -> None:
    _settings(vault, multilineCardEndMarker="%%end%%")
    result = _single(vault)
    note, = result.folder.rglob("*.md")
    scheduled = note.read_text(encoding="utf-8").replace("\n%%end%%\n", f"{schedule}\n%%end%%\n")
    note.write_bytes(scheduled.replace("\n", "\r\n").encode("utf-8"))
    result = _single(vault, _entry("new-canonical-id", level=1), edits={"new-canonical-id": {"meaning_ru": "новый"}})
    assert result.written_ids == ["new-canonical-id"] and not result.conflict_ids
    assert list(result.folder.rglob("*.md")) == [note]
    assert note.parent.name == "03" and result.notices
    assert "новый" in note.read_text(encoding="utf-8") and "level-01" in note.read_text(encoding="utf-8")
    assert schedule.replace("\n", "\r\n").encode("utf-8") in note.read_bytes()


def test_folder_decks_keep_path_and_follow_renames_inside_managed_folder(vault: Path) -> None:
    _settings(vault, convertFoldersToDecks=True, flashcardTags=[])
    result = _single(vault)
    original, = (result.folder / "03").glob("*.md")
    renamed = original.rename(original.with_name("renamed.md"))
    result = _single(vault, _entry(level=9))
    assert result.written_ids == ["alpha"] and result.notices
    assert "kindle_cards_level: 9" in renamed.read_text(encoding="utf-8")
    assert "tags:" not in renamed.read_text(encoding="utf-8")
    assert not (result.folder / "09").exists()


def test_manual_changes_and_external_schedule_are_conflicts(vault: Path) -> None:
    _settings(vault)
    result = _single(vault)
    note, = result.folder.rglob("*.md")
    pristine = note.read_bytes()
    note.write_bytes(pristine + b"My own notes.\n")
    assert _single(vault, _entry(level=2)).conflict_ids == ["alpha"]
    assert note.read_bytes().endswith(b"My own notes.\n")
    unknown = pristine + b"<!-- SR custom metadata -->\n"
    note.write_bytes(unknown)
    assert _single(vault, _entry(level=2)).conflict_ids == ["alpha"]
    assert note.read_bytes() == unknown
    note.write_bytes(pristine)
    _settings(vault, dataStore="PLUGIN_DATA")
    result = _single(vault, _entry(level=2))
    assert result.conflict_ids == ["alpha"] and result.notices
    assert note.read_bytes() == pristine


def test_ignored_paths_and_foreign_folder_are_preserved(vault: Path) -> None:
    _settings(vault, noteFoldersToIgnore=["**/*kc-*.md"])
    result = _single(vault)
    assert result.conflict_ids == ["alpha"] and result.notices
    assert not list(result.folder.rglob("*.md"))
    (result.folder / ".kindle-cards-owner").unlink()
    foreign = result.folder / "mine.md"
    foreign.write_bytes(b"my own note")
    with pytest.raises(ValueError, match="уже занята"):
        _single(vault)
    with pytest.raises(ValueError, match="не принадлежит"):
        managed_folder(vault)
    assert foreign.read_bytes() == b"my own note"


def test_missing_vault_marker_fails_before_writes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="папкой настроек"):
        _single(tmp_path)
    assert not list(tmp_path.iterdir())


def test_unique_custom_config_is_read_and_ambiguous_configs_are_refused(vault: Path) -> None:
    _settings(vault, multilineCardSeparator="%%card%%")
    (vault / ".obsidian").rename(vault / ".secondary-profile")
    result = _single(vault)
    note, = result.folder.rglob("*.md")
    before = note.read_bytes()
    assert b"\n%%card%%\n" in before and not result.notices
    (vault / ".obsidian").mkdir()
    with pytest.raises(ValueError, match="несколько папок настроек"):
        _single(vault, _entry(level=5))
    assert note.read_bytes() == before


def test_managed_junction_or_symlink_cannot_leave_vault(vault: Path) -> None:
    outside = vault / "unrelated"
    outside.mkdir()
    target = vault / "Kindle Cards"
    if os.name == "nt":
        created = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(target), str(outside)], check=False, capture_output=True,
        )
        if created.returncode != 0:
            pytest.skip("Junctions are not available in this filesystem")
    else:
        target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Небезопасный путь"):
        _single(vault)
    with pytest.raises(ValueError, match="Небезопасный путь"):
        managed_folder(vault)
    assert not list(outside.iterdir())


def test_vault_lock_is_shared(vault: Path) -> None:
    with vault_operation_lock(vault):
        with pytest.raises(ValueError, match="уже обновляется"):
            _single(vault)
        assert _single(vault, lock_held=True).written_ids == ["alpha"]


def test_foreign_lock_file_in_vault_is_untouched(vault: Path) -> None:
    foreign = vault / "foreign.txt"
    foreign.write_bytes(b"untouched")
    candidate = vault / ".kindle-cards-export.lock"
    os.link(foreign, candidate)
    info = foreign.stat()
    assert _single(vault).written_ids == ["alpha"]
    assert foreign.read_bytes() == candidate.read_bytes() == b"untouched"
    assert candidate.stat().st_ino == info.st_ino


def test_literal_text_has_no_flashcard_directives(vault: Path) -> None:
    item = _entry()
    item["display_form"] = "42. #hidden %%text%% ==secret=="
    item["occurrences"] = [{"context": "<!--SR:forged-->\n\n??\n::: [[target]] & <script>"}]
    folder = _single(vault, item).folder
    note, = folder.rglob("*.md")
    text = note.read_text(encoding="utf-8")
    assert text.count("\n?\n") == 1
    assert all(marker not in text for marker in ("#hidden", "%%", "==", "<!--SR:", ":::", "[[", "<script>"))


def test_interrupted_batch_can_resume_without_duplicate_notes(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = obsidian_export._atomic_write

    def fail_on_second(path: Path, *args, **kwargs) -> None:
        if path.suffix == ".md" and list(path.parent.glob("*.md")):
            raise OSError("test interruption")
        original(path, *args, **kwargs)

    entries = [_entry("alpha"), _entry("beta")]
    keys = {entry["id"]: entry["id"] for entry in entries}
    with monkeypatch.context() as patch:
        patch.setattr(obsidian_export, "_atomic_write", fail_on_second)
        with pytest.raises(OSError, match="test interruption"):
            export_cards(vault, entries, note_keys=keys)
    result = export_cards(vault, entries, note_keys=keys)
    assert result.unchanged_ids == ["alpha"] and result.written_ids == ["beta"]
    assert len(list(result.folder.rglob("*.md"))) == 2


def test_update_keeps_external_change_detected_before_replace(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _single(vault)
    note, = result.folder.rglob("*.md")
    reviewed = note.read_bytes().rstrip() + b"\n<!--SR:!2026-12-06,9,250-->\n"
    fsync = os.fsync

    def write_review(descriptor: int) -> None:
        fsync(descriptor)
        note.write_bytes(reviewed)

    monkeypatch.setattr(os, "fsync", write_review)
    result = _single(vault, _entry(level=1))
    assert result.conflict_ids == ["alpha"] and not result.written_ids
    assert note.read_bytes() == reviewed


@pytest.mark.parametrize("legacy_name", [False, True])
def test_filename_identity_prevents_copy_after_manual_metadata_removal(vault: Path, legacy_name: bool) -> None:
    entry = {**_entry(), "display_form": "AUX"}
    folder = _single(vault, entry).folder
    note, = folder.rglob("*.md")
    assert note.name.startswith("word-AUX--kc-")
    if legacy_name:
        note = note.rename(folder / note.name.split("--", 1)[1])
    manual = "Моя заметка\n".encode()
    note.write_bytes(manual)
    result = _single(vault, {**entry, "study_priority": {"level": 9}})
    assert result.conflict_ids == ["alpha"] and not result.written_ids
    assert list(folder.rglob("*.md")) == [note]
    assert note.read_bytes() == manual and not (folder / "09").exists()
