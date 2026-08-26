# ParcelPilot Support Intelligence

Role-based AI support for ParcelPilot customers and internal agents. The assistant answers from retrieved knowledge-base files, orders, and tickets — not from memorized policy. Admins can upload, replace, or delete PDFs; later answers follow the new files.

## What it does

- Chat with tools: orders, tickets, document search, cancellation/credit calculators, source conflict resolution, confirm-to-submit escalations/follow-ups
- Role isolation: customers see only their account; internal support sees all accounts; only Admin manages the knowledge base
- Source resolution: customer agreement can override SOP; a newer CURRENT policy can override an older SOP for global defaults
- Issue intelligence: recurring ticket themes and known-issue links (internal/admin)
- Observability: tool traces and decision badges on each answer

## Stack

- Frontend: React, Vite, TypeScript (`frontend/`)
- Backend: Django, DRF, SimpleJWT (`backend/`)
- Database: PostgreSQL (chunk embeddings stored as JSON; cosine similarity in the app)
- AI: OpenAI (`gpt-4o-mini`) when `OPENAI_API_KEY` is set; otherwise a deterministic mock path that still runs tools

## Demo logins

Password for all: `demo1234`

| Email | Role | Scope |
| --- | --- | --- |
| northstar@demo.local | CUSTOMER | ACCT-001 (Northstar, Enterprise) |
| lumenworks@demo.local | CUSTOMER | ACCT-002 (LumenWorks, Growth) |
| support@demo.local | INTERNAL_SUPPORT | All accounts; no document admin |
| admin@demo.local | ADMIN | All accounts + document upload/delete |

Seeded knowledge base (from `Docs for implementation/`): Support Policy v3, deprecated v2, Cancellation & Service Credit SOP v4, Product Ops + known issues, Northstar agreement, LumenWorks agreement.

## Local run (no Docker)

PostgreSQL must be running. Create database `parcelpilot`.

```bash
cd backend
cp ../.env.example ../.env
uv sync
uv run python manage.py migrate
uv run python manage.py seed_demo
uv run python manage.py runserver
```

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

Set `OPENAI_API_KEY` in `.env` for live chat. `USE_MOCK_EMBEDDINGS=true` keeps hash embeddings even with a chat key.

## Local Docker

From the repo root:

```bash
docker compose up --build
```

This uses Django `runserver`, the Vite dev server, and `seed_demo` on every start. Do not use this compose file on AWS.

## AWS (HTTP, single EC2)

Production files: `docker-compose.prod.yml`, `frontend/Dockerfile.prod`, `backend/entrypoint.sh`, `.env.production.example`.

One Ubuntu **t3.micro**, security group **22** (your IP) and **80** (anywhere), Elastic IP attached. On the host: 2 GB swap, Docker, copy the repo (keep `Docs for implementation/`), create `.env` from `.env.production.example` (not your laptop `.env`).

```bash
cd /home/ubuntu/Support   # or your project directory on the instance
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend python manage.py seed_demo
```

Open `http://YOUR.ELASTIC.IP/`. Run `seed_demo` only once. To ship new code: `rsync` from your Mac (exclude `.env`, `node_modules`, `.venv`) then `up -d --build` again. Do not seed again unless you want a data reset.

## API

- `POST /api/auth/login/`
- `POST /api/agent/chat/`
- `GET /api/issue-intelligence/`
- `POST /api/documents/upload/` (ADMIN)
- `POST /api/actions/{id}/confirm/`
- `GET /health/` (production)

## Tests

```bash
cd backend
uv run python manage.py test apps.source_resolution apps.actions apps.agent apps.documents
```

## Layout

- `backend/` Django apps (agent, documents, orders, tickets, users, issue intelligence, …)
- `frontend/` Chat UI, login, admin documents, issue intelligence
- `Docs for implementation/` Assessment Excel, policy PDFs, optional Test Policy Update Version 2.0 for override demos
