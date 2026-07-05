"""Logging setup for dashpublish."""

from __future__ import annotations

import logging

_CONFIGURED = False


def setup_logging(verbose: bool = False) -> None:
    """Configure stdlib logging with a concise console format.

    Idempotent: safe to call multiple times. ``verbose`` selects DEBUG vs INFO.
    """
    global _CONFIGURED
    level = logging.DEBUG if verbose else logging.INFO

    root = logging.getLogger()
    root.setLevel(level)

    if not _CONFIGURED:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root.addHandler(handler)
        _CONFIGURED = True
    else:
        for handler in root.handlers:
            handler.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
