"""A reader-facing error that carries a code from `contracts.ERROR_CODES`.

`str(error)` is the Russian text the UI shows; the bridge puts `code` in the `{ok: false, ...}`
response so the UI can react to it (and Rust passes both on to the frontend).
"""

from __future__ import annotations

from kindle_vocab_app.contracts import ERROR_TEXTS


class CodedError(ValueError):
    def __init__(self, code: str, detail: str = "", *, text: str = "") -> None:
        if code not in ERROR_TEXTS:
            raise ValueError(f"Unknown error code: {code!r}")
        base = text or ERROR_TEXTS[code]
        super().__init__(f"{base}: {detail}" if detail else base)
        self.code = code
