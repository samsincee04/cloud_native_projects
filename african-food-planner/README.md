# African Food Planner

Plan weekly African meals from what you already have in the pantry. The app tracks ingredients, suggests recipes you can cook now (or almost cook), builds meal plans and shopping lists with sensible units, and delivers alerts through an in-app inbox fed by background jobs.

## Architecture

| Layer | Stack | Role |
|--------|--------|------|
| **Frontend** | Next.js 14 (single page, no extra routes) | Pantry, recipes, meal plan, shopping, cook-now, reminders; talks to the API at `NEXT_PUBLIC_API_URL` |
| **Backend** | FastAPI + SQLAlchemy | REST API: users, pantry, recipes, meal plans, shopping lists, substitutions, cook-now, nutrition estimates, notifications |
| **Worker** | Python (shared `app` package) | Scheduled-style jobs: expiry alerts, shopping-list refresh, weekly plan reminders → stored as **notifications** |
| **Database** | PostgreSQL 16 | Users, pantry, recipes, meal plans, shopping lists, notifications, etc. Schema via `create_tables()` + idempotent `ensure_*` helpers and SQL under `backend/migrations/` |

```
Browser (localhost:3000)
        │
        ▼
   Next.js frontend
        │
        ▼
   FastAPI backend (localhost:8000)
        │
        ├──► Postgres
        │
   Worker (manual / cron)
        └──► Postgres (notifications)
```

## Quick start

From the repo root:

```bash
cd infra
docker compose up --build
```

| Service | URL |
|---------|-----|
| App UI | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

Seed sample recipes (once the API is up):

```bash
curl -X POST http://localhost:8000/admin/seed_recipes
```

Optional: run background jobs manually (worker container exits after one shot on compose up):

```bash
docker compose exec worker python worker/run_daily.py
docker compose exec worker python worker/run_weekly.py
```

Environment (set in `infra/docker-compose.yml`):

- `DATABASE_URL` — Postgres connection for backend and worker
- `NEXT_PUBLIC_API_URL` — browser-facing API base (default `http://localhost:8000`)
- `RECIPES_SEED_PATH` — path to `data/recipes_seed.json` inside the backend container

## Demo flow (what to click)

1. **Open** http://localhost:3000  
2. **Create Profile** — stores a user id in the browser.  
3. **Inbox** (top card) — after running `run_daily.py`, unread alerts appear; use **Mark read** on each item. Empty state shows *No new alerts*.  
4. **Pantry**  
   - Add ingredients (name, quantity, unit, optional expiry date).  
   - Use **+** / **-** / **Consumed** for quick adjustments, or edit quantity/expiry and **Save**.  
   - Items with expiry show *expires in Xd* or *expired*.  
5. **Recipes**  
   - Pick a recipe from the dropdown.  
   - Try **Nutrition (rough)** and **Scale** for servings.  
   - Scroll down to **Add recipe** if you want a custom entry.  
6. **Meal Plan**  
   - Set **Week start (Mon)** (a Monday date).  
   - **Load plan** — loads an existing week, or start empty.  
   - **Auto-generate week** — uses pantry-aware dinner suggestions (servings + max missing).  
   - Or **Add to plan list** per day/meal, then **Save plan**.  
7. **Shopping**  
   - With a plan loaded, **Generate shopping list** (unit-aware totals, e.g. kg/L).  
   - Check off items; optional *Swap ideas* when substitutions exist.  
8. **Cook Now**  
   - **Load recommendations** — *Can cook now* vs *Almost* (missing chips + swap ideas).  
   - Click a recipe name to jump to **Recipes** detail.  
9. **Reminders** — legacy reminder list (separate from Inbox notifications); **Refresh reminders** and mark read as needed.

For a full weekly loop: seed recipes → fill pantry → auto-generate meal plan → generate shopping list → run daily worker → refresh Inbox for expiry/shopping notifications.
