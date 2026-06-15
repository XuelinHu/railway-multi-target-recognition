# Agent Instructions

## Git Workflow

- Every time the agent modifies files in this repository, it must commit the completed change and push it to the remote GitHub repository before finishing the task.
- Use clear commit messages that describe the actual change.
- Check `git status --short --branch` before committing to avoid including unrelated or generated files.
- Do not commit local runtime artifacts such as `node_modules/`, `.venv/`, `dist/`, logs, uploaded data, model weights, or `.env` files.

## Network And Startup

- This project uses FastAPI for the backend and Vue + Vite for the frontend.
- Local backend default port: `8000`.
- FRP backend public mapping: `47.120.48.245:18000-18010 -> 127.0.0.1:8000-8010`.
- FRP frontend public mapping: `47.120.48.245:14000-14010 -> 127.0.0.1:4000-4010`.
- Assigned frontend port for this project: `4004` (public FRP port `14004`).
- When exposing the frontend through FRP, prefer an unused local frontend port in `4000-4010` rather than Vite's default `5173`.
- When starting the frontend for FRP access, set `VITE_API_BASE_URL` to the backend address that the browser can reach.
