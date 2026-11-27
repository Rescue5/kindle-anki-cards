"""Run the current Windows source tree against a persistent development profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from kindle_vocab_app.doctor import check_command, npm_command
from kindle_vocab_app.workspace_lock import exclusive_file_lock
from scripts.dev_profile import prepare_profile

ROOT = Path(__file__).resolve().parents[1]
PORT = 1476
PROFILE_MESSAGES = {
    "created": "Создан новый тестовый профиль.",
    "copied": "Скопированы существующая библиотека и настройки. Автоперевод в тестовом профиле выключен.",
    "existing": "Открывается существующий тестовый профиль.",
}


def run(workspace: Path, *, seed: bool) -> int:
    npm = npm_command()
    if npm is None or not (ROOT / "node_modules" / ".bin" / "tauri.cmd").is_file():
        raise RuntimeError("Подготовьте среду разработки командой .\\scripts\\setup-dev.ps1.")
    cargo = check_command("cargo", ["cargo", "--version"])
    if not cargo.ok:
        raise RuntimeError(f"Cargo недоступен в среде разработки. {cargo.detail}")

    installed = Path(os.environ["APPDATA"]) / "com.kindlevocab.cards"
    installed_model = Path(os.environ["LOCALAPPDATA"]) / "Kindle Cards" / "bridge" / "models" / "rp-v2-expanded.sqlite"
    previous_source = ROOT if not (installed / ".app-data" / "kindle_cards.sqlite3").is_file() else installed
    model = installed_model if installed_model.is_file() else ROOT / ".app-data" / "models" / installed_model.name
    installed = installed.resolve()
    if workspace == installed or workspace in installed.parents or installed in workspace.parents:
        raise RuntimeError("Для запуска из исходников используйте отдельную папку профиля.")

    with exclusive_file_lock(
        workspace / ".kindle-cards-dev.lock",
        busy=RuntimeError("Этот тестовый профиль уже открыт."),
        prepare_failed=RuntimeError("Не удалось подготовить папку тестового профиля."),
        acquire_failed=RuntimeError("Не удалось заблокировать тестовый профиль."),
    ):
        state = prepare_profile(workspace, previous_source, seed=seed, bundled_model=model if model.is_file() else None)
        print(PROFILE_MESSAGES[state], flush=True)
        print(f"Профиль: {workspace}", flush=True)

        config = workspace / "tauri-dev.json"
        config.write_text(json.dumps({
            "identifier": "com.kindlevocab.cards.dev",
            "build": {
                "beforeDevCommand": f"npm run dev -- --port {PORT} --strictPort --configLoader runner",
                "devUrl": f"http://127.0.0.1:{PORT}",
            },
            "app": {"windows": [{"title": "Kindle Cards (Dev)", "width": 1320, "height": 840, "minWidth": 600, "minHeight": 720}]},
        }), encoding="utf-8")
        env = os.environ.copy()
        env["KINDLE_CARDS_WORKSPACE"] = str(workspace)
        env["KINDLE_CARDS_PYTHON"] = sys.executable
        profile_id = hashlib.sha256(os.path.normcase(str(workspace)).encode()).hexdigest()[:16]
        env["KINDLE_CARDS_KEYRING_SERVICE"] = f"kindle-cards-dev-{profile_id}"
        env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT), env.get("PYTHONPATH"))))
        env["WEBVIEW2_USER_DATA_FOLDER"] = str(workspace / "WebView2")
        env.setdefault("CARGO_TARGET_DIR", str(ROOT / "build" / "cargo-target"))
        # Match the Windows build profile already used successfully by the local toolchain.
        env.setdefault("CARGO_PROFILE_RELEASE_BUILD_OVERRIDE_DEBUG", "true")
        return subprocess.call(
            [npm, "run", "tauri", "--", "dev", "--release", "--config", str(config)],
            cwd=ROOT,
            env=env,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(os.environ["LOCALAPPDATA"]) / "Kindle Cards Dev")
    parser.add_argument("--empty-profile", action="store_true", help="skip copying an existing library on first launch")
    args = parser.parse_args()
    try:
        return run(args.workspace.resolve(), seed=not args.empty_profile)
    except (OSError, RuntimeError) as error:
        print(f"Не удалось запустить Kindle Cards: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
