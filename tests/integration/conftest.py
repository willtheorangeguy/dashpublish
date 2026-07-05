"""Integration test configuration: register markers."""

from __future__ import annotations


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "ffmpeg: tests that run a real ffmpeg binary (skipped when absent)"
    )
