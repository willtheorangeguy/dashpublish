<!-- Logo -->
<h1 align="center">dashpublish</h1>

<!-- Copy -->
<h4 align="center">Finds the interesting moments in your dashcam footage, cuts them into a compilation, and publishes it to YouTube — private first, public only once you have watched it.</h4>

<!-- Badges -->
<div align="center">
  <img alt="GitHub Issues" src="https://img.shields.io/github/issues/willtheorangeguy/dashpublish">
  <img alt="GitHub Pull Requests" src="https://img.shields.io/github/issues-pr/willtheorangeguy/dashpublish">
  <img alt="License" src="https://img.shields.io/github/license/willtheorangeguy/dashpublish">
</div>

<!-- Navigation -->
<p align="center">
  <a href="#key-features">Key Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a> •
  <a href="#documentation">Documentation</a> •
  <a href="#support">Support</a> •
  <a href="#contributing">Contributing</a> •
  <a href="#credits">Credits</a> •
  <a href="#license">License</a>
</p>

## Key Features

- **Semantic search over video** — index dashcam footage and find overtaking, near misses, tailgating, crashes, and funny moments by describing them, not by tagging them.
- **A web UI for the part that needs judgement** — browse what was found, star what is worth keeping, hide what is not.
- **LLM-planned edits** — an edit decision list becomes an ffmpeg render: cropped and scaled to profile, concatenated, with music ducked under the clip audio.
- **Short and long profiles** — a 60-second vertical cut, or a five-minute compilation.
- **Publishes privately by default.** The upload path cannot make a video public; only the separate `publish go` step can.
- **Fake mode** — the whole pipeline runs offline with no API keys, for trying it or developing against it.
- CLI, web UI, and a `watch` daemon that indexes and scans new footage as it arrives.

## Installation

```bash
uv sync --extra dev
npm --prefix frontend ci && npm --prefix frontend run build
dashpublish init
```

Needs Python 3.11 or 3.12, [uv](https://docs.astral.sh/uv/), Node 20+, and [ffmpeg](https://ffmpeg.org/download.html). Semantic indexing needs [sentrysearch](https://github.com/ssrajadh/sentrysearch) installed separately. See [`docs/installation.md`](docs/installation.md).

## Usage

```bash
dashpublish index                        # register and index footage
dashpublish scan                         # find the interesting moments
dashpublish serve                        # browse and curate at :8000
dashpublish compile --profile short      # plan an EDL and render
dashpublish publish upload 1             # upload, privately
dashpublish publish go 1                 # make it public, once you have watched it
```

`DASHPUBLISH_FAKE=1` runs all of it with no API keys and no network — see [`docs/configuration.md`](docs/configuration.md).

## Documentation

Full documentation lives in [`docs/`](docs/README.md):
[Quickstart](docs/quickstart.md) · [Installation](docs/installation.md) · [Configuration](docs/configuration.md) · [Architecture](docs/architecture.md) · [API](docs/api.md) · [Development](docs/development.md) · [Deployment](docs/deployment.md) · [FAQ](docs/faq.md) · [Troubleshooting](docs/troubleshooting.md) · [Roadmap](docs/roadmap.md)

## Support

Open a [GitHub Discussion](https://github.com/willtheorangeguy/dashpublish/discussions/new) or file an [issue](https://github.com/willtheorangeguy/dashpublish/issues/new/choose).

## Contributing

Contributions welcome. See the org-wide [Contributing Guide](https://github.com/willtheorangeguy/.github/blob/main/CONTRIBUTING.md) and [Code of Conduct](https://github.com/willtheorangeguy/.github/blob/main/CODE_OF_CONDUCT.md).

## Credits

Semantic video indexing by [sentrysearch](https://github.com/ssrajadh/sentrysearch). Built with [FastAPI](https://fastapi.tiangolo.com/), [SQLAlchemy](https://www.sqlalchemy.org/), [Typer](https://typer.tiangolo.com/), [uv](https://docs.astral.sh/uv/), [Vite](https://vite.dev/), and [ffmpeg](https://ffmpeg.org/). Embeddings and edit planning via [Gemini](https://ai.google.dev/), [DashScope](https://www.alibabacloud.com/), or a local [Ollama](https://ollama.com/) model.

## License

MIT — see [`LICENSE.md`](LICENSE.md).

> You are publishing footage of public roads, other people's vehicles, and their number plates. [`docs/faq.md`](docs/faq.md) covers what that means before you press publish.
