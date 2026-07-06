"""Subprocess wrapper around the external ``sentrysearch`` CLI, plus a test fake.

``sentrysearch search`` overwrites ``~/.sentrysearch/last_search.json`` on every run,
so searches must be issued sequentially and results consumed immediately.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from dashpublish.db.schemas import SearchMatch
from dashpublish.logging import get_logger
from dashpublish.sentry.parse import parse_last_search, parse_stdout

logger = get_logger(__name__)


class SentrySearchError(RuntimeError):
    """The sentrysearch CLI failed."""


class SentrySearchNotFoundError(SentrySearchError):
    """The sentrysearch executable is not on PATH."""


def _tail(text: str, lines: int = 10) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


class SentrySearchClient:
    """Drives the ``sentrysearch`` CLI via subprocess."""

    def __init__(
        self,
        exe: str = "sentrysearch",
        backend: str | None = None,
        home: Path | None = None,
    ) -> None:
        self.exe = exe
        self.backend = backend
        self.home = home if home is not None else Path.home() / ".sentrysearch"

    # -- helpers ------------------------------------------------------------
    def ensure_installed(self) -> None:
        """Raise :class:`SentrySearchNotFoundError` if the CLI is missing."""
        if shutil.which(self.exe) is None:
            raise SentrySearchNotFoundError(
                f"'{self.exe}' not found on PATH. Install it with "
                "'uv tool install sentrysearch' (requires Python 3.11+ and FFmpeg) "
                "and run 'sentrysearch init'."
            )

    def _run(
        self, args: list[str], *, timeout_s: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        cmd = [self.exe, *args]
        logger.info("running: %s", " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_s
            )
        except FileNotFoundError as exc:
            raise SentrySearchNotFoundError(
                f"'{self.exe}' not found on PATH. Install it with "
                "'uv tool install sentrysearch'."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SentrySearchError(
                f"sentrysearch timed out after {timeout_s}s: {' '.join(cmd)}"
            ) from exc
        if proc.stdout:
            for line in proc.stdout.splitlines():
                logger.debug("sentrysearch: %s", line)
        if proc.returncode != 0:
            raise SentrySearchError(
                f"sentrysearch exited {proc.returncode}: {' '.join(cmd)}\n"
                f"{_tail(proc.stderr or proc.stdout)}"
            )
        return proc

    # -- commands -------------------------------------------------------------
    def index(
        self,
        path: str | Path,
        *,
        chunk_duration: int | None = None,
        overlap: int | None = None,
    ) -> None:
        """Index a file or directory into sentrysearch's embedding store.

        sentrysearch exits 0 even when every chunk fails to embed (failures go to
        its DLQ), so the output text is inspected: a missing-dependency error is
        fatal, and chunk-level embed failures are surfaced as errors here rather
        than reported as a clean index.
        """
        args = ["index", str(path)]
        if chunk_duration is not None:
            args += ["--chunk-duration", str(chunk_duration)]
        if overlap is not None:
            args += ["--overlap", str(overlap)]
        if self.backend:
            args += ["--backend", self.backend]
        proc = self._run(args)

        output = f"{proc.stdout or ''}\n{proc.stderr or ''}"
        if "Missing dependencies" in output:
            raise SentrySearchError(
                "sentrysearch cannot embed with this backend — missing optional "
                f"dependencies:\n{_tail(output)}\n"
                "(In Docker, rebuild with --build-arg SENTRYSEARCH_EXTRAS=local "
                "for the local backend, or switch [embeddings].backend to an API "
                "backend such as gemini.)"
            )
        if "recorded to DLQ" in output or "in DLQ" in output:
            raise SentrySearchError(
                f"sentrysearch failed to embed one or more chunks of {path} "
                f"(sent to its DLQ):\n{_tail(output)}\n"
                "(Re-run indexing after fixing the cause; sentrysearch retries "
                "DLQ'd chunks with --retry-failed.)"
            )

    def search(
        self,
        query: str,
        *,
        threshold: float,
        save_top: int,
        results: int = 10,
        dedupe: float | None = None,
        rerank: bool = False,
        timeout_s: float = 600,
    ) -> list[SearchMatch]:
        """Run one search and return parsed matches (may be empty).

        Prefers ``last_search.json`` when it was (re)written by this run; falls back
        to parsing the captured stdout.
        """
        args = [
            "search",
            query,
            "--results",
            str(results),
            "--save-top",
            str(save_top),
            "--threshold",
            str(threshold),
        ]
        if dedupe is not None:
            args += ["--dedupe", str(dedupe)]
        if rerank:
            args.append("--rerank")
        if self.backend:
            args += ["--backend", self.backend]

        started = time.time()
        proc = self._run(args, timeout_s=timeout_s)

        last_search = self.home / "last_search.json"
        try:
            fresh = (
                last_search.exists() and last_search.stat().st_mtime >= started - 1.0
            )
        except OSError:
            fresh = False
        if fresh:
            matches = parse_last_search(last_search)
            if matches:
                return matches
        return parse_stdout(proc.stdout or "")


class FakeSentryClient:
    """In-memory stand-in for :class:`SentrySearchClient` (fake mode / tests).

    ``matches`` maps a query substring to canned :class:`SearchMatch` lists; the first
    substring found in the query wins. Records all calls in ``indexed_paths`` and
    ``searches``.
    """

    def __init__(self, matches: dict[str, list[SearchMatch]] | None = None) -> None:
        self.matches = dict(matches or {})
        self.indexed_paths: list[str] = []
        self.searches: list[dict] = []
        self.fail_on: set[str] = set()  # query substrings that raise

    def ensure_installed(self) -> None:  # pragma: no cover - trivial
        return None

    def index(
        self,
        path: str | Path,
        *,
        chunk_duration: int | None = None,
        overlap: int | None = None,
    ) -> None:
        self.indexed_paths.append(str(path))

    def search(
        self,
        query: str,
        *,
        threshold: float,
        save_top: int,
        results: int = 10,
        dedupe: float | None = None,
        rerank: bool = False,
        timeout_s: float = 600,
    ) -> list[SearchMatch]:
        self.searches.append(
            {
                "query": query,
                "threshold": threshold,
                "save_top": save_top,
                "results": results,
                "dedupe": dedupe,
                "rerank": rerank,
            }
        )
        for substring in self.fail_on:
            if substring in query:
                raise SentrySearchError(f"fake failure for query: {query}")
        for substring, canned in self.matches.items():
            if substring in query:
                return [m.model_copy() for m in canned]
        return []
