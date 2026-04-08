## Backend API Contract
The backend is a FastAPI service running locally on port 8000.
### Endpoint
- POST /summarize
### Request JSON
‘‘‘json
{
"text": "string (required, non-empty)",
"max_length": "integer (optional, default = 100)"
}
{
"summary": "string",
"model": "string",
"truncated": "boolean"
}

## Authentication (Development JWT)
All API requests (except GET /health) must include an Authorization header:
Authorization: Bearer <JWT_TOKEN>
In this lab, <JWT_TOKEN> is a hard-coded development token.
Behavior:
- If the header is missing, return HTTP 401 with a clear error message.
- If the token is invalid, return HTTP 401 with a clear error message.
- If the token is valid, continue processing the request normally.