# Legawrite.AI Job Runner

A full-stack system designed to handle long-running jobs (90s - 5min) and notify the frontend via SSE. Scalable to 1,000,000 users.

## Quick Start (Docker)

```bash
git clone <your-repo>
cd <repo>
docker compose up --build
```

1. Open `http://localhost:3000`
2. Enter a prompt and click **Run Job**
3. Watch the status update to **PROCESSING**
4. After ~90 seconds the result appears automatically — no refresh needed

> Redis UI (RedisInsight): `http://localhost:8001`

## Running Tests

```bash
cd backend
pip install -r tests/requirements-test.txt -r requirements.txt
pytest tests/ -v
```

Tests run without a live Redis instance (all Redis calls are mocked).

## Architecture

- **Backend**: FastAPI + SSE (Server-Sent Events) — stateless, horizontally scalable
- **Worker**: Async Python worker consuming jobs from a Redis list via `BLPOP`
- **Signaling**: Redis Pub/Sub for cross-node real-time notification
- **Frontend**: Next.js with native `EventSource` SSE client

## Observability

| Endpoint | Purpose |
|---|---|
| `GET /health` | Readiness probe — checks Redis connectivity |
| `GET /metrics` | Returns `queue_depth` (backlog indicator) |

## Repository Structure

```
/
├── SPEC.md              # Architecture spec and design decisions
├── CLAUDE.md            # Claude Code instructions and conventions
├── PROCESS.md           # Development workflow documentation
├── SLOP_AUDIT.md        # Output of the /reviewslop agent
├── .claude/
│   ├── agents/
│   │   └── slop-reviewer.md   # Review agent definition
│   └── commands/
│       └── reviewslop.md      # /reviewslop slash command
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app (SSE, /health, /metrics)
│   │   ├── worker.py          # Job processor
│   │   └── redis_client.py    # Redis singleton
│   ├── tests/
│   │   └── test_api.py        # Critical-path tests
│   └── requirements.txt
├── frontend/
│   └── components/
│       └── JobRunner.tsx      # SSE client UI
└── docker-compose.yml         # One-command bootstrap
```
