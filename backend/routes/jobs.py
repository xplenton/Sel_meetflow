"""Iter 253 — Generic background-job polling API.

Pattern:
  1. Client calls a synchronous "fire" endpoint (e.g. /news/{id}/push/bulk-async)
     which returns {job_id: "..."} immediately.
  2. Client polls GET /api/jobs/{job_id} until status == "complete" or "failed".
  3. Job result is included in the response when complete.

Backed by arq's built-in job-result tracking in Redis.
"""
from fastapi import APIRouter, HTTPException, Request

from dependencies import get_current_user
from services.background_queue import _get_pool, ENABLED


router = APIRouter()


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, request: Request):
    """Poll status + result of a background job (arq).

    Returns:
      - status: "queued" | "in_progress" | "complete" | "failed" | "not_found"
      - result: present when status == "complete"
      - error: present when status == "failed"
    """
    await get_current_user(request)  # auth gate
    if not ENABLED:
        return {"job_id": job_id, "status": "complete", "result": None,
                "note": "background queue disabled - jobs ran inline"}
    try:
        pool = await _get_pool()
        from arq.jobs import Job
        job = Job(job_id, pool)
        info = await job.info()
        if info is None:
            return {"job_id": job_id, "status": "not_found"}
        # arq stores status in JobStatus enum
        status = await job.status()
        status_str = status.value if hasattr(status, "value") else str(status)
        result_dict = {"job_id": job_id, "status": status_str}
        if status_str == "complete":
            try:
                res = await job.result(timeout=0.1)
                # If the result is binary (e.g. a PDF), don't try to JSON-encode it —
                # the caller fetches it via the type-specific download endpoint.
                if isinstance(res, (bytes, bytearray)):
                    result_dict["result"] = {"binary": True, "size": len(res)}
                else:
                    result_dict["result"] = res
            except Exception as e:
                result_dict["status"] = "failed"
                result_dict["error"] = str(e)
        return result_dict
    except Exception as e:
        # Redis down / arq misconfigured — degrade gracefully.
        raise HTTPException(503, f"job status unavailable: {e}")
