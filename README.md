# dashpublish

Dashcam AI clip pipeline and YouTube publisher.

See the project plan for the full design. This is a work-in-progress greenfield
project. Package A (core: config, db, jobs, fakes) is implemented first; later
packages build ingest, LLM/compile, YouTube, API, SPA, and CLI on top.

## Quick start (development)

```bash
python -m uv venv --python 3.12
python -m uv pip install -e ".[dev]"
python -m uv run pytest
```
