#!/bin/bash
# Iter 254 — Backend startup wrapper that toggles between dev (hot-reload, 1
# worker) and prod (4 workers, no reload) based on the DEV_MODE env variable.
#
# Usage in supervisord.conf:
#   command=/app/backend/start.sh
#   environment=DEV_MODE="1"   # for dev with hot-reload
#
# Without DEV_MODE: production 4-worker mode (default).
# With DEV_MODE=1: single worker + --reload (file changes auto-restart).

cd /app/backend

if [ "${DEV_MODE:-0}" = "1" ]; then
    echo "[start.sh] DEV_MODE=1 — starting uvicorn with --reload (1 worker)"
    exec /root/.venv/bin/uvicorn server:app \
        --host 0.0.0.0 --port 8001 --reload
else
    echo "[start.sh] DEV_MODE off — starting uvicorn with 8 workers + uvloop"
    # Iter 335 — Performance tuning under load:
    #   --loop uvloop / --http httptools : C-backed event loop + HTTP parser
    #     (~2-4x faster than asyncio/h11 under concurrency).
    #   --limit-concurrency : graceful 503 instead of unbounded queue depth.
    #   --backlog : TCP accept queue depth so bursts don't get reset.
    #   --timeout-keep-alive : keep idle TCP connections short so workers
    #     don't get pinned by abandoned clients.
    # Iter 345 — workers 4 → 8 to lift the ~150 RPS plateau observed in the
    # iter-344 soak. The container has 8 vCPUs; the previous 4-worker setup
    # left 50% headroom on CPU even at p95 spikes.
    exec /root/.venv/bin/uvicorn server:app \
        --host 0.0.0.0 --port 8001 --workers 8 \
        --loop uvloop --http httptools \
        --limit-concurrency 1000 \
        --backlog 2048 \
        --timeout-keep-alive 5
fi
