import asyncio
import json
import logging
import sys
import uuid
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from .redis_client import get_redis

# Structured JSON logging — mirrors worker.py format
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
    stream=sys.stdout,
)
logger = logging.getLogger("api")

app = FastAPI(title="Legawrite API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOB_TTL_SECONDS = 3600  # Mirror worker TTL


@app.post("/api/jobs")
async def create_job(request: Request):
    data = await request.json()
    prompt = data.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    job_id = str(uuid.uuid4())
    redis = await get_redis()

    # Store initial state with TTL
    job_data = {
        "job_id": job_id,
        "prompt": prompt,
        "status": "pending",
        "result": None,
    }
    await redis.set(f"job:{job_id}", json.dumps(job_data), ex=JOB_TTL_SECONDS)

    # Push to queue for worker
    await redis.lpush("job_queue", job_id)
    logger.info(f"Created job: {job_id}")

    return {"job_id": job_id, "status": "pending"}


@app.get("/api/jobs/{job_id}/stream")
async def stream_job_updates(job_id: str, request: Request):
    redis = await get_redis()

    # Check if job exists
    job_raw = await redis.get(f"job:{job_id}")
    if not job_raw:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        # ignore_subscribe_messages must be set at construction time in redis-py 5.x.
        # Passing it to get_message() raises TypeError in redis-py >= 5.0.
        pubsub = redis.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(f"job_channel:{job_id}")

        try:
            # Send current state immediately — handles reconnects and
            # jobs that completed before the client opened the stream.
            current_job = json.loads(await redis.get(f"job:{job_id}"))
            yield {
                "event": "status",
                "data": json.dumps({"status": current_job["status"]}),
            }

            if current_job["status"] in ("completed", "failed"):
                if current_job["status"] == "completed":
                    yield {
                        "event": "result",
                        "data": json.dumps({"data": current_job["result"]}),
                    }
                else:
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": current_job.get("error", "Unknown error")}),
                    }
                return

            # Listen for Pub/Sub updates
            while True:
                if await request.is_disconnected():
                    logger.info(f"Client disconnected from job: {job_id}")
                    break

                message = await pubsub.get_message(timeout=1.0)
                if message:
                    payload = json.loads(message["data"])

                    if "status" in payload:
                        yield {
                            "event": "status",
                            "data": json.dumps({"status": payload["status"]}),
                        }

                    if "result" in payload:
                        yield {
                            "event": "result",
                            "data": json.dumps({"data": payload["result"]}),
                        }

                    if "error" in payload:
                        yield {
                            "event": "error",
                            "data": json.dumps({"error": payload["error"]}),
                        }

                    if payload.get("status") in ("completed", "failed"):
                        break

                await asyncio.sleep(0.1)

        finally:
            await pubsub.unsubscribe(f"job_channel:{job_id}")

    return EventSourceResponse(event_generator())


@app.get("/health")
async def health():
    """Readiness probe — checks Redis connectivity."""
    try:
        redis = await get_redis()
        await redis.ping()
        return {"status": "healthy", "redis": "ok"}
    except Exception as exc:
        logger.error(f"Health check failed: {exc}")
        return JSONResponse(status_code=503, content={"status": "unhealthy", "redis": str(exc)})


@app.get("/metrics")
async def metrics():
    """Basic metrics endpoint — queue depth and active job count."""
    try:
        redis = await get_redis()
        queue_depth = await redis.llen("job_queue")
        return {"queue_depth": queue_depth}
    except Exception as exc:
        logger.error(f"Metrics check failed: {exc}")
        return JSONResponse(status_code=503, content={"error": str(exc)})
