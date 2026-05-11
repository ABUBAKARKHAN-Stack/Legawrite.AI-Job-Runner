# PROCESS.md - Workflow Documentation

## Planning vs Execution
I started by analyzing the requirements and constraints. The 1M user requirement immediately pointed towards a stateless backend with a distributed signaling mechanism. I chose SSE over WebSockets for its simplicity and native reconnection features, backed by Redis Pub/Sub for cross-instance notification.

## Sub-agent Delegation
The development was driven using the primary Claude Code interface. I used the `slop-reviewer` agent to audit the codebase periodically to ensure adherence to the "zero slop" rule.

## Custom Commands
- `/reviewslop`: Orchestrates the `slop-reviewer` agent to scan the repository and generate `SLOP_AUDIT.md`.

## Extended Thinking
I used extended thinking to model the failure surfaces of SSE at scale, specifically considering connection limits and how to handle client reconnections without losing the job completion signal.

## Development Loop
1. Define Spec and Constraints.
2. Build Backend (FastAPI + Redis).
3. Build Frontend (Next.js).
4. Dockerize.
5. Audit for Slop.
6. Fix findings.
7. Final Validation.
