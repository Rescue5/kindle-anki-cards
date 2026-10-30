"""Build the self-contained Python bridge used by the installed desktop app.

Produces ``build/bridge/kindle-bridge/`` (PyInstaller one-folder build plus the
NLTK corpora the offline optimizer needs). One-folder keeps start-up fast,
which matters because the app starts the bridge for every action.

Usage (from the repository root, in the project's Python environment):
    python packaging/build_bridge.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "bridge"
DIST = BUILD / "kindle-bridge"
# Only what the offline optimizer uses: lemmas/senses and the POS tagger.
NLTK_PACKAGES = ["wordnet", "averaged_perceptron_tagger_eng"]
# wordfreq ships frequency lists for ~40 languages; the optimizer queries English only.
WORDFREQ_KEEP = ("_en.msgpack.gz",)


def run(*args: str) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True)


def build_executable() -> None:
    run(
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onedir", "--console",
        "--name", "kindle-bridge",
        "--distpath", str(BUILD),
        "--workpath", str(BUILD / "work"),
        "--specpath", str(BUILD),
        "--paths", str(ROOT),
        "--collect-data", "kindle_vocab_app",
        "--collect-all", "wordfreq",
        "--collect-all", "langcodes",
        "--collect-data", "language_data",
        "--collect-data", "genanki",
        "--hidden-import", "keyring.backends.Windows",
        "--hidden-import", "keyring.backends.macOS",
        "--hidden-import", "win32com.client",
        "--hidden-import", "pythoncom",
        "--exclude-module", "tkinter",
        str(ROOT / "packaging" / "bridge_entry.py"),
    )


def prune() -> None:
    """Drop data the bridge never reads; it would only bloat the installer."""
    # PyInstaller's nltk hook copies whatever NLTK data exists on the build
    # machine; replace it with the pinned corpora downloaded below.
    shutil.rmtree(DIST / "_internal" / "nltk_data", ignore_errors=True)
    for path in (DIST / "_internal" / "wordfreq" / "data").iterdir():
        if path.is_file() and not path.name.endswith(WORDFREQ_KEEP):
            path.unlink()


def download_nltk_data() -> None:
    import nltk

    target = DIST / "_internal" / "nltk_data"
    target.mkdir(parents=True, exist_ok=True)
    for package in NLTK_PACKAGES:
        if not nltk.download(package, download_dir=str(target), quiet=True, raise_on_error=True):
            raise SystemExit(f"Failed to download NLTK package {package}")
    # Zipped copies are redundant once extracted; drop them to keep the installer small.
    for archive in target.rglob("*.zip"):
        if archive.with_suffix("").is_dir():
            archive.unlink()


def _frozen(executable: Path, workspace: Path, action: str) -> dict:
    # An empty APPDATA hides any NLTK data installed on the build machine, so
    # the check proves the bundled corpora are used, as on a clean computer.
    appdata = BUILD / "smoke-appdata"
    appdata.mkdir(parents=True, exist_ok=True)
    env = {
        "KINDLE_CARDS_WORKSPACE": str(workspace),
        "PYTHONUTF8": "1",
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "APPDATA": str(appdata),
        "USERPROFILE": str(appdata),
    }
    completed = subprocess.run(
        [str(executable)],
        input=json.dumps({"action": action, "payload": {}}),
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=300, check=False,
    )
    response = json.loads(completed.stdout)
    if not response.get("ok"):
        raise SystemExit(f"Smoke test {action} failed: {response.get('error')}\n{completed.stderr[-2000:]}")
    return response["result"]


def _seed_workspace(workspace: Path) -> None:
    sys.path.insert(0, str(ROOT))
    from kindle_vocab_app import tauri_bridge, vocab_cache
    from kindle_vocab_app.library_repository import repository_for

    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True)
    entries = tauri_bridge.demo_state()["entries"]
    catalog = vocab_cache.merge_kindle(vocab_cache.empty_catalog(), entries, sync_id="smoke")
    repository_for(workspace).save_catalog(catalog)


def smoke_test() -> None:
    """The frozen bridge must analyse words exactly like the development Python."""
    sys.path.insert(0, str(ROOT))
    from kindle_vocab_app.tauri_bridge import dispatch

    executable = DIST / ("kindle-bridge.exe" if sys.platform == "win32" else "kindle-bridge")
    frozen_ws, reference_ws = BUILD / "smoke-frozen", BUILD / "smoke-reference"
    for workspace in (frozen_ws, reference_ws):
        _seed_workspace(workspace)
    for action in ("load_demo", "llm_config"):
        _frozen(executable, frozen_ws, action)
        print(f"smoke {action}: ok", flush=True)

    frozen = _frozen(executable, frozen_ws, "process_queue")
    reference = dispatch("process_queue", {}, reference_ws)

    def analyses(result: dict) -> dict:
        drop = {"processed_at"}
        return {
            item["lemma"]: {k: v for k, v in (item["processing"]["analysis"] or {}).items() if k not in drop}
            for item in result["entries"]
        }

    if analyses(frozen) != analyses(reference):
        raise SystemExit(f"Frozen analysis differs:\n{analyses(frozen)}\n!=\n{analyses(reference)}")
    if not all(value.get("wordnet_synset_count") for value in analyses(frozen).values()):
        raise SystemExit("WordNet data is missing in the frozen bridge")
    print(f"smoke process_queue: ok ({len(frozen['entries'])} words identical to development Python)", flush=True)


if __name__ == "__main__":
    build_executable()
    prune()
    download_nltk_data()
    smoke_test()
    print(f"Bridge ready: {DIST}")
