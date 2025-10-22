# Backend - Device Management API (Flask)

This Flask backend provides RESTful endpoints under `/api` for managing network devices (CRUD) and status checks (simulated reachability). Storage is in-memory by default so it works without MongoDB.

## Run locally

1. Python 3.10+
2. Install dependencies:
   pip install -r requirements.txt
3. Start server:
   PORT=3001 python app.py

Server runs on http://localhost:3001

Health: GET /api/health
OpenAPI (minimal): GET /openapi.json

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
