# dashpublish — Troubleshooting

## `ffmpeg not found`

Install ffmpeg and put it on `PATH`, or set `FFMPEG_PATH` to the binary. It is needed both for
rendering compilations and for probing footage duration during `index`, so nothing works without
it.

## `sentrysearch` not found

It is a separate CLI:

```bash
uv tool install git+https://github.com/ssrajadh/sentrysearch
sentrysearch init
```

Python 3.11+ and ffmpeg. `dashpublish init` warns rather than failing, so you can still explore
everything with `DASHPUBLISH_FAKE=1`.

## A job is stuck in `planning` or `rendering`

```bash
dashpublish jobs
```

The job's `error` column carries the underlying cause — commonly a missing `GEMINI_API_KEY` or an
ffmpeg failure. Fix it and re-run `dashpublish compile`.

## The video stays private

Working as intended. `publish upload` cannot make anything public; run
`dashpublish publish go RECORD_ID`.

## "App not verified" during OAuth

Expected for a personal tool. Add yourself as a test user on the OAuth consent screen. Unverified
apps are capped at 100 users, and Google's verification review is not worth pursuing here.

## Docker: nothing gets indexed

Almost always `[general].footage_dir` pointing at a **host** path. Inside the containers it must
be `/data/footage`, which is where compose bind-mounts `./footage`.

The symptom is a container that runs happily and finds no files.

## Ollama unreachable from Docker

`localhost` inside a container is the container. Use `host.docker.internal` in
`[llm].ollama_url` to reach an Ollama server on the host — the example config notes this.

## Indexing is costing more than expected

Roughly $2.84 per hour of footage on the Gemini backend. A `watch` daemon on a directory that
keeps filling will keep spending.

Index a small folder first, or switch `[embeddings].backend` to `local`.

## Scan finds nothing

| Check | How |
|---|---|
| Is the footage indexed? | `dashpublish index` first; embeddings are what scan queries |
| Is the threshold too high? | `[scan].default_threshold`, and tune with `--dry-run` |
| Right category? | `dashpublish scan --category NAME` |

`--dry-run` uses a throwaway database, so experimenting costs nothing but time.

## Compile produces a video that is too short

The short profile caps at `[compile].short_max_s` and biases toward clips of 15 seconds or less;
the long profile targets `[compile].long_target_s`. If there are not enough starred clips, the
result is short — `--from top` uses the highest-scoring clips instead of only starred ones.

## The music drowns the clip audio

`[compile].music_duck_db` (default −12) is how far the music is pushed under the clip audio by
`sidechaincompress`. Make it more negative.

## The web UI is blank

The SPA must be built:

```bash
npm --prefix frontend ci && npm --prefix frontend run build
```

In Docker it is baked into the image at build time, so a blank UI there means the build stage
failed — check the build log rather than the runtime one.

## Two containers, one database, odd behaviour

`web` and `watch` share one SQLite file, and `watch` sets `DASHPUBLISH_NO_WORKER=1` so only
`web` drains the queue. If both were draining, or if `watch` had its own database, jobs would
appear to vanish.

## Still stuck

[Open an issue](https://github.com/willtheorangeguy/dashpublish/issues/new/choose) with the
output of `dashpublish jobs`, the relevant job's error, and whether you are in fake mode.
