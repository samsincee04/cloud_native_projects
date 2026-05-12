# Frontend — agents.md (v1)

## Objective (Day 3)
Create a minimal Next.js UI that supports:
- Preferences input
- Feed list of clusters
- Cluster detail view

## Constraints
- Keep it minimal: ideally one page file.
- No chat UI.
- No UI frameworks.
- Use fetch() calls to backend endpoints.
- Store user_id in localStorage.

## Allowed files (Day 3)
- frontend/app/page.tsx
- frontend/agents.md

# Frontend — agents.md (Day 5)

## Objective
Build a minimal Next.js UI (single page) with 3 modes:
1) Preferences
2) Feed (cluster cards)
3) Cluster detail

## Constraints
- Use ONE page file: frontend/app/page.tsx (no new routes/pages).
- No UI frameworks, no styling libraries.
- Keep components minimal and in the same file.
- Must call backend endpoints:
  - POST /users
  - PUT /users/{id}/preferences
  - GET /feed_clusters?user_id=...
  - GET /clusters/{cluster_id}
- Store user_id in localStorage.
- Include basic loading + error text.

## Allowed files
- frontend/app/page.tsx
- frontend/agents.md
- frontend/.env.local (optional)