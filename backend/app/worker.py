import asyncio
import json
import logging
import sys
from .redis_client import get_redis

# Structured JSON logging — required for production observability
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
    stream=sys.stdout,
)
logger = logging.getLogger("worker")

JOB_TTL_SECONDS = 3600  # Expire completed/failed jobs after 1 hour


async def process_jobs():
    redis = await get_redis()
    logger.info("Worker started, waiting for jobs...")

    while True:
        # blpop blocks until a job_id arrives; timeout=0 means wait forever.
        result = await redis.blpop("job_queue", timeout=0)
        if not result:
            continue

        _, job_id = result
        logger.info(f"Picked up job: {job_id}")

        job_raw = await redis.get(f"job:{job_id}")
        if not job_raw:
            logger.warning(f"Job {job_id} not found in Redis — skipping")
            continue

        job_data = json.loads(job_raw)

        # ── Mark as PROCESSING ────────────────────────────────────────────
        job_data["status"] = "processing"
        await redis.set(f"job:{job_id}", json.dumps(job_data), ex=JOB_TTL_SECONDS)
        await redis.publish(
            f"job_channel:{job_id}", json.dumps({"status": "processing"})
        )
        logger.info(f"Job {job_id} → processing")

        # ── Run the job (simulated with asyncio.sleep) ────────────────────
        try:
            await asyncio.sleep(90)

            result_text = (
                f"Result for prompt: '{job_data['prompt']}' - Completed successfully."
            )
            job_data["status"] = "completed"
            job_data["result"] = result_text

            await redis.set(f"job:{job_id}", json.dumps(job_data), ex=JOB_TTL_SECONDS)
            await redis.publish(
                f"job_channel:{job_id}",
                json.dumps({"status": "completed", "result": result_text}),
            )
            logger.info(f"Job {job_id} → completed")

        except Exception as exc:
            # ── FAILED state — publish so the SSE client can show an error ──
            error_msg = str(exc)
            logger.error(f"Job {job_id} failed: {error_msg}")

            job_data["status"] = "failed"
            job_data["error"] = error_msg

            await redis.set(f"job:{job_id}", json.dumps(job_data), ex=JOB_TTL_SECONDS)
            await redis.publish(
                f"job_channel:{job_id}",
                json.dumps({"status": "failed", "error": error_msg}),
            )


if __name__ == "__main__":
    asyncio.run(process_jobs())
