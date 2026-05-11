# CLAUDE.md - Legawrite.AI Take-Home

Project instructions and conventions.

## Tech Stack
- Backend: FastAPI (Python 3.11+)
- Frontend: Next.js (TypeScript)
- Infrastructure: Docker, Redis
- Signaling: Server-Sent Events (SSE) with Redis Pub/Sub

## Architecture
- `backend/`: FastAPI application. Handles API requests and SSE connections.
- `worker/`: (Part of backend) Processes long-running jobs.
- `frontend/`: Next.js application.
- `Redis`: Used for job state persistence and Pub/Sub signaling.

## Coding Standards
- **Zero Slop**: No unused imports, dead code, or speculative abstractions.
- **Strict Typing**: Use Python type hints and TypeScript interfaces.
- **Error Handling**: Graceful failure with appropriate status codes and user feedback.
- **Scalability**: Design for 1M concurrent users.

## Commands
- Build & Run: `docker compose up --build`
- Backend Lint: `ruff check .`
- Frontend Lint: `npm run lint`
- Audit: `/reviewslop` (custom agent command)
