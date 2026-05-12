# PROCESS.md - Development Workflow

## Overview

This document describes how I used Claude Code CLI as the primary development driver to build the Legawrite.AI job signaling system. All decisions were spec-first: if a feature isn't in `SPEC.md`, it doesn't ship.

---

## Phase 1: Planning & Spec-First Design

Before writing a single line of code, I used **extended thinking** to model the core technical problem: how do you reliably signal 1,000,000 browser clients when a long-running job completes?

### Extended Thinking Usage

I prompted Claude with extended thinking enabled to evaluate three signaling mechanisms:

1. **Short Polling** — Rejected immediately. At 1M users polling every 2s = 500k req/sec sustained. This is a database and API killer before any real load.
2. **WebSockets** — Viable but over-engineered. Bi-directional framing, manual heartbeats, and sticky session complexity are unnecessary for a one-way "job done" signal.
3. **SSE + Redis Pub/Sub** — Chosen. Native browser `EventSource` auto-reconnect, HTTP/2 multiplexing, stateless API nodes via Redis fanout. Extended thinking helped surface the file descriptor bottleneck (1 FD per open SSE connection) as the primary 1M-user limit — not CPU or memory.

Extended thinking also helped map out the full failure surface before implementation: worker crash semantics (at-most-once vs at-least-once), client reconnect race conditions, and the Redis-down cascade.

### Spec Written Before Code

`SPEC.md` was written first and locked. It defined:
- The state machine: `PENDING → PROCESSING → COMPLETED/FAILED`
- The API contract (endpoints, event types, payloads)
- The Redis data model with TTL
- Failure modes table (worker crash, client disconnect, Redis down, duplicate submission)
- Scaling plan across all three tiers (API, worker, connection)
- Observability requirements (structured logs, `/health`, `/metrics`)

No code was written until the spec was complete. This made every subsequent decision traceable to a spec line.

---

## Phase 2: Execution Order

Implementation followed a strict dependency order:

1. **`redis_client.py`** — Singleton connection pool. Written first since both `main.py` and `worker.py` depend on it.
2. **`worker.py`** — Job processor with `BLPOP`, state transitions, Pub/Sub publish, `try/except` → FAILED path.
3. **`main.py`** — FastAPI routes: `POST /api/jobs`, `GET /api/jobs/{id}/stream` (SSE + Pub/Sub), `/health`, `/metrics`.
4. **`JobRunner.tsx`** — Frontend `EventSource` client with named event listeners (`status`, `result`, `error`).
5. **`docker-compose.yml`** — Orchestration with service health checks, graceful shutdown, and `restart: on-failure`.
6. **Tests** — Critical-path tests for job creation, 404 guard, health probe, metrics.

Each component was committed separately with an intentional commit message describing the why, not just the what.

---

## Phase 3: Sub-Agent Delegation

### The `slop-reviewer` Sub-Agent

I built a dedicated sub-agent at `.claude/agents/slop-reviewer.md` to audit the codebase against `SPEC.md`. This agent is **non-optional** — it runs after every meaningful code change.

**Why a sub-agent instead of inline review?**
- A sub-agent is independent of the main conversation context — it reads the spec fresh each time, without bias from what was just written.
- It produces a structured artifact (`SLOP_AUDIT.md`) that is version-controlled and reviewable.
- It can be re-run live during the interview to prove findings are reproducible.

**Delegation pattern used:**
```
Main session → writes code → /reviewslop → slop-reviewer agent runs →
reads SPEC.md → walks all files → classifies each entity →
outputs SLOP_AUDIT.md → main session acts on findings
```

### What the Agent Found

The agent identified 3 real issues in its first run:
1. **Hardcoded `http://localhost:8000`** in `JobRunner.tsx` — bypasses `NEXT_PUBLIC_API_URL` env var
2. **Missing TTL** on `redis.set()` calls — jobs accumulate in Redis memory indefinitely
3. **`err: any` TypeScript cast** — violates `CLAUDE.md` strict typing requirement

All three were remediated in a follow-up commit. The diff is documented in `SLOP_AUDIT.md`.

---

## Phase 4: Custom Slash Commands

### `/reviewslop`

Defined at `.claude/commands/reviewslop.md`. Triggers the `slop-reviewer` sub-agent.

**Why a slash command?**
- Makes the audit a first-class workflow step — one command instead of a multi-step prompt.
- Ensures the agent is always invoked the same way, producing consistent `SLOP_AUDIT.md` output.
- Allows the interviewer to re-run the audit live: `/reviewslop` → `SLOP_AUDIT.md` is updated.

**When it was run:**
- After the initial implementation (found 3 issues)
- After each remediation commit (verified clean)
- Before final submission (verified clean)

---

## Phase 5: Validation

Final validation checklist before submission:

- [ ] `docker compose up --build` completes cleanly on first run
- [ ] Submit prompt → status updates to PROCESSING
- [ ] After 90s → result renders without manual refresh
- [ ] EventStream tab in DevTools shows: `status: processing` → `status: completed` → `result`
- [ ] `/health` returns `{"status": "healthy", "redis": "ok"}`
- [ ] `/metrics` returns `{"queue_depth": 0}`
- [ ] `docker compose up --scale worker=2` — 2 jobs run concurrently, 3rd queues correctly
- [ ] Tests pass: `pytest backend/tests/ -v`

All items confirmed passing.

---

## Key Design Decisions & Rationale

| Decision | Rationale |
|---|---|
| SSE over WebSockets | One-way signal only; `EventSource` auto-reconnect is free; lower overhead |
| Redis list + `BLPOP` over in-memory queue | Survives API restarts; supports N worker replicas with atomic pop |
| State-on-reconnect before Pub/Sub subscribe | Prevents missed-event race condition if job completes during disconnect |
| Singleton Redis client | Prevents connection pool leak (new pool on every call = FD exhaustion) |
| `ignore_subscribe_messages=True` on `pubsub()` | redis-py 5.x API — prevents `json.loads(int)` crash on subscribe confirmation |
| TTL on all Redis keys (1 hour) | Prevents unbounded memory growth at scale |
| `restart: on-failure` on worker | Basic crash recovery without Celery complexity |
| `--timeout-graceful-shutdown 30` on uvicorn | Drains in-flight SSE connections before process exits |
