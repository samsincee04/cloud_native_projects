Objective:
Containerize the backend and frontend services from previous labs,
then run them together using Docker Compose.
Hard constraints:
- Do not modify existing agents.md files in backend or frontend.
- Do not refactor application code.
- Prefer configuration over code changes.
- Do not introduce Kubernetes.
Backend container constraints:
- Read Python version and dependency information
from backend/pyproject.toml.
- Use a compatible python base image.
- Run the backend using uvicorn.
- Bind uvicorn to 0.0.0.0.
- Expose port 8000 in the container.
Frontend container constraints:
- Read Node.js requirements from frontend/package.json.
- Use a compatible node base image.
- Expose port 3000 in the container.
- The frontend must obtain the backend API base URL from an
environment variable.
- If the frontend already supports configuring
the API base URL via an environment
variable, do not modify frontend source code.
- If the frontend hardcodes the API base URL, you may
modify exactly one existing
frontend file to replace the hardcoded value with an
environment variable read.
- No other frontend source files may be changed.
Compose constraints:
- Create lab6-docker/docker-compose.yml defining
services: backend, frontend.
- Create lab6-docker/.env providing configuration values
used by compose.
- Compose must map host ports so services are reachable
from the host machine.
- The frontend must reach the backend using the
compose service name "backend"
on the compose network, not localhost.
Allowed files:
- lab6-docker/backend/Dockerfile
- lab6-docker/backend/.dockerignore
- lab6-docker/frontend/Dockerfile
- lab6-docker/frontend/.dockerignore
- lab6-docker/docker-compose.yml
- lab6-docker/.env

Acceptance checks (performed manually):
- docker compose up --build starts both services.
- Frontend is reachable at http://localhost:3000
(or configured host port).
- Backend is reachable at http://localhost:8000/docs
(or configured host port).
- The frontend can successfully call a backend endpoint
while running under compose.