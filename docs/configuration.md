# dashpublish — Configuration

Two places, on purpose: **non-secret settings in `dashpublish.toml`**, **secrets in the
environment**. Nothing sensitive is ever written to the TOML.

`dashpublish.example.toml` is the annotated template.

## `dashpublish.toml`

```toml
[general]
footage_dir = "./footage"       # where dashcam uploads land
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
category_id = "2"               # "2" = Autos & Vehicles
```

### `[youtube].default_privacy` cannot be `public`

It is typed `Literal["private", "unlisted"]`. Setting it to `"public"` is a configuration error,
not an option — the only path to a public video is `dashpublish publish go`.

That guard is in the type system rather than in a comment, which is what makes it reliable.

### `[embeddings].backend`

| Backend | Notes |
|---|---|
| `gemini` | Default, cheapest to start. Roughly **$2.84 per hour of footage** indexed |
| `dashscope` | Alternative hosted option |
| `local` | Qwen3-VL on your own hardware — no per-clip cost, needs a GPU |

This is the setting with a real bill attached. Index a small folder first.

### `[scan]`

`default_threshold` is the similarity cut-off, `save_top` how many matches to keep per category
per video, and `dedupe_window_s` how close two matches can be before they are treated as one
moment. `rerank` trades a little time for better ordering.

### `[compile]`

`short_max_s` and `long_target_s` set the two profiles' durations; `music_duck_db` is how far the
music is pushed under the clip audio by `sidechaincompress`.

## Environment

Secrets and toggles only — see `.env.example`:

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Required when `[llm].provider` or `[embeddings].backend` is `gemini` |
| `DASHSCOPE_API_KEY` | Required when `[embeddings].backend` is `dashscope` |
| `YOUTUBE_CLIENT_SECRETS` | Path to the OAuth Desktop-app client secrets JSON |
| `DASHPUBLISH_CONFIG` | Path to `dashpublish.toml` (default `./dashpublish.toml`) |
| `DASHPUBLISH_FAKE` | `1` runs everything offline with no keys |
| `DASHPUBLISH_NO_WORKER` | `1` disables the in-process job worker |

`.gitignore` covers `.env`, `/dashpublish.toml`, `/footage/`, `/music/`, and the sqlite files, so
none of your configuration or footage can be committed by accident.

## `DASHPUBLISH_FAKE`

Replaces sentrysearch with an in-memory client, the LLM with deterministic synthetic EDLs and
metadata, and YouTube with a simulator returning fake video ids. No network, no keys, no cost.

The test suite runs in this mode, so it exercises the real code paths end to end.

## `DASHPUBLISH_NO_WORKER`

Stops a process draining the job queue. The compose `watch` container sets it so that jobs it
enqueues are handled by the `web` container's worker — both share one SQLite database.
