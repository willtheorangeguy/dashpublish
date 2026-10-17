# dashpublish — Deployment

## Docker compose

```bash
cp dashpublish.example.toml dashpublish.toml
# set [general].footage_dir = "/data/footage" — the path inside the containers
cp .env.example .env
# set GCP_PROJECT_ID to the project containing the published image
# fill in GEMINI_API_KEY / YOUTUBE_CLIENT_SECRETS

mkdir -p footage music
docker compose pull
docker compose up -d
```

Compose pulls `gcr.io/${GCP_PROJECT_ID}/dashpublish:latest`; set
`DASHPUBLISH_VERSION` in `.env` to a release tag to pin a specific version.
The release workflow builds and pushes both the release tag and `latest` to GCR.
Configure the repository variable `GCP_PROJECT_ID` and repository secret
`GCP_SA_KEY` (a service-account JSON key with permission to write to the
project's GCR registry) before publishing a GitHub release.

Two containers, one image, one named data volume:

| Container | Runs |
|---|---|
| `web` | `dashpublish serve` on `:8000`, with an in-process worker draining the queue |
| `watch` | `dashpublish watch`, polling `/data/footage` and enqueuing index/scan jobs |

`watch` sets `DASHPUBLISH_NO_WORKER=1`, so the jobs it enqueues are drained by `web`'s worker.
Both share one SQLite database.

The built SPA is baked into the image at `src/dashpublish/web` during the build, so `web` serves
the API and the UI from one process.

## `footage_dir` is a container path

The most common compose mistake: `[general].footage_dir` must be `/data/footage` — where the
compose file bind-mounts `./footage` — and **not** the host path. A host path in the TOML gives
you a container that indexes nothing and reports no error.

## There is no authentication

`dashpublish serve` has no login. Do not expose port 8000 beyond your own machine without a
reverse proxy that authenticates.

This matters more than for a typical self-hosted app: the cached OAuth token under
`<data_dir>/tokens/youtube.json` is a refresh token for your YouTube channel, and the API can use
it to upload. Anyone who can reach the port can put a video on your channel.

## Data

Everything lives under `[general].data_dir` in the named volume — the SQLite database, `clips/`,
`compilations/`, and `tokens/`. Back it up, and treat `tokens/` as a credential.

`docker compose down -v` removes it, including the OAuth token.

## Scaling

Two containers on one SQLite file works because writes are infrequent and there is a single
worker. More workers, or separate machines, would need a real database first.

## Costs in production

Indexing runs per hour of footage — roughly $2.84 on the default Gemini backend. A `watch`
daemon pointed at a directory that fills up continuously will spend continuously; that is worth
knowing before leaving it running against a live dashcam upload folder.

`[embeddings].backend = "local"` moves that cost to your own hardware.

## Updating

```bash
docker compose pull
docker compose up -d
```

Migrations run at start.
