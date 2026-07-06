"""dashpublish command-line interface.

Global options (``--config``, ``--verbose``) apply to every subcommand and are
handled in the Typer callback below. Command groups:

- ``init``            — write dashpublish.toml, migrate + seed the database
- ``index``            — register footage and index unindexed videos
- ``scan``             — run detection category queries
- ``clips list/star``  — browse and curate detected clips
- ``compile``          — plan (LLM EDL) and render a compilation
- ``publish upload/go``— upload to YouTube and flip it public
- ``jobs``             — inspect the job queue
- ``serve``            — run the FastAPI + SPA server
- ``watch``            — poll footage and enqueue index/scan jobs
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Optional

import typer

from dashpublish.cli import clips as clips_cli
from dashpublish.cli import compile_cmd
from dashpublish.cli import publish as publish_cli
from dashpublish.cli._common import ensure_db, get_cfg, make_sentry_client
from dashpublish.config import DEFAULT_CONFIG_PATH, load_config, reset_config
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.ingest import register_footage
from dashpublish.jobs import queue
from dashpublish.logging import get_logger, setup_logging
from dashpublish.sentry import ensure_indexed, run_scan
from dashpublish.watch.daemon import watch_loop

__version__ = "0.1.0"

logger = get_logger(__name__)

app = typer.Typer(
    help="dashpublish — dashcam AI clip pipeline and YouTube publisher.",
    no_args_is_help=True,
)
app.add_typer(clips_cli.app, name="clips")
app.add_typer(publish_cli.app, name="publish")
app.command(name="compile")(compile_cmd.compile_)

# Fallback config template, used when no ./dashpublish.example.toml is available on
# disk to copy from (e.g. inside the Docker image, which does not ship it). Keep in
# sync with the repo-root dashpublish.example.toml.
_DEFAULT_TOML = """\
# dashpublish configuration.
# Secrets live in environment variables (see .env.example), never in this file.

[general]
# Directory where dashcam footage is uploaded / lives.
footage_dir = "./footage"
# Where dashpublish stores its database, clips, compilations, tokens, etc.
data_dir = "~/.dashpublish"

[embeddings]
# One of: "gemini", "dashscope", "local"
backend = "gemini"

[llm]
# One of: "gemini", "ollama"
provider = "gemini"
model = "gemini-2.5-flash"
ollama_url = "http://localhost:11434"
ollama_model = "llama3.1"

[scan]
default_threshold = 0.5
save_top = 3
dedupe_window_s = 3
rerank = true

[compile]
short_max_s = 60
long_target_s = 300
music_duck_db = -12
transition = "cut"

