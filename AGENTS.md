<!-- headroom:rtk-instructions -->
# RTK (Rust Token Killer) - Token-Optimized Commands

When running shell commands, **always prefix with `rtk`**. This reduces context
usage by 60-90% with zero behavior change. If rtk has no filter for a command,
it passes through unchanged — so it is always safe to use.

## Key Commands
```bash
# Git (59-80% savings)
rtk git status          rtk git diff            rtk git log

# Files & Search (60-75% savings)
rtk ls <path>           rtk read <file>         rtk grep <pattern>
rtk find <pattern>      rtk diff <file>

# Test (90-99% savings) — shows failures only
rtk pytest tests/       rtk cargo test          rtk test <cmd>

# Build & Lint (80-90% savings) — shows errors only
rtk tsc                 rtk lint                rtk cargo build
rtk prettier --check    rtk mypy                rtk ruff check

# Analysis (70-90% savings)
rtk err <cmd>           rtk log <file>          rtk json <file>
rtk summary <cmd>       rtk deps                rtk env

# GitHub (26-87% savings)
rtk gh pr view <n>      rtk gh run list         rtk gh issue list

# Infrastructure (85% savings)
rtk docker ps           rtk kubectl get         rtk docker logs <c>

# Package managers (70-90% savings)
rtk pip list            rtk pnpm install        rtk npm run <script>
```

## Rules
- In command chains, prefix each segment: `rtk git add . && rtk git commit -m "msg"`
- For debugging, use raw command without rtk prefix
- `rtk proxy <cmd>` runs command without filtering but tracks usage
<!-- /headroom:rtk-instructions -->

<!-- codex-agent-runtime:start -->

## Runtime Ports And Database Configuration

- Keep this section aligned with the root README when database names, ports, or service defaults change.
- Do not copy secrets from local `.env` files into commits; document only placeholders or compose defaults.

### Database
- Primary database: PostgreSQL.
- Default database name: `railway_recognition`.
- Default database port: `5432`.
- Default application URL: `postgresql+psycopg://deipss:<PASSWORD>@127.0.0.1:5432/railway_recognition`.
- PostgreSQL stores assets, tasks, labels, annotation versions, and queue state. Tests may override `DATABASE_URL` with temporary SQLite URLs.

### Default Ports
- Backend API: `8010` on the host in local docs; Compose maps host `8010` to container `8000`.
- Frontend Vite dev server: `4004`.
- PostgreSQL: `5432`.

### Notes For Codex Agents
- Redis is not required; PostgreSQL task rows are used for queue claiming.
- Before committing, check `git status --short --branch` and avoid staging unrelated runtime artifacts.

### Source Files Checked
- `backend/.env.example`
- `backend/app/core/config.py`
- `docker-compose.yml`
- `frontend/vite.config.ts`

<!-- codex-agent-runtime:end -->

## GitHub Commit Language

- Use English for all GitHub commit messages and pull/push related commit notes.
