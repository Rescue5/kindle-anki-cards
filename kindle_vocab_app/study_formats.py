"""Plain-text flashcards for the Quizlet and RemNote import forms."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from kindle_vocab_app import card_fields

_SEPARATORS = {"quizlet": "\t", "remnote": " >> "}
_CONTROLS = str.maketrans({code: " " for code in (*range(32), *range(127, 160), 0xFEFF)})
_LITERAL_MARKUP = str.maketrans("<>{}[]#*`_", "＜＞｛｝［］＃＊｀＿")
_DELIMITER_PUNCTUATION = str.maketrans("=:;+-~&", "＝：；＋－～＆")
_DELIMITER_PATTERNS = re.compile(r"={2,}|:{2,}|;{2,}|[;:-]-|\+{2,}|~{2,}|&(?:#[xX]?[\da-fA-F]+|[a-zA-Z]\w*);")
_LIST_MARKER = re.compile(r"^(?:[-+]\s|[0-9]+[.)](?=\s|$))")
_SPECIAL_ANSWER = re.compile(r"^(?:-|[0-9]+\.|[Aa]\))")
_MARKER_PUNCTUATION = str.maketrans("-+.)", "－＋．）")


def write_study_file(
    output_path: Path,
    destination: str,
    lexemes: list[dict[str, Any]],
    edits: Mapping[str, Mapping[str, Any]],
) -> None:
    """Write one card per line and atomically replace the caller's reserved output."""
    separator = _SEPARATORS.get(destination)
    if separator is None:
        raise ValueError(f"Unsupported study file destination: {destination}")

    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", delete=False,
            dir=output_path.parent, prefix=f".{output_path.name}.", suffix=".tmp",
        ) as stream:
            temporary = Path(stream.name)
            for lexeme in lexemes:
                front, back = _card_text(lexeme, edits.get(str(lexeme["id"])))
                if destination == "remnote":
                    front = _remnote_literal(front, _LIST_MARKER)
                    back = _remnote_literal(back, _SPECIAL_ANSWER)
                stream.write(f"{front}{separator}{back}\n")
        temporary.replace(output_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _card_text(lexeme: Mapping[str, Any], edit: Mapping[str, Any] | None) -> tuple[str, str]:
    card = card_fields.resolve(lexeme, edit)
    occurrence = card.occurrence
    front = (
        _single_line(occurrence.get("word"))
        or _single_line(lexeme.get("display_form"))
        or _single_line(lexeme.get("lemma"))
    )
    back = _single_line(card.meaning_ru) or "Перевод не добавлен"
    context = _single_line(occurrence.get("context"))
    if context:
        back = f"{back} · Пример: {context}"
    return front, back


def _single_line(value: Any) -> str:
    # The two importers take pasted text. Neither documents quoted multi-line fields.
    return " ".join(str(value or "").translate(_CONTROLS).split())


def _remnote_literal(text: str, leading_marker: re.Pattern[str]) -> str:
    # Use visible look-alikes so pasted user text cannot form a second card marker.
    text = _DELIMITER_PATTERNS.sub(lambda match: match[0].translate(_DELIMITER_PUNCTUATION), text)
    text = text.translate(_LITERAL_MARKUP)
    return leading_marker.sub(lambda match: match[0].translate(_MARKER_PUNCTUATION), text, count=1)
