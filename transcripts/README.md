# Transcripts

This folder contains edited highlights from the Claude Code session used to build this project.

## Session: Initial Build + Architecture
- Drove the spec with extended thinking on the 1M-user bottleneck
- Chose SSE over WebSockets and short polling (justified in SPEC.md)
- Built FastAPI backend, Redis Pub/Sub worker, Next.js frontend in sequence
- Dockerized with health-checked service dependencies

## Session: Redis Bug Fix
- Caught `TypeError: PubSub.get_message() got an unexpected keyword argument 'ignore_subscribe_messages'`
- Root cause: `redis-py 5.x` moved `ignore_subscribe_messages` to the `pubsub()` constructor
- Also caught silent connection-pool leak in `get_redis()` (new pool on every call)
- Fixed both; verified end-to-end SSE flow confirmed working in browser DevTools EventStream tab

## Session: Gap Audit vs Take-Home PDF
- Extracted full PDF spec text and compared against codebase
- Found missing: SPEC.md sections (observability, security, architecture diagram), no FAILED state in worker, no tests, no structured logs, no graceful shutdown, no /metrics, hardcoded localhost URL, missing TTL on Redis keys
- Implemented all gaps in priority order
- Regenerated SLOP_AUDIT.md with real findings and diffs
