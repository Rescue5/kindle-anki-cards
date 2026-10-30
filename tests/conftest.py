"""Shared pytest configuration.

On Windows, antivirus and search indexers briefly hold freshly written files,
so removing a test's temporary directory can fail with "directory not empty"
after every assertion has already passed. Cleanup failures are not test
failures, so temporary directories ignore them there.
"""

from __future__ import annotations

import functools
import sys
import tempfile

if sys.platform == "win32":
    tempfile.TemporaryDirectory = functools.partial(  # type: ignore[misc]
        tempfile.TemporaryDirectory, ignore_cleanup_errors=True
    )
