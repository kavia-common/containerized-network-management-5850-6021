# Backend - Device Management API (Flask)

This Flask backend provides RESTful endpoints under `/api` for managing network devices (CRUD) and status checks (simulated reachability). Storage is in-memory by default so it works without MongoDB.

## Run locally

1. Python 3.10+
2. Install dependencies:
   pip install -r requirements.txt
3. Start server:
   PORT=3001 python app.py

Server runs on http://localhost:3001 (host 0.0.0.0 by default when run directly)

- API prefix: all endpoints are under `/api`
- Health: GET /api/health

## Swagger / OpenAPI

Interactive API docs and OpenAPI JSON are available:

- Swagger UI: GET /api/docs
- OpenAPI JSON: GET /api/openapi.json

These document and expose:
- GET /api/devices
- POST /api/devices
- GET /api/devices/{id}
- PUT /api/devices/{id}
- DELETE /api/devices/{id}
- GET /api/devices/status
- POST /api/devices/{id}/status
- GET /api/health

CORS: Enabled for `/api/*` allowing all origins in preview/dev so the UI can call the backend even without dev proxying. In development with CRA, package.json proxy forwards `/api` to port 3001.

## Environment variables

These are placeholders for future MongoDB integration. Not required at runtime now.

- MONGODB_URL=
- MONGODB_DB=
- STATUS_CACHE_TTL_SECONDS=10  (optional)

See `.env.example` at repo root for sample values.

## Notes

- Status checks are simulated to avoid external network dependencies: even last octet IPs are treated as online.
- IP addresses must be unique. Validation prevents duplicates and invalid IPs.
- Designed to be swapped to MongoDB later without breaking API.
