"""Bring-your-own-key LLM providers used for contextual card enrichment."""

from __future__ import annotations


class LLMError(RuntimeError):
    """A provider failure with a user-facing (Russian) message.

    ``fatal`` errors (bad key, unknown model, no quota) stop a whole run because
    every following request would fail the same way. ``transient`` errors
    (timeouts) say nothing about the words, so they are not recorded as failed.
    """

    def __init__(self, message: str, *, fatal: bool = False, transient: bool = False) -> None:
        super().__init__(message)
        self.fatal = fatal
        self.transient = transient
