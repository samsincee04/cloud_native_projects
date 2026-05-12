# Infrastructure — agents.md

## Docker Compose

- **Compose file:** `infra/docker-compose.yml` (run from `infra/`).
- **Env template:** `infra/.env.example` → copy to `infra/.env` (never commit `.env`).
- **Stack:** `db` (Postgres 16), `backend` (FastAPI), `frontend` (Next.js); **`worker`** is profiled / on-demand.

See the root **README.md** section **Run Demo (Docker)** for commands.
