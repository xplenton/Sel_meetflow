#!/bin/bash
# Startup wrapper for Redis — installs redis-server if not present, then execs it.
# This is needed because the container's /usr/bin/redis-server is not persistent
# across container restarts in the Emergent preview environment.
set -e

if ! command -v redis-server >/dev/null 2>&1; then
    echo "[redis-startup] redis-server not found, installing..."
    apt-get update -qq >/dev/null 2>&1 || true
    apt-get install -y redis-server --no-install-recommends >/dev/null 2>&1 || {
        echo "[redis-startup] apt-get install failed — ws_broker will run in single-pod mode"
        # Sleep forever so supervisor doesn't mark as FATAL; manual re-trigger possible
        exec sleep infinity
    }
    echo "[redis-startup] installed successfully"
fi

exec /usr/bin/redis-server \
    --port 6379 \
    --bind 127.0.0.1 \
    --protected-mode yes \
    --daemonize no \
    --save "" \
    --appendonly no
