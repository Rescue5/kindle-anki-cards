"""File locks shared by bridge processes using the same profile."""

from __future__ import annotations

import errno
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def exclusive_file_lock(
    path: Path, *, busy: Exception, prepare_failed: Exception, acquire_failed: Exception,
) -> Iterator[None]:
    # Keep the path fixed and let the OS release the lock when the descriptor closes.
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = path.open("ab")
    except OSError as exc:
        raise prepare_failed from exc
    with lock_file:
        try:
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise busy from exc
            raise acquire_failed from exc
        yield


@contextmanager
def enrichment_run_lock(workspace: Path) -> Iterator[None]:
    """Hold from candidate selection through the last saved enrichment result."""
    with exclusive_file_lock(
        workspace / ".app-data" / "enrichment.lock",
        busy=RuntimeError("Перевод уже выполняется в этой библиотеке. Дождитесь завершения"),
        prepare_failed=RuntimeError("Не удалось подготовить папку библиотеки для перевода"),
        acquire_failed=RuntimeError("Не удалось начать перевод в этой библиотеке"),
    ):
        yield
