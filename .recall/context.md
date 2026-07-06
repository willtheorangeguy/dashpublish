# Project Context — dashpublish (updated 2026-07-05)

_Hand-written by the session agent (the auto TextRank summary was noisy)._

## 🎯 Goal
Greenfield app, fully implemented this session: a Python CLI + web app that indexes dashcam footage with sentrysearch (semantic video search), detects interesting clips (overtaking, cut-off, high-speed…), surfaces them in a React web UI, LLM-plans and ffmpeg-renders short/long compilation videos, and publishes to YouTube (upload private → review in UI → publish public). Full approved plan: `C:\Users\Daniela Sada\.claude\plans\i-have-a-dashcam-splendid-phoenix.md`.

## 🧭 Summary
- Built in 7 packages by Opus/Sonnet subagents, integrated and verified by Fable: A core (config/SQLite/repos/job queue), B ingest+sentrysearch+scan, C LLM(Gemini/Ollama)+EDL+ffmpeg render, D YouTube, E FastAPI+worker, F React SPA, G CLI+watch+Docker+README.
- Verified: 174 tests + 1 skipped, ruff clean; offline fake-mode E2E (index → scan w/ dedupe → real ffmpeg 1080×1920 render → metadata → fake upload/publish); live server checks (SPA, Range streaming 206/416, ffmpeg thumbnails); Docker image builds and boots with real sentrysearch + ffmpeg inside.
- 8 commits on master (c8b55b0..fbab684), one per package + integration fixes.

## ⏭️ Next steps / open threads
- Nothing unimplemented. Not yet exercised live (needs user's keys): real GEMINI_API_KEY indexing/planning, real sentrysearch runs, YouTube OAuth (`dashpublish init --youtube`); README documents setup.
- Env quirks: uv only via `python -m uv`; venv is Python 3.12; ffmpeg via winget (FFMPEG_PATH honored); Docker Desktop daemon usually stopped.
- Known design notes: plan/render jobs ride job type "compile" with payload.action; compilation stuck-status safety net lives in jobs/tasks.py run_job; frontend sends EDL trims as trim_start/trim_end, API canonicalizes to *_s.

## 📂 Key files
- src/dashpublish/{db,ingest,sentry,llm,compile,metadata,youtube,jobs,api,cli,watch}/ — full pipeline
- frontend/ — Vite+React SPA (build output served by FastAPI)
- Dockerfile, docker-compose.yml (web + watch services), README.md
