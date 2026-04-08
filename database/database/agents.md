Objective:
Add PostgreSQL-backed persistence to the existing summarize application.
Hard Constraints:
- Use SQLAlchemy Core for database access.
- Database queries must be written as explicit SQL strings (e.g., text-based queries).
- Do not define ORM models or use SQLAlchemy ORM sessions.
- Do not refactor unrelated code.
- Do not change existing API behavior.
- All database access must use SQL executed from Python.
- PostgreSQL must run as a Docker container managed by Docker Compose.
- Database configuration must use environment variables.
Database / Container Constraints:
- Add a PostgreSQL service to docker-compose.yml.
- Use a Docker volume so database data persists across container restarts.
- The backend must connect to PostgreSQL using the compose service name
(not localhost).
Allowed Files:
- lab7-database/docker-compose.yml
- lab7-database/.env
- lab7-database/backend/*
- lab7-database/SQL schema files
Disallowed:
- ORMs and ORM models
- migration frameworks
- new frontend code
- changes to existing endpoints beyond persistence
- changes to frontend/agents.md or backend/agents.md
Acceptance Checks:
- PostgreSQL container runs successfully.
- summaries table exists.
- /summarize inserts a row into the database.
- GET /summaries returns stored data.
- Data persists across backend container restarts.