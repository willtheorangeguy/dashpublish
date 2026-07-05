"""LLM provider errors."""

from __future__ import annotations


class LLMError(RuntimeError):
    """Raised when an LLM provider cannot produce usable output.

    Covers configuration problems (missing API key, unknown provider) and
    unrecoverable bad output (invalid JSON even after one retry).
    """
