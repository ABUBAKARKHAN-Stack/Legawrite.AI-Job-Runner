# SPEC.md - Long-Running Job Signaling System

## Problem Statement
Build a system where a user submits a prompt, a backend job runs for 90s-5min, and the frontend
is notified upon completion. The system must scale to 1,000,000 users.

**Locked Assumptions:**
- Jobs are fire-and-forget; the client only needs to know when they complete or fail.
- Redis is the sole data store for this demo (no Postgres).
- Authentication is out of scope.
- The job payload is a simulated `asyncio.sleep(90)` with a fake result string.

---

## Architecture Diagram

```
Browser (EventSource)
        │  SSE (GET /api/jobs/{id}/stream)
        ▼
┌──────────────────┐     ┌──────────────────┐
│   API Node 1     │     │   API Node 2     │  ← stateless, N replicas
│  (FastAPI/uvicorn│     │  (FastAPI/uvicorn)│
└────────┬─────────┘     └────────┬─────────┘
         │  subscribe job_channel:{id}        │
         └────────────┬───────────┘
                      ▼
          ┌─────────────────────┐
          │      Redis          │
          │  Pub/Sub + State    │  ← job:{id} key (TTL 1h)
          └──────────┬──────────┘
                     │  BLPOP job_queue
                     ▼
          ┌─────────────────────┐
          │    Worker Process   │  ← N replicas, stateless
          │  (asyncio, Python)  │
          └─────────────────────┘
```

**Flow:**
1. `POST /api/jobs` → writes `job:{id}` to Redis, pushes `job_id` onto `job_queue` list.
2. Worker `BLPOP`s from `job_queue`, updates state, publishes to `job_channel:{id}`.
3. API node subscribed to `job_channel:{id}` forwards the message to the open SSE connection.
4. Browser `EventSource` receives the event and renders the result — no refresh needed.

---

## Signaling Mechanism: Server-Sent Events (SSE) + Redis Pub/Sub

### Chosen Mechanism: SSE
We use **Server-Sent Events (SSE)** for real-time notifications.
- **Pros**:
    - Native browser support with automatic reconnection (`EventSource`).
    - Lower overhead than WebSockets (unidirectional is enough for "job done").
    - Works well with HTTP/2 multiplexing.
- **Justification**: For 1M users, minimizing per-connection overhead is critical. SSE connections
  are persistent but lightweight HTTP streams. Redis Pub/Sub decouples the worker from the API tier,
  so any API node can relay the signal regardless of which node the client is connected to.

### Alternatives Considered
1. **Short Polling**:
    - *Rejected*: 1M users polling every 2s = 500k req/sec sustained. This would crush the DB
      and API tier and adds unnecessary latency.
2. **WebSockets**:
    - *Rejected*: Bi-directional framing and manual reconnection/heartbeat logic add complexity
      that is unnecessary for a one-way "job done" signal. SSE's built-in reconnect (`EventSource`)
      is simpler and more resilient for this use case.

---

## API Contract

### POST `/api/jobs`
- **Request**: `{ "prompt": string }`
- **Response**: `{ "job_id": string, "status": "pending" }`

### GET `/api/jobs/{job_id}/stream`
- **Response**: SSE Stream
- **Events**:
    - `status`: `{ "status": "processing" | "completed" | "failed" }`
    - `result`: `{ "data": string }` (sent on completion)
    - `error`: `{ "error": string }` (sent on failure)

### GET `/health`
- **Response**: `{ "status": "healthy", "redis": "ok" }` or HTTP 503

### GET `/metrics`
- **Response**: `{ "queue_depth": int }`

---

## Data Model & State Machine

**Redis key**: `job:{job_id}` (JSON string, TTL: 1 hour)

```json
{
  "job_id": "uuid",
  "prompt": "string",
  "status": "pending | processing | completed | failed",
  "result": "string | null",
  "error": "string | null"
}
```

