"""Entry point of the frozen Python bridge shipped inside the desktop installer."""

from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller's NLTK runtime hook imports nltk before this script runs, so
    # NLTK_DATA would be read too late. Put the bundled corpora first explicitly;
    # otherwise a clean machine would silently run without WordNet.
    import nltk

    bundled = str(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "nltk_data")
    if bundled not in nltk.data.path:
        nltk.data.path.insert(0, bundled)

from kindle_vocab_app.tauri_bridge import main  # noqa: E402 - must follow the NLTK path setup

if __name__ == "__main__":
    raise SystemExit(main())
