# dashpublish frontend

React + Vite + TypeScript SPA (control center for the dashcam pipeline).

- Dev: `npm install` then `npm run dev` (Vite dev server on :5173, proxies `/api` to `http://localhost:8000` — run the FastAPI backend separately).
- Build: `npm run build` (runs `tsc -b` then `vite build`), output goes to `frontend/dist`.
- Typecheck only: `npx tsc --noEmit`.
- FastAPI serves `dist/index.html` for all non-`/api` routes (client-side routing via react-router).
