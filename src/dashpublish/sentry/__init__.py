"""sentrysearch integration: CLI client, output parsers, detection scan (Package B)."""

from dashpublish.sentry.client import (
    FakeSentryClient,
    SentrySearchClient,
    SentrySearchError,
    SentrySearchNotFoundError,
)
from dashpublish.sentry.parse import parse_last_search, parse_stdout, ts_to_seconds
from dashpublish.sentry.scan import ScanResult, ensure_indexed, run_scan

__all__ = [
    "FakeSentryClient",
    "ScanResult",
    "SentrySearchClient",
    "SentrySearchError",
    "SentrySearchNotFoundError",
    "ensure_indexed",
    "parse_last_search",
    "parse_stdout",
    "run_scan",
    "ts_to_seconds",
]
