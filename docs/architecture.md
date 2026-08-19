# dashpublish — Architecture

A staged pipeline with a job queue, driven equally from a CLI and a web UI.

```
footage_dir
   └── index      register_footage → videos table
          └── sentrysearch index   → embeddings (ChromaDB)
                 └── scan          category queries → clips table
                        └── web UI  star / hide
                               └── compile  LLM edit decision list → ffmpeg → compilations
                                      └── publish upload  → YouTube (private)
                                             └── publish go → public
```

## Layout

```
src/dashpublish/
├── cli/          Typer commands
├── api/          FastAPI app, routers, deps
├── compile/      audio, edl, planner
├── youtube/      auth, upload, publish, service, and a fake
├── config.py     pydantic settings
└── web/          the built SPA, baked in at Docker build time
frontend/         the SPA source (Vite + React)
```

About 6,600 lines of Python.

## The job queue

Long operations — index, scan, compile, upload — run as jobs with status, progress, and an error
column. `dashpublish jobs [--watch]` lists them; the web UI polls them.

A worker runs **in-process** inside `dashpublish serve`, which keeps a single-machine deployment
to one process. `DASHPUBLISH_NO_WORKER=1` disables it, which is how the compose `watch` container
enqueues work for the `web` container to drain — both sharing one SQLite database.

## Stages

**index** registers footage into the `videos` table and hands it to sentrysearch for embedding.
ffmpeg probes duration.

**scan** runs the category queries — overtaking, near miss, tailgating, crash, and the rest —
against the embeddings, scoring and deduplicating matches into the `clips` table.
`--dry-run` uses a throwaway database and a fake client, so it **never touches the real data**;
that is worth knowing, since scan is the step you will want to experiment with.

**compile** asks the LLM for an edit decision list, then renders it with ffmpeg: crop or scale to
the profile, concatenate, and optionally duck music under the clip audio. `--plan-only` prints
the EDL and stops.

**publish** uploads and, separately, makes public.

## The publish guard

```python
PrivacyStatus = Literal["private", "unlisted"]
```

`upload_compilation` uses `cfg.youtube.default_privacy`, whose type cannot express `"public"`.
The only call that sets public is in `publish()`, reached solely by `dashpublish publish go`.

So the "private first" promise is enforced by the type system rather than by discipline — the
right way to guard a step that cannot be undone. `upload_compilation` separately refuses a
compilation that is not in status `rendered` with a file that exists.

## The web layer

FastAPI with routers per resource — videos, clips, scans, compilations, publish, jobs,
categories, settings — plus `streaming.py` for video previews. The built SPA is served from the
same process, so `serve` is one port and one thing to run.

## Fake mode

`DASHPUBLISH_FAKE=1` swaps in `youtube/service.py`'s `FakeYouTube`, an in-memory sentrysearch
client, and a deterministic LLM. Every stage runs, so the tests exercise real code paths rather
than mocks of them — which is why the suite can cover
`index → scan → compile → publish upload → publish go` without a key.

## Data

SQLite under `[general].data_dir`, alongside `clips/`, `compilations/`, and `tokens/`. Alembic
migrations (`alembic.ini`).

Two containers sharing one SQLite file works because the write volume is low and the worker is
single; it is the thing to revisit before scaling out.

## External dependencies

| Component | Role |
|---|---|
| sentrysearch | Semantic video indexing and search |
| Gemini / DashScope / local | Embeddings |
| Gemini / Ollama | Edit planning and metadata |
| ffmpeg | Probing and rendering |
| YouTube Data API | Upload and privacy |

All of them are replaceable by fakes, which is what makes the pipeline testable.
