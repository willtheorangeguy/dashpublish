# dashpublish — API

Two surfaces: a CLI and an HTTP API. The web UI uses the second; both drive the same pipeline.

## CLI

Global options: `--config PATH` (overrides `DASHPUBLISH_CONFIG`) and `--verbose`.

| Command | Does |
|---|---|
| `init [--youtube]` | Write `dashpublish.toml` if absent, migrate, seed categories, check sentrysearch, optionally run the OAuth flow |
| `index [PATH]` | Register footage and index anything unindexed |
| `scan [--category NAME]... [--dry-run]` | Run category queries and persist clips |
| `clips list [--category] [--starred] [--json]` | List detected clips |
| `clips star ID [--unstar]` | Star or unstar |
| `compile --profile short\|long [--from starred\|top] [--clips IDs] [--music FILE] [--title T] [--plan-only]` | Plan an EDL and render |
| `publish upload COMP_ID [--title] [--description] [--tags a,b]` | Generate missing metadata, upload privately |
| `publish go RECORD_ID` | Make an uploaded video public |
| `jobs [--watch]` | List jobs; `--watch` polls until the queue drains |
| `serve [--host] [--port]` | FastAPI + SPA, with an in-process worker |
| `watch [--interval SECONDS]` | Poll footage and enqueue index/scan jobs |

### `scan --dry-run`

Uses a throwaway database and a fake client. It **never writes to the real database**, which
makes it safe to experiment with thresholds and categories.

### `compile --plan-only`

Prints the LLM's edit decision list as JSON and stops before rendering. The cheap way to see what
it intends.

### `publish upload` cannot publish

It uses `[youtube].default_privacy`, typed to accept only `private` or `unlisted`. `publish go`
is the only command that makes a video public.

## HTTP API

FastAPI, served by `dashpublish serve`, with routers per resource:

| Router | Covers |
|---|---|
| `videos` | Registered footage |
| `clips` | Detected clips, starring, hiding |
| `scans` | Running and inspecting scans |
| `compilations` | Planning, rendering, metadata |
| `publish` | Upload and go-public |
| `jobs` | Queue status and progress |
| `categories` | The detection categories |
| `settings` | Configuration surfaced to the UI |

`streaming.py` serves video ranges for previews in the browser.

Interactive documentation is at `/docs` when the server is running — FastAPI generates it from
the route signatures, so it is always current in a way this page cannot be.

## Authentication

**There is none.** `dashpublish serve` is intended to run on your own machine. Anything reachable
from elsewhere should sit behind a reverse proxy that authenticates — the API can start uploads
to your YouTube account using the cached OAuth token.

That last point is worth dwelling on: the token in `<data_dir>/tokens/youtube.json` is a refresh
token for your channel, and the API can act on it.

## External APIs

Gemini or DashScope for embeddings, Gemini or Ollama for planning, and the YouTube Data API for
upload and privacy. Costs and configuration are in [Configuration](./configuration.md).
