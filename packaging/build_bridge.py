"""Build the self-contained Python bridge used by the installed desktop app.

Produces ``build/bridge/kindle-bridge/`` (PyInstaller one-folder build plus the
NLTK corpora the offline optimizer needs). One-folder keeps start-up fast,
which matters because the app starts the bridge for every action.

Usage (from the repository root, in the project's Python environment):
    python packaging/build_bridge.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
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
EXPANDED_MODEL_SHA256 = "a24e16fa43a22ab3cdb871b2bc16971997fe97ab1a35ce18ee53119090d96f75"
EXPANDED_SOURCE_SHA256 = "60bc1a8f30a8d41bc527a1ba5747508b030faf2e58df213bb341f490b59e15db"


def configure_build(output_dir: Path) -> None:
    global BUILD, DIST
    BUILD = output_dir.resolve()
    DIST = BUILD / "kindle-bridge"


def include_expanded_model(model: Path, notice: Path) -> None:
    model = model.resolve()
    notice = notice.resolve()
    if not model.is_file() or hashlib.sha256(model.read_bytes()).hexdigest() != EXPANDED_MODEL_SHA256:
        raise SystemExit("Expanded model is missing or has an unexpected SHA-256")
    if not notice.is_file() or not notice.read_text(encoding="utf-8").strip():
        raise SystemExit("A non-empty ranking model notice is required when bundling the model")
    try:
        with sqlite3.connect(f"{model.as_uri()}?mode=ro", uri=True) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            source = connection.execute("SELECT source_sha256 FROM provenance").fetchone()[0]
            connection.execute("SELECT share FROM coverage LIMIT 1").fetchone()
            connection.execute("SELECT spelling, headword FROM aliases LIMIT 1").fetchone()
    except sqlite3.Error as exc:
        raise SystemExit(f"Expanded model SQLite validation failed: {exc}") from exc
    if version != 1 or source != EXPANDED_SOURCE_SHA256:
        raise SystemExit("Expanded model provenance or schema does not match the pinned source")
    target = DIST / "models"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(model, target / "rp-v2-expanded.sqlite")
    shutil.copy2(notice, DIST / "ranking-model-notices.txt")


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


def _frozen(executable: Path, workspace: Path, action: str, payload: dict | None = None) -> dict:
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
        input=json.dumps({"action": action, "payload": payload or {}}, ensure_ascii=False),
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
    word_id = frozen["entries"][0]["id"]
    meaning = "мимолётное впечатление"
    _frozen(executable, frozen_ws, "save_card_edit", {"lexeme_id": word_id, "meaning_ru": meaning})
    saved = _frozen(executable, frozen_ws, "load_library")["entries"]
    if next(entry for entry in saved if entry["id"] == word_id)["card"]["meaning_ru"] != meaning:
        raise SystemExit("Frozen bridge failed the UTF-8 card edit round trip")
    print("smoke save_card_edit: UTF-8 preserved after restart", flush=True)


def _assert_no_model_in_bridge() -> None:
    model = DIST / "models" / "rp-v2-expanded.sqlite"
    if model.exists():
        raise SystemExit("Public bridge build must not contain the private expanded RP-V2 model")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=BUILD, help="isolated bridge build directory")
    parser.add_argument("--expanded-model", type=Path, help="opt in to bundling a pinned expanded RP-V2 SQLite model")
    parser.add_argument("--model-notice", type=Path, help="required attribution notice for --expanded-model")
    parser.add_argument("--public-release", action="store_true", help="assert the bridge is built without the private expanded model")
    args = parser.parse_args()
    if args.public_release and args.expanded_model:
        parser.error("--public-release cannot be combined with --expanded-model")
    if bool(args.expanded_model) != bool(args.model_notice):
        parser.error("--expanded-model and --model-notice must be supplied together")
    configure_build(args.output_dir)
    build_executable()
    prune()
    download_nltk_data()
    if args.expanded_model:
        include_expanded_model(args.expanded_model, args.model_notice)
    if args.public_release:
        _assert_no_model_in_bridge()
        print("Public release guard: private expanded RP-V2 model is excluded", flush=True)
    smoke_test()
    print(f"Bridge ready: {DIST}")


if __name__ == "__main__":
    main()
