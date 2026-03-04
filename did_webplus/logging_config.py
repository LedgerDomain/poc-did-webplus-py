"""Logging configuration for did:webplus.

Log level is controlled by DID_WEBPLUS_LOG_LEVEL (or LOG_LEVEL).
Valid values: DEBUG, INFO, WARNING, ERROR, CRITICAL.
Default: WARNING.
"""

from __future__ import annotations

import logging
import os

_DID_WEBPLUS_LOGGER = "did_webplus"


def configure_logging() -> None:
    """Configure logging for did:webplus package from env."""
    level_str = (
        os.environ.get("DID_WEBPLUS_LOG_LEVEL") or os.environ.get("LOG_LEVEL") or "WARNING"
    ).upper()
    level = getattr(logging, level_str, logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger(_DID_WEBPLUS_LOGGER).setLevel(level)