[youtube]
# One of: "private", "unlisted"
default_privacy = "private"
# YouTube category id; "2" = Autos & Vehicles.
category_id = "2"
"""


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"dashpublish {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    config: Optional[Path] = typer.Option(
        None, "--config", help="Path to dashpublish.toml (sets DASHPUBLISH_CONFIG)."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug logging."),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """dashpublish command-line interface."""
    if config is not None:
        os.environ["DASHPUBLISH_CONFIG"] = str(config)
        reset_config()
    setup_logging(verbose)


@app.command()
def init(
    youtube: bool = typer.Option(
        False, "--youtube", help="Run the YouTube OAuth browser flow after setup."
    ),
) -> None:
    """Write dashpublish.toml (if absent), migrate the database, and seed categories."""
    cfg_path = Path(os.environ.get("DASHPUBLISH_CONFIG", DEFAULT_CONFIG_PATH)).expanduser()
    if cfg_path.exists():
        typer.echo(f"Config already exists at {cfg_path}; leaving it unchanged.")
    else:
        example = Path("dashpublish.example.toml")
        content = example.read_text(encoding="utf-8") if example.exists() else _DEFAULT_TOML
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(content, encoding="utf-8")
        typer.echo(f"Wrote {cfg_path}")

    reset_config()
    cfg = load_config()
    db_path, paths = ensure_db(cfg)
    typer.echo(f"Database ready at {db_path}")

    if shutil.which("sentrysearch") is None:
        typer.echo(
            "WARNING: 'sentrysearch' was not found on PATH.\n"
            "  Install it with: uv tool install git+https://github.com/ssrajadh/sentrysearch\n"
            "  (requires Python 3.11+ and ffmpeg), then run 'sentrysearch init'."
        )
    else:
        typer.echo("sentrysearch found on PATH.")

    if youtube:
        if cfg.fake_mode:
            typer.echo("DASHPUBLISH_FAKE is set; skipping YouTube OAuth in fake mode.")
        elif not cfg.youtube_client_secrets:
            typer.echo(
                "YOUTUBE_CLIENT_SECRETS is not set; skipping YouTube OAuth. "
                "Set it and re-run 'dashpublish init --youtube'."
            )
        else:
            from dashpublish.youtube import get_credentials

            get_credentials(cfg.youtube_client_secrets, paths.tokens_dir, run_flow=True)
            typer.echo("YouTube OAuth complete; token saved.")

    typer.echo(
        "\nNext steps:\n"
        "  dashpublish index    # register footage\n"
        "  dashpublish scan     # run detection categories\n"
        "  dashpublish serve    # start the web UI + API"
    )


@app.command()
def index(
    path: Optional[Path] = typer.Argument(
        None, help="Footage directory (defaults to [general].footage_dir)."
    ),
) -> None:
    """Register footage files and index any unindexed videos."""
    cfg = get_cfg()
    db_path, _ = ensure_db(cfg)
    footage_dir = path or (Path(cfg.general.footage_dir) if cfg.general.footage_dir else None)
    if footage_dir is None:
        typer.echo("No footage directory given and [general].footage_dir is not set.", err=True)
        raise typer.Exit(1)

    client = make_sentry_client(cfg)
    with session_scope(db_path) as session:
        result = register_footage(session, footage_dir)
        typer.echo(
            f"Registered footage: {result.new} new, {result.seen} seen, {result.total} total"
        )
        indexed = ensure_indexed(session, client)
    typer.echo(f"Indexed {indexed} video(s)")


def _resolve_categories(session, names: list[str]) -> list | None:
    """Resolve ``--category`` names to Category rows, or None to mean "all enabled".

    Exits with status 1 if any given name is unknown.
    """
    if not names:
        return None
    cats = []
    for name in names:
        cat = repo.get_category_by_name(session, name)
        if cat is None:
            typer.echo(f"Unknown category: {name!r}", err=True)
            raise typer.Exit(1)
        cats.append(cat)
    return cats


@app.command()
def scan(
    category: list[str] = typer.Option(
        [], "--category", "-c", help="Limit to this category (repeatable)."
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help=(
            "Use a throwaway database and a fake sentry client; the real database "
            "is left untouched."
        ),
    ),
) -> None:
    """Run detection category queries and persist matching clips."""
    cfg = get_cfg()

    if dry_run:
        import tempfile

        from dashpublish.db.engine import create_all_for_tests, get_engine
        from dashpublish.sentry import FakeSentryClient

        tmp_dir = Path(tempfile.mkdtemp(prefix="dashpublish-dryrun-"))
        tmp_db_path = str(tmp_dir / "dryrun.sqlite")
        create_all_for_tests(get_engine(tmp_db_path))
        client = FakeSentryClient()
        try:
            with session_scope(tmp_db_path) as session:
                repo.seed_default_categories(session)
                cats = _resolve_categories(session, category)
                result = run_scan(
                    session, client, tmp_dir / "clips", categories=cats, scan_cfg=cfg.scan
                )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        typer.echo(
            f"[dry-run] clips_found={result.clips_found} "
            f"categories_run={result.categories_run} errors={len(result.errors)}"
        )
        for err in result.errors:
            typer.echo(f"  error: {err}")
        if result.errors:
            raise typer.Exit(2)
        return

    db_path, paths = ensure_db(cfg)
    client = make_sentry_client(cfg)
    with session_scope(db_path) as session:
        cats = _resolve_categories(session, category)
        ensure_indexed(session, client)
        result = run_scan(session, client, paths.clips_dir, categories=cats, scan_cfg=cfg.scan)

    typer.echo(
        f"clips_found={result.clips_found} categories_run={result.categories_run} "
        f"errors={len(result.errors)}"
    )
    for err in result.errors:
        typer.echo(f"  error: {err}")
    if result.errors:
        raise typer.Exit(2)


@app.command()
def jobs(
    watch: bool = typer.Option(
        False, "--watch", help="Poll every 2s until the queue is empty."
    ),
) -> None:
    """List recent jobs (id / type / status / progress / error)."""
    cfg = get_cfg()
    db_path, _ = ensure_db(cfg)

    def _print() -> list:
        with session_scope(db_path) as session:
            rows = queue.list_jobs(session)
        if not rows:
            typer.echo("No jobs.")
        for j in rows[:20]:
            detail = j.error or j.message or ""
            typer.echo(f"[{j.id:>4}] {j.type:<8} {j.status:<8} {j.progress:>5.0%}  {detail}")
        return rows

    rows = _print()
    if not watch:
        return
    while any(j.status in ("queued", "running") for j in rows):
        time.sleep(2)
        rows = _print()


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Run the FastAPI + SPA server (uvicorn)."""
    import uvicorn

    uvicorn.run("dashpublish.api.app:app", host=host, port=port)


@app.command()
def watch(
    interval: int = typer.Option(60, "--interval", help="Seconds between footage polls."),
) -> None:
    """Poll the footage directory and enqueue index/scan jobs when new files appear."""
    cfg = get_cfg()
    db_path, _ = ensure_db(cfg)
    typer.echo(f"Config: {cfg.config_path or 'built-in defaults (no dashpublish.toml found)'}")
    typer.echo(f"Watching {cfg.general.footage_dir!r} every {interval}s (Ctrl+C to stop)")
    watch_loop(cfg, db_path, interval_s=interval)
    typer.echo("Watch daemon stopped.")


if __name__ == "__main__":
    app()
