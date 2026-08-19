# dashpublish — Quickstart

## Try it offline first

Fake mode runs the entire pipeline with no API keys, no network, and no cost:

```bash
export DASHPUBLISH_FAKE=1
uv sync --extra dev
uv run dashpublish init
uv run dashpublish index ./sample-footage
uv run dashpublish scan
uv run dashpublish compile --profile short --from starred --plan-only
uv run dashpublish serve
```

sentrysearch becomes an in-memory fake, the LLM returns deterministic edit decision lists, and
YouTube uploads are simulated. Nothing leaves the machine.

Do this before configuring anything real — indexing costs money, and this is how you find out
whether the tool suits you.

## The real pipeline

```bash
dashpublish init            # config, database, categories, optional YouTube OAuth
dashpublish index           # register and index footage
dashpublish scan            # run the category queries
dashpublish serve           # browse at :8000, star what is worth keeping
```

Then, once you have starred some clips:

```bash
dashpublish compile --profile short --from starred
dashpublish publish upload 1
# watch it on YouTube
dashpublish publish go 1
```

## What each step costs you

| Step | Cost |
|---|---|
| `index` | Embeddings — roughly **$2.84 per hour of footage** on sentrysearch's Gemini backend at default settings |
| `scan` | Query embeddings; cheap |
| `compile` | One LLM call to plan the edit |
| `publish` | Nothing |

Start with a small folder. A large backlog indexed at once is the expensive mistake.

## Curating

`dashpublish serve` is where the judgement happens: the scan finds candidates, and you decide
which are actually interesting. Star them, and `compile --from starred` uses those.

`--from top` uses the highest-scoring clips instead, if you would rather not curate.

## Two publish steps, on purpose

`publish upload` cannot make a video public — the privacy setting is typed to accept only
`private` or `unlisted`. `publish go` is the only path to public, and it is a separate command
you run after watching the result.

## Short or long

| | Short | Long |
|---|---|---|
| Aspect | 9:16, 1080×1920, centre crop | 16:9, 1920×1080, scale and pad |
| Duration | up to 60s | targets 300s |
| Segments | 2–10s | 4–30s |
| Title | `#Shorts` suffix guaranteed | plain |

Both keep each clip's original audio; `--music FILE` plays underneath, ducked with
`sidechaincompress`.

## Watching for new footage

```bash
dashpublish watch --interval 60
```

Polls the footage directory and enqueues index and scan jobs as files arrive.
