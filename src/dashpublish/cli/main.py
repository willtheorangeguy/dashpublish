"""Minimal Typer CLI stub. Package G replaces this with the full command set."""

from __future__ import annotations

import typer

__version__ = "0.1.0"

app = typer.Typer(help="dashpublish — dashcam AI clip pipeline and YouTube publisher.")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"dashpublish {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """dashpublish command-line interface."""


if __name__ == "__main__":
    app()