**State transitions:**
```
PENDING ──► PROCESSING ──► COMPLETED
                    └──────► FAILED
```

1. `PENDING`: Job created, queued in Redis `job_queue` list.
2. `PROCESSING`: Worker picked up the job via `BLPOP`.
3. `COMPLETED`: Job finished, result stored in Redis.
4. `FAILED`: Job threw an exception; error stored in Redis; client receives `error` SSE event.

---

## Failure Modes & Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| **Worker crash mid-job** | Job stays in `PROCESSING` with no Pub/Sub message | At-least-once: re-queue via a separate watchdog or Celery visibility timeout. Currently, re-deploy restarts the worker loop; the job key TTL (1h) prevents ghost data. |
| **Client disconnect** | `request.is_disconnected()` returns `True` | `EventSource` auto-reconnects. On reconnect, the API reads the current job state from Redis and immediately sends the current status — no signal is lost. |
| **API node crash** | Client loses SSE connection | `EventSource` reconnects to any healthy API node. Redis state is the source of truth; the new node resumes streaming. |
| **Redis down** | `/health` returns 503 | Load balancer stops routing. Worker reconnects on next `blpop` call. Jobs in-flight are lost (acceptable for this demo scope). |
| **Duplicate submission** | Same prompt submitted twice | Two separate `job_id` UUIDs are created — idempotency is at the job-ID level. Clients track their own `job_id`; duplicate UI submissions are blocked by disabling the form while a job is active. |

---

## Scaling Plan — 1,000,000 Users

**Primary bottleneck**: Concurrent open SSE connections on the API tier.
- Each connection holds one socket fd + one Redis Pub/Sub subscription.
- At 1M users: 1M file descriptors + 1M Redis subscriptions.

**Solution layers:**

| Layer | Mechanism |
|---|---|
| **API tier** | Horizontal scale-out (stateless FastAPI nodes). Each node subscribes to only the channels for its own connections. L7 load balancer (Nginx / AWS ALB) with sticky sessions for SSE OR Redis Pub/Sub fanout makes sticky sessions optional. |
| **Worker tier** | Horizontal scale-out. Multiple workers consume from the same `job_queue` Redis list. `BLPOP` provides at-most-once delivery per worker. |
| **Connection tier** | Tune OS: `ulimit -n 1000000`, `net.ipv4.tcp_tw_reuse`, `SO_REUSEPORT`. Use HTTP/2 to multiplex streams. |
| **Redis tier** | Redis Cluster for Pub/Sub throughput. Separate read replicas for state reads. |

---

## Observability

| Signal | Implementation |
|---|---|
| **Structured logs** | JSON-formatted logs via Python `logging` in both `api` and `worker` processes. Fields: `time`, `level`, `logger`, `message`. |
| **Health endpoint** | `GET /health` — checks Redis `PING`. Used by Docker healthcheck and load balancer. |
| **Metrics endpoint** | `GET /metrics` — returns `queue_depth` (length of `job_queue` list). A spike indicates workers are falling behind. |
| **Alerting (production)** | Alert on: `queue_depth > N`, `/health` returning 503, worker process restarts, job age in `PROCESSING` state exceeding 10 minutes. |

---

## Security

| Concern | Stance |
|---|---|
| **Authentication / Authorization** | Out of scope for this demo. In production: JWT bearer token on `POST /api/jobs`; SSE endpoint validates `job_id` ownership. |
| **Input validation** | Prompt is validated as a non-empty string. Length limit would be enforced in production. |
| **CORS** | Currently `allow_origins=["*"]` for the demo. Production: restrict to the frontend origin. |
| **Redis exposure** | Redis is on the internal Docker network, not exposed externally. |
| **SSE `job_id` enumeration** | UUIDs are unguessable. Auth would further prevent cross-user access. |

---

## Out of Scope
- Authentication & authorization
- Complex UI styling
- Persistent database (Postgres) — Redis handles both state and signaling for this demo
- Job cancellation
- Rate limiting
