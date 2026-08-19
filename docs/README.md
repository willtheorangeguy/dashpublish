# dashpublish — Documentation

A pipeline that turns a directory of dashcam footage into a published YouTube compilation, with
you in the loop at the two points that need judgement: which clips are worth keeping, and whether
the finished video should be public.

```
footage_dir  →  index  →  sentrysearch embeddings
                            ↓
                          scan (category queries)
                            ↓
                       clips table  →  web UI: star / hide
                            ↓
                    compile --profile short|long
                  (LLM edit decision list → ffmpeg)
                            ↓
                     publish upload   (YouTube, private)
                            ↓
                     you watch it
                            ↓
                     publish go       (public)
```

## Pages

- [Quickstart](./quickstart.md) — the whole pipeline, offline, in ten minutes
- [Installation](./installation.md) — uv, ffmpeg, sentrysearch, YouTube OAuth
- [Configuration](./configuration.md) — `dashpublish.toml` and the environment
- [Architecture](./architecture.md) — the stages, the job queue, the two processes
- [API](./api.md) — the CLI reference and the HTTP API
- [Development](./development.md) — tests, fake mode, layout
- [Deployment](./deployment.md) — Docker compose
- [FAQ](./faq.md) — cost, privacy, what to think about before publishing
- [Troubleshooting](./troubleshooting.md) — ffmpeg, OAuth, stuck jobs
- [Roadmap](./roadmap.md) — direction and non-goals
- [Known issues](./internal/known-issues.md) — recorded defects

## Publishing is deliberately two steps

`publish upload` sends the video to YouTube with `[youtube].default_privacy`, and that setting is
typed `Literal["private", "unlisted"]` — **`"public"` is not a value it will accept**. The only
path to a public video is the separate `publish go` command.

That is enforced by the type, not by convention, which is the right way to build a guard around
an irreversible action. Uploading the wrong compilation is recoverable; publishing it is much
less so.

## Fake mode

```bash
export DASHPUBLISH_FAKE=1
```

Replaces sentrysearch with an in-memory client, the LLM with deterministic synthetic output, and
YouTube with a simulator. The full `index → scan → compile → publish upload → publish go` path
runs with **no API keys and no network**.

It is how the test suite works, and it is the right way to explore the tool before spending
anything. See [Configuration](./configuration.md).

## Before you publish anything

Dashcam footage contains other people's vehicles, number plates, faces, and the roads outside
their homes — and the moments this tool is designed to surface are, by definition, the ones where
somebody did something badly. [FAQ](./faq.md) covers what is worth thinking about.
