# Sports News Noise Filter

Local RSS ingestion, clustering, and a minimal Next.js + FastAPI stack.

## Run Demo (Docker)

Prerequisites: [Docker](https://docs.docker.com/get-docker/) with Compose v2.

1. **Environment**

   From the `infra/` directory, copy the example env file and edit if needed. **Do not commit `.env`.**

   ```bash
   cd infra
   cp .env.example .env
   ```

2. **Start database, API, and UI**

   From **`infra/`** (same place as `.env`):

   ```bash
   cd infra
   docker compose up --build -d
   ```

   - Postgres: `localhost:${POSTGRES_PORT:-5432}` (default `5432`)
   - Backend: `http://localhost:${BACKEND_PORT:-8000}` (e.g. `GET /health`)
   - Frontend: `http://localhost:${FRONTEND_PORT:-3000}`

   Inside containers, the API uses **`DATABASE_URL`** with host **`db`** (not `localhost`). The frontend build embeds **`NEXT_PUBLIC_API_URL`** / **`NEXT_PUBLIC_API_BASE_URL`** as **`http://localhost:8000`** so your **browser** on the host can reach the published API port.

3. **Run the worker once (ingest RSS → DB)**

   The worker service uses **`profiles: [worker]`** so it is **not** started by `docker compose up`. Run it on demand:

   ```bash
   cd infra
   docker compose run --rm worker
   ```

   If your Compose version does not pick up the profile automatically, use:

   `docker compose --profile worker run --rm worker`

   This uses **`WORKER_DATABASE_URL`** (host **`db`**, not `localhost`) and reads `docs/rss_sources.md` from the image.

4. **Open the app and what to click**

   - Open **http://localhost:3000** (or your `FRONTEND_PORT`).
   - Under **Player Setup**, click **Create My Profile** (or use **Reset Profile** / **Create** again as needed).
   - Open **Preferences**, choose sports/topics, then **Save preferences**.
   - Open **Feed** to load clustered stories; click a card for detail.

5. **Stop**

   ```bash
   cd infra
   docker compose down
   ```

   To remove the database volume as well: `docker compose down -v`.

### Troubleshooting

- **`bind: address already in use` on port 3000** — Something else is using that port (e.g. local `npm run dev`). Either stop it (`lsof -i :3000` on macOS) or set `FRONTEND_PORT=3001` in `infra/.env`, run `docker compose up -d` again, and open `http://localhost:3001`.
