"""Render the Anki note template with sample data to HTML for README screenshots.

Usage: python packaging/render_card_preview.py build/card-preview.html
The output is a static page; capture it with any headless browser.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kindle_vocab_app import anki_export  # noqa: E402 - repository import for a standalone script

SAMPLE = {
    "id": "sample-dread",
    "lemma": "dread",
    "display_form": "dread",
    "forms": ["dread"],
    "occurrences": [
        {
            "word": "dread",
            "context": "A quiet dread settled over the room.",
            "book_title": "Shadows and Signals",
            "authors": "Demo Library",
        }
    ],
    "processing": {"state": "ready", "analysis": {"base_form": "dread", "pos": "n", "accepted": True, "importance_score": 7}},
    "enrichment": {
        "status": "ready",
        "meaning_ru": "страх; тревожное предчувствие",
        "definition_en": "a strong fear of something that may happen",
        "context_ru": "Комнату накрыл тихий страх.",
        "example_en": "She thought about the exam with dread.",
        "example_ru": "Она думала об экзамене со страхом.",
    },
}


def render(template: str, fields: dict[str, str]) -> str:
    """Minimal Anki template rendering: {{#Field}}…{{/Field}} sections and {{Field}}."""
    def section(match: re.Match[str]) -> str:
        return match.group(2) if fields.get(match.group(1)) else ""

    previous = None
    while previous != template:
        previous = template
        template = re.sub(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", section, template, flags=re.DOTALL)
    return re.sub(r"\{\{(\w+)\}\}", lambda match: fields.get(match.group(1), ""), template)


def main(output: Path) -> None:
    fields = anki_export.build_note_fields(SAMPLE)
    back = render(anki_export.BACK, fields)
    page = f"""<!doctype html><html><head><meta charset="utf-8"><style>{anki_export.CSS}
body {{ margin: 0; padding: 36px 24px; }}</style></head>
<body class="card">{back}</body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "card-preview.html")
