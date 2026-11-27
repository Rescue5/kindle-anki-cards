"""Publish complete files despite a brief Windows sharing lock."""

import time
from pathlib import Path


def replace_file(source: Path, target: Path) -> None:
    for delay in (0.025, 0.05, 0.1, 0.2):
        try:
            source.replace(target)
        except OSError as error:
            # Windows can report a sharing lock as access denied.
            if getattr(error, "winerror", None) not in {5, 32, 33}:
                raise
            time.sleep(delay)
        else:
            return
    source.replace(target)
