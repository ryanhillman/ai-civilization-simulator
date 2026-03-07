# AI Civilization Simulator

An always-live web application that simulates a small AI-driven medieval village. Six autonomous agents interact, trade, gossip, form relationships, and react to events in a deterministic turn-based simulation with selective LLM interpretation.

## Architecture

- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Zustand + TanStack Query
- **Backend**: Python 3.12 + FastAPI + SQLAlchemy 2 (async) + Alembic
- **Database**: PostgreSQL 16
- **AI**: Anthropic Claude (selective, structured output only)

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- Node.js 20+ + [pnpm](https://pnpm.io/)

### 1. Start the database

```bash
docker compose up -d
```

### 2. Backend setup

```bash
cd backend
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

uv sync
uv run alembic upgrade head
uv run python seed/village_seed.py
uv run uvicorn app.main:app --reload
```

Backend runs at http://localhost:8000
API docs at http://localhost:8000/docs

### 3. Frontend setup

```bash
cd frontend
pnpm install
pnpm dev
```

Frontend runs at http://localhost:3000

### 4. pgAdmin (optional)

Visit http://localhost:5050 — login: `admin@local.dev` / `admin`
Add server: host=`postgres`, port=`5432`, user=`civ_user`, pass=`civ_pass`

## Project Structure

```
ai-civilization-simulator/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routes + deps
│   │   ├── core/         # Config, database engine
│   │   ├── domain/       # Simulation engine + AI orchestration
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   └── services/     # DB access layer
│   ├── alembic/          # Database migrations
│   ├── prompts/          # LLM prompt templates
│   ├── seed/             # Initial village data
│   └── tests/
└── frontend/
    └── src/
        ├── api/          # Typed API client
        ├── components/   # UI components
        ├── store/        # Zustand state
        └── types/        # TypeScript types
```

## Simulation Design

The world only advances when the user triggers it — no background loop, no continuous simulation. The LLM never directly mutates world state; it only interprets and narrates what the deterministic engine has decided.

Each turn pipeline:
1. Advance world clock (day / season / weather)
2. Apply scheduled/global events
3. Refresh agent state (hunger, sickness, urgency)
4. Generate action opportunities
5. Resolve deterministic actions
6. Invoke AI only for genuinely ambiguous decisions
7. Resolve social effects (gossip, trust, reputation)
8. Record timeline entries and memories
9. Persist state

## Development

### Run tests

```bash
cd backend
uv run pytest
```

### Create a new migration

```bash
cd backend
uv run alembic revision --autogenerate -m "your description"
uv run alembic upgrade head
```

### Reset the world

```
DELETE /api/world/{world_id}/reset
```
or call `uv run python seed/village_seed.py` to wipe and re-seed.
