# dashpublish

Dashcam AI clip pipeline and YouTube publisher: index dashcam footage with
semantic video search, surface the interesting moments (overtaking, near
misses, tailgating, crashes, funny moments, ...) in a web UI, build a
compilation with an LLM-written edit decision list, and publish it to YouTube
— privately first, then public once you've reviewed it.

## Contents

- [What it is](#what-it-is)
- [Quick start (local)](#quick-start-local)
- [CLI reference](#cli-reference)
- [Configuration](#configuration)
- [sentrysearch install](#sentrysearch-install)
- [Docker](#docker)
- [Fake mode (offline demo)](#fake-mode-offline-demo)
- [Short vs long form](#short-vs-long-form)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## What it is

```
                         +--------------------+
  dashcam uploads  --->  |  footage_dir        |
  (Tesla events or       |  (mp4/mov tree)      |
   generic mp4/mov)      +----------+-----------+
                                    |
                                    v
                      dashpublish index / watch
                  (register_footage -> videos table)
                                    |
                                    v
                     sentrysearch index (embeddings)
                                    |
                                    v
                      dashpublish scan (category queries:
                    overtaking, near-miss, tailgating, crash, ...)
                                    |
                                    v
                           clips table (scored,
                         deduped, starred/hidden)
                                    |
                      web UI: browse / star / curate
                                    |
                                    v
                    dashpublish compile --profile short|long
              (LLM edit-decision-list -> ffmpeg render: crop/scale,
                  concat, optional music ducked under clip audio)
                                    |
                                    v
                        compilations table (rendered .mp4)
                                    |
                     web UI: review, edit metadata
                                    |
                                    v
                 dashpublish publish upload  (YouTube, private + AI title/
                                               description/tags)
                                    |
                      you review it on YouTube
                                    |
                                    v
                     dashpublish publish go   (flip to public)
```

Everything above the "web UI" steps is also driven from the CLI, and a
`dashpublish watch` daemon can run the index/scan steps automatically as new
footage arrives.

## Quick start (local)

Requires Python 3.11 or 3.12, [uv](https://docs.astral.sh/uv/), Node 20+ (to
build the SPA), and [ffmpeg](https://ffmpeg.org/download.html) on `PATH`.

```bash
# 1. Install dependencies (dev extras include pytest/ruff).
uv sync --extra dev

# 2. Build the web UI once (dashpublish serves it as a static bundle).
cd frontend && npm ci && npm run build && cd ..

# 3. Write dashpublish.toml, migrate the database, seed detection categories.
uv run dashpublish init

# 4. Point [general].footage_dir at your dashcam footage, then:
uv run dashpublish index      # register + embed new footage
uv run dashpublish scan       # run detection category queries -> clips

# 5. Start the web UI + API.
uv run dashpublish serve
# -> http://localhost:8000
```

In the web UI: **Library** shows detected clips (filter by category, star the
good ones); **Builder** creates a compilation from starred/top clips and lets
the LLM plan an EDL, which you can drag/trim/reorder before rendering;
**Review** plays the rendered file and lets you edit the AI-generated
title/description/tags before uploading (private) or publishing (public);
**Status** shows the job queue; **Settings** lets you change the embeddings
backend, LLM provider/model, and footage directory without editing the TOML.

No Gemini key or YouTube app yet? See [Fake mode](#fake-mode-offline-demo) to
try the whole pipeline offline first.

## CLI reference

Every command accepts the global options `--config PATH` (overrides
`DASHPUBLISH_CONFIG`) and `--verbose` (debug logging).

| Command | Description |
|---|---|
| `dashpublish init [--youtube]` | Write `dashpublish.toml` if absent, migrate the DB, seed categories, check for `sentrysearch`, optionally run the YouTube OAuth flow. |
| `dashpublish index [PATH]` | Register footage (default: `[general].footage_dir`) and index unindexed videos. |
| `dashpublish scan [--category NAME]... [--dry-run]` | Run detection category queries and persist matching clips; `--dry-run` uses a throwaway DB + fake client and never touches the real database. |
| `dashpublish clips list [--category] [--starred] [--json]` | List detected clips. |
| `dashpublish clips star ID [--unstar]` | Star (or unstar) a clip. |
| `dashpublish compile --profile short\|long [--from starred\|top] [--clips ID,ID] [--music FILE] [--title T] [--plan-only]` | Plan an LLM edit-decision-list and render it; `--plan-only` prints the EDL JSON and stops. |
| `dashpublish publish upload COMP_ID [--title] [--description] [--tags a,b]` | Generate any missing metadata from the compilation's EDL, then upload to YouTube (private by default). |
| `dashpublish publish go RECORD_ID` | Flip an uploaded video's privacy to public. |
| `dashpublish jobs [--watch]` | List recent jobs (id/type/status/progress/error); `--watch` polls every 2s until the queue drains. |
| `dashpublish serve [--host] [--port]` | Run the FastAPI + SPA server (uvicorn), with an in-process worker draining the job queue. |
| `dashpublish watch [--interval SECONDS]` | Poll the footage directory and enqueue index/scan jobs when new files appear. |

## Configuration

`dashpublish.toml` (see [`dashpublish.example.toml`](dashpublish.example.toml)
for the full template with comments) holds non-secret settings:

```toml
[general]
footage_dir = "./footage"      # where dashcam uploads land
data_dir = "~/.dashpublish"     # db.sqlite, clips/, compilations/, tokens/

[embeddings]
backend = "gemini"              # "gemini" | "dashscope" | "local"

[llm]
provider = "gemini"             # "gemini" | "ollama"
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
transition = "cut"              # "cut" | "crossfade"

[youtube]
default_privacy = "private"     # "private" | "unlisted"
category_id = "2"                # "2" = Autos & Vehicles
```

Secrets and runtime toggles are environment variables only (never written to
the TOML file) — see [`.env.example`](.env.example):

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Required if `[llm].provider` or `[embeddings].backend` is `gemini`. |
| `DASHSCOPE_API_KEY` | Required if `[embeddings].backend` is `dashscope`. |
| `YOUTUBE_CLIENT_SECRETS` | Path to the OAuth "Desktop app" client secrets JSON (see below). |
| `DASHPUBLISH_CONFIG` | Path to `dashpublish.toml` (default `./dashpublish.toml`). |
| `DASHPUBLISH_FAKE` | `1`/`true` enables fully offline [fake mode](#fake-mode-offline-demo). |
| `DASHPUBLISH_NO_WORKER` | `1` disables the in-process job worker (used by the `watch` container in compose). |

### YouTube OAuth setup

1. Create a project in the [Google Cloud Console](https://console.cloud.google.com/).
2. Configure the OAuth consent screen (External is fine for personal use; add
   yourself as a test user while the app is unverified).
3. Create OAuth credentials of type **Desktop app** and download the client
   secrets JSON.
4. Set `YOUTUBE_CLIENT_SECRETS` to that file's path and run
   `dashpublish init --youtube` (or authenticate lazily the first time you
   `publish upload`) — a browser window opens once; the refresh token is
   cached under `<data_dir>/tokens/youtube.json`.

## sentrysearch install

[sentrysearch](https://github.com/ssrajadh/sentrysearch) does the semantic
video indexing/search (chunks + embeds video into ChromaDB). It's an external
CLI, installed separately:

```bash
uv tool install git+https://github.com/ssrajadh/sentrysearch
sentrysearch init
```

Requires Python 3.11+ and ffmpeg. `dashpublish init` checks whether it's on
`PATH` and warns (without failing) if it isn't — you can still explore the
rest of the pipeline in [fake mode](#fake-mode-offline-demo) without it.

## Docker

```bash
cp dashpublish.example.toml dashpublish.toml
# edit dashpublish.toml: set [general].footage_dir = "/data/footage"
# (that's the path *inside* the containers, not a host path)
cp .env.example .env
# fill in GEMINI_API_KEY / YOUTUBE_CLIENT_SECRETS / etc.

mkdir -p footage music
docker compose up --build
```

This starts two containers sharing one image and one named data volume:

- `web` — `dashpublish serve` on `:8000`, with its own worker thread draining
  the job queue.
- `watch` — `dashpublish watch`, polling `/data/footage` (bind-mounted from
  `./footage`) and enqueuing `index`/`scan` jobs; it sets
  `DASHPUBLISH_NO_WORKER=1` so those jobs are left for `web`'s worker to
  drain (both containers share the same sqlite database).

The built React SPA is baked into the image at `src/dashpublish/web` during
the build (see the Dockerfile) so `web` serves API + UI from one process.

## Fake mode (offline demo)

Set `DASHPUBLISH_FAKE=1` to run the entire pipeline with no external services,
API keys, or network access: sentrysearch is replaced with an in-memory fake
client, the LLM provider returns deterministic synthetic EDLs/metadata, and
YouTube uploads are simulated (fake video ids, no network).

```bash
export DASHPUBLISH_FAKE=1
uv run dashpublish init
uv run dashpublish index ./sample-footage
uv run dashpublish scan
uv run dashpublish compile --profile short --from starred --plan-only
uv run dashpublish serve
```

This is also how the test suite exercises `index -> scan -> compile ->
publish upload -> publish go` end to end without any real keys.

## Short vs long form

| | Short | Long |
|---|---|---|
| Aspect / size | 9:16, 1080×1920 (center crop) | 16:9, 1920×1080 (scale + pad) |
| Duration | up to `[compile].short_max_s` (default 60s) | targets `[compile].long_target_s` (default 300s) |
| Segment length | 2-10s, biased toward clips ≤15s | 4-30s |
| Overlays | none | none (v1) |
| YouTube title | `#Shorts` suffix guaranteed | plain |

Both profiles keep each clip's original audio; an optional `--music FILE`
plays underneath, ducked via `sidechaincompress` (`[compile].music_duck_db`).

## Troubleshooting

- **`ffmpeg not found`** — install ffmpeg and put it on `PATH`, or set
  `FFMPEG_PATH` to the binary. Required for rendering compilations (and for
  probing footage duration during `index`).
- **YouTube video stuck private / "app not verified"** — unverified OAuth
  apps are capped at 100 users, and Google's review process for public apps
  is not worth it for a personal tool; publishing stays a manual, deliberate
  `dashpublish publish go` step for this reason. Add yourself as a test user
  on the OAuth consent screen.
- **`sentrysearch` not found / install fails** — it needs Python 3.11+ and
  ffmpeg; see [sentrysearch install](#sentrysearch-install). You can still
  demo everything else with `DASHPUBLISH_FAKE=1`.
- **Which embeddings backend?** — Gemini's embedding API is the default and
  cheapest to get started; DashScope is an alternative hosted option; "local"
  runs a Qwen3-VL model on your own hardware (no per-clip API cost, but needs
  a GPU). sentrysearch's Gemini backend runs roughly **~$2.84/hour** of
  footage indexed at default settings — budget accordingly for large
  backlogs, or start with a small folder.
- **Compilation stuck in `planning`/`rendering` with a job marked `error`** —
  check `dashpublish jobs`; the job's `error` column has the underlying
  cause (e.g. missing `GEMINI_API_KEY`, ffmpeg failure). Re-run
  `dashpublish compile` once it's fixed.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src tests
```

`DASHPUBLISH_FAKE=1` is used throughout the test suite so it runs fully
offline. A handful of ffmpeg smoke tests under `tests/integration/` are
gated on ffmpeg actually being present on `PATH`.
