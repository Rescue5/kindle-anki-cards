"""Bring-your-own-key LLM providers used for contextual card enrichment."""

from __future__ import annotations


class LLMError(RuntimeError):
    """A provider failure with a user-facing (Russian) message.

    ``fatal`` errors (bad key, unknown model, no quota) stop a whole run because
    every following request would fail the same way.
    """

    def __init__(self, message: str, *, fatal: bool = False) -> None:
        super().__init__(message)
        self.fatal = fatal
