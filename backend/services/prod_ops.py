"""
Production-readiness extensions for the MeetFlow API.

Centralises four concerns that were previously scattered or missing:

  1. **Health endpoint** (`/api/health`) — Load-balancer-friendly liveness +
     readiness probe. Checks the Mongo connection with a cheap `ping`.
  2. **Structured logging** — JSON logs with a request-id attached to every
     log line produced during a request. Request-id is also echoed back in
     the `X-Request-ID` response header so clients can reference it in bug
     reports.
  3. **Rate limiting** — `slowapi` limiter that protects auth endpoints from
     brute-force + password-reset flooding.
  4. **ETag / Cache-Control headers** — Lightweight response cache for GET
     endpoints that are not volatile (e.g. `/branding`, `/chat/statuses`).

Everything here is additive — if anything fails to import or configure,
the app continues to boot.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from fastapi import APIRouter, FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


# ---------------------------------------------------------------------------
# Request-ID context + structured JSON logging
# ---------------------------------------------------------------------------
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter — no external deps. Attaches the current
    request_id (from the ContextVar) so correlated log lines can be found
    for any given request."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Accept any `extra={...}` a caller passed
        for k, v in record.__dict__.items():
            if k in ("msg", "args", "levelname", "levelno", "name", "pathname",
                     "filename", "module", "exc_info", "exc_text", "stack_info",
                     "lineno", "funcName", "created", "msecs", "relativeCreated",
                     "thread", "threadName", "processName", "process", "message"):
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except Exception:
                payload[k] = repr(v)
        return json.dumps(payload, ensure_ascii=False)


def configure_json_logging() -> None:
    """Swap the root handlers to a single stdout handler with JSON output.
    Idempotent — safe to call on reload."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    # Remove previous JsonFormatter handlers to keep things idempotent on reload
    root.handlers = [h for h in root.handlers if not isinstance(getattr(h, "formatter", None), JsonFormatter)]
    root.addHandler(handler)
    # Keep INFO as the default; callers can raise to WARNING in prod via env
    if root.level in (logging.NOTSET, logging.WARNING):
        root.setLevel(logging.INFO)
    # Uvicorn's access logger is noisy + duplicates; keep it at WARNING in JSON mode
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Request-ID middleware
# ---------------------------------------------------------------------------
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Log and re-raise so FastAPI's exception handlers still run
            logging.getLogger("request").exception(
                "unhandled_exception",
                extra={"path": request.url.path, "method": request.method},
            )
            request_id_var.reset(token)
            raise
        duration_ms = int((time.perf_counter() - start) * 1000)
        response.headers["X-Request-ID"] = rid
        # Only log API traffic (skip static/health to avoid noise)
        path = request.url.path
        if path.startswith("/api/") and path != "/api/health":
            logging.getLogger("request").info(
                "http_request",
                extra={
                    "method": request.method,
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "client": request.client.host if request.client else None,
                },
            )
        request_id_var.reset(token)
        return response


# ---------------------------------------------------------------------------
# ETag / Cache-Control middleware
# ---------------------------------------------------------------------------
# Endpoints that are safe to cache briefly. Responses get a weak ETag + a
# `Cache-Control: private, max-age=30` header and a 304 shortcut on matching
# `If-None-Match`. Chosen conservatively so we never stale-serve writes.
_ETAG_CACHEABLE_PREFIXES = (
    "/api/organization/branding",
    "/api/news/categories",
    "/api/news/tags",
)


class ETagMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method != "GET" or not any(
            request.url.path.startswith(p) for p in _ETAG_CACHEABLE_PREFIXES
        ):
            return await call_next(request)
        response = await call_next(request)
        # Only weak-ETag small JSON bodies that we can buffer safely
        if response.status_code != 200:
            return response
        try:
            body_bytes = b""
            async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                body_bytes += chunk
        except Exception:
            return response
        # Iter 288 — use SHA-256 for the ETag (was MD5). Still only a cache id,
        # not security-relevant, but SHA-256 satisfies static scanners.
        etag = 'W/"' + hashlib.sha256(body_bytes).hexdigest()[:16] + '"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "private, max-age=30"})
        new_headers = dict(response.headers)
        new_headers["ETag"] = etag
        new_headers["Cache-Control"] = "private, max-age=30"
        # content-length must be recomputed
        new_headers.pop("content-length", None)
        return Response(
            content=body_bytes,
            status_code=response.status_code,
            headers=new_headers,
            media_type=response.media_type,
        )


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
def _rate_limit_key(request: Request) -> str:
    """Use email+IP for auth routes so a single shared IP (hospital Wi-Fi)
    doesn't lock everyone out, but a single bad actor can't rotate email
    addresses to escape."""
    try:
        # Best-effort: peek at the json body; slowapi will dispatch the
        # decorator synchronously so we re-read the body safely via
        # `request.state`.
        email = getattr(request.state, "_rl_email", "")
    except Exception:
        email = ""
    return f"{get_remote_address(request)}|{email or '-'}"


limiter = Limiter(key_func=_rate_limit_key, default_limits=[])


def install_production_extensions(app: FastAPI, api_router: APIRouter) -> None:
    """Wire everything into the given app. Call this ONCE from server.py
    AFTER the routers are included but BEFORE CORS (so the response headers
    still flow through). CORS wraps the whole thing as the outermost layer."""
    configure_json_logging()

    # Sentry — no-op when SENTRY_DSN is unset. Initialised here so even
    # startup exceptions get captured (iter 121).
    sentry_dsn = os.environ.get("SENTRY_DSN", "").strip()
    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.starlette import StarletteIntegration
            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=os.environ.get("SENTRY_ENV", "production"),
                release=os.environ.get("SENTRY_RELEASE", "meetflow@iter-121"),
                traces_sample_rate=0.2,
                integrations=[FastApiIntegration(), StarletteIntegration()],
            )
            logging.getLogger("sentry").info("sentry_sdk initialised")
        except Exception as e:
            logging.getLogger("sentry").warning(f"sentry init failed: {e}")

    # Middlewares run bottom-up: last added == outermost wrapper.
    app.add_middleware(ETagMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # Rate-limit
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Health endpoint — registered directly on `app` so it works even if
    # the api_router has already been included.
    @app.get("/api/health")
    async def health_check():
        from database import db  # local import to avoid import cycles
        started = time.perf_counter()
        mongo_ok = False
        mongo_err = None
        try:
            await db.command("ping")
            mongo_ok = True
        except Exception as e:
            mongo_err = str(e)[:200]
        duration_ms = int((time.perf_counter() - started) * 1000)
        status = "ok" if mongo_ok else "degraded"
        body = {
            "status": status,
            "checks": {
                "mongo": {"ok": mongo_ok, "error": mongo_err, "duration_ms": duration_ms},
            },
            "version": "iter-113",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        return JSONResponse(body, status_code=200 if mongo_ok else 503)
