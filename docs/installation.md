# dashpublish — Installation

## Requirements

| | |
|---|---|
| Python | 3.11 or 3.12 |
| [uv](https://docs.astral.sh/uv/) | Dependency management |
| Node | 20+, to build the SPA |
| [ffmpeg](https://ffmpeg.org/download.html) | On `PATH` — rendering and duration probing |
| [sentrysearch](https://github.com/ssrajadh/sentrysearch) | Semantic indexing; installed separately |

Everything except ffmpeg and sentrysearch can be skipped if you only want fake mode.

## Install

```bash
git clone https://github.com/willtheorangeguy/dashpublish.git
cd dashpublish
uv sync --extra dev
npm --prefix frontend ci
npm --prefix frontend run build
dashpublish init
```

`dashpublish init` writes `dashpublish.toml` if absent, migrates the database, seeds the
categories, checks for sentrysearch, and optionally runs the YouTube OAuth flow with
`--youtube`.

The SPA is built once and served as a static bundle by `dashpublish serve`.

## sentrysearch

```bash
uv tool install git+https://github.com/ssrajadh/sentrysearch
sentrysearch init
```

It does the semantic video indexing — chunking and embedding video into ChromaDB — and is an
external CLI rather than a library. Python 3.11+ and ffmpeg.

`dashpublish init` **warns without failing** if it is missing, so you can explore everything else
in fake mode first. That is the right default: sentrysearch is the component that costs money to
run.

## YouTube OAuth

1. Create a project in the [Google Cloud Console](https://console.cloud.google.com/).
2. Configure the OAuth consent screen — External is fine for personal use; add yourself as a test
   user while the app is unverified.
3. Create credentials of type **Desktop app** and download the client secrets JSON.
4. `export YOUTUBE_CLIENT_SECRETS=/path/to/secrets.json`
5. `dashpublish init --youtube`, or authenticate lazily on first `publish upload`.

A browser opens once; the refresh token is cached under `<data_dir>/tokens/youtube.json`.

Unverified OAuth apps are capped at 100 users, which is irrelevant for a personal tool and is why
Google's verification review is not worth pursuing.

## Verify

```bash
dashpublish --help
ffmpeg -version
DASHPUBLISH_FAKE=1 uv run dashpublish init
```

The third proves the whole install without needing keys or sentrysearch.

## Configuration

```bash
cp dashpublish.example.toml dashpublish.toml
cp .env.example .env
```

Non-secret settings in the TOML, secrets in the environment — see
[Configuration](./configuration.md).

## Docker

See [Deployment](./deployment.md).

## Uninstall

Remove the checkout and `~/.dashpublish` (or whatever `[general].data_dir` points at) — that
holds the database, clips, compilations, and the cached YouTube token.
