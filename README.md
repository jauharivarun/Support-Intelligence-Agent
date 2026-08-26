# ParcelPilot Support Intelligence

Role-based AI support platform for customers and internal support. Local demo MVP.

## Stack

- **Frontend:** React + Vite + TypeScript (`frontend/`)
- **Backend:** Django + DRF + SimpleJWT (`backend/`)
- **DB:** PostgreSQL (embeddings stored as JSON vectors; cosine similarity in-app)
- **AI:** OpenAI Responses API (`gpt-4o-mini`) when `OPENAI_API_KEY` is set; deterministic mock path otherwise. Embeddings can use mock vectors via `USE_MOCK_EMBEDDINGS=true` independently of the chat model.

## Quick start (local, no Docker)

### 1. Database

```bash
createdb parcelpilot
```

### 2. Backend

```bash
cd backend
cp ../.env.example ../.env   # optional; defaults work for local demo
uv sync
uv run python manage.py migrate
uv run python manage.py seed_demo
uv run python manage.py runserver
```

Demo users (password `demo1234`):

| Email | Role |
|-------|------|
| northstar@demo.local | CUSTOMER (ACCT-001) |
| lumenworks@demo.local | CUSTOMER (ACCT-002) |
| support@demo.local | INTERNAL_SUPPORT |
| admin@demo.local | ADMIN |

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### OpenAI (optional)

Set `OPENAI_API_KEY` in `.env`. Without it, the agent uses a deterministic mock path that still exercises tools, source resolution, and pending actions.

## Docker Compose

Requires Docker. From repo root:

```bash
docker compose up --build
```

## Useful API paths

- `POST /api/auth/login/`
- `POST /api/agent/chat/`
- `GET /api/issue-intelligence/`
- `POST /api/documents/upload/` (ADMIN)
- `POST /api/actions/{id}/confirm/`

## Tests

```bash
cd backend
uv run python manage.py test apps.source_resolution apps.actions
```

## Seed data

Uses files in `Docs for implementation/`:

- `ParcelPilot_Assessment_Data.xlsx`
- Policy / agreement PDFs `01`–`06`
