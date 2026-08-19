# dashpublish — Development

## Setup

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src tests
```

## Fake mode is the development mode

```bash
export DASHPUBLISH_FAKE=1
```

sentrysearch becomes an in-memory client, the LLM returns deterministic EDLs and metadata, and
YouTube is simulated. The whole pipeline runs with no keys, no network, and no cost.

The test suite uses it throughout, so the tests exercise the **real** pipeline code with fake
boundaries — not mocks of the pipeline. That is what makes a suite covering
`index → scan → compile → publish upload → publish go` possible at all.

A few ffmpeg smoke tests under `tests/integration/` are gated on ffmpeg being present.

## Layout

```
src/dashpublish/
├── cli/        Typer commands, one module per group
├── api/        FastAPI app, routers/, deps, models
├── compile/    audio ducking, EDL types, the planner
├── youtube/    auth, upload, publish, service (+ FakeYouTube)
└── config.py   pydantic settings
frontend/       Vite + React SPA
tests/          unit and integration
```

## Conventions

- **Secrets in the environment, settings in TOML.** `config.py` never reads a secret from the
  file, and nothing writes one to it.
- **Every external service has a fake.** Adding one means adding its fake in the same change, or
  the suite stops being able to run offline.
- **Irreversible actions are typed.** `PrivacyStatus = Literal["private", "unlisted"]` is why
  `publish upload` cannot make a video public. Keep guards in the type system where the type
  system can hold them.
- **Long work goes through the job queue**, with progress and an error column, so both the CLI
  and the UI can report it.
- **`--dry-run` must not touch the real database.** `scan --dry-run` uses a throwaway one.

## Adding a detection category

Categories are seeded by `init` and live in the database, so a new one is a seed entry plus its
query text. `scan --category NAME` runs a single one, and `--dry-run` lets you tune the threshold
without writing anything.

## The frontend

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

The production build is baked into `src/dashpublish/web` at Docker build time, so `serve` hosts
API and UI from one process.

## Migrations

Alembic, configured in `alembic.ini`.

## Costs while developing

Indexing is the expensive step — roughly $2.84 per hour of footage on the default Gemini backend.
Use fake mode unless you are specifically testing the real embeddings path, and then use a short
clip.

## Recording defects

Bugs found while working here go in [`internal/known-issues.md`](./internal/known-issues.md)
rather than being fixed in passing, unless fixing them is the job you are on.
