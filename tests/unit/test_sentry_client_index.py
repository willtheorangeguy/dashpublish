"""SentrySearchClient.index must surface embed failures that sentrysearch hides.

The upstream CLI exits 0 even when every chunk fails to embed (failures land in
its DLQ), so the client inspects the output text.
"""

from __future__ import annotations

import subprocess

import pytest

from dashpublish.sentry.client import SentrySearchClient, SentrySearchError


def _fake_run(stdout: str):
    def runner(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    return runner


def test_index_raises_on_missing_dependencies(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_run(
            "Auto-detected model: qwen8b\n"
            "  Failed after 3 attempt(s), recorded to DLQ: Missing dependencies "
            "for local backend: No module named 'torch'\n"
            "Indexed 0 new chunks from 0 files. Total: 0 chunks from 0 files.\n"
        ),
    )
    with pytest.raises(SentrySearchError, match="missing optional"):
        SentrySearchClient(backend="local").index("/data/footage")


def test_index_raises_on_dlq_failures(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_run(
            "Indexing file 1/1: a.mp4 [chunk 1/1]\n"
            "  Failed after 3 attempt(s), recorded to DLQ: connection reset\n"
            "Indexed 0 new chunks from 0 files. Total: 0 chunks from 0 files.\n"
        ),
    )
    with pytest.raises(SentrySearchError, match="DLQ"):
        SentrySearchClient().index("/data/footage")


def test_index_clean_run_passes(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_run("Indexed 12 new chunks from 3 files. Total: 12 chunks from 3 files.\n"),
    )
    SentrySearchClient().index("/data/footage")  # must not raise
