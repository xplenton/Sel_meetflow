# Production Multi-Pod Deployment Guide — MeetFlow

This guide describes how to deploy MeetFlow in a multi-pod horizontally-scaled
configuration for production, leveraging the Redis Pub/Sub broker (iter 176)
and MongoDB Replica Set (validated in iter 175).

> **Important**: This setup is **not** active in the Emergent preview
> environment — the preview uses a single-pod supervisor config with
> hot-reload. The configs below are intended for Kubernetes / dedicated
> cloud deployment.

---

## Target architecture

```
                    ┌──────────────────────────────┐
          HTTPS     │        nginx Ingress         │
  Client ────────▶  │  (load balancer + TLS term.) │
                    └────────────┬─────────────────┘
                                 │ round-robin, keepalive
                 ┌───────────────┼───────────────┐
                 ▼               ▼               ▼
          ┌───────────┐   ┌───────────┐   ┌───────────┐
          │   Pod A   │   │   Pod B   │   │   Pod C   │
          │ uvicorn   │   │ uvicorn   │   │ uvicorn   │
          │ 8 workers │   │ 8 workers │   │ 8 workers │
          └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
                │ WebSocket fan-out + presence  │
                └────────────┬──────────────────┘
                             ▼
                       ┌────────────┐
                       │   Redis    │  ← pub/sub channel "meetflow:ws"
                       │  (single)  │  ← sorted set "meetflow:presence"
                       └────────────┘
                             ▲
                             │ all Mongo reads/writes
                  ┌──────────┴────────────┐
                  ▼                       ▼
            ┌──────────┐            ┌──────────┐
            │ Mongo    │            │ Mongo    │
            │ Primary  │◀──── RS ───▶│ Secondary│ × 2
            └──────────┘            └──────────┘
```

---

## 1. nginx load-balancer config

`/etc/nginx/conf.d/meetflow.conf`:

```nginx
upstream meetflow_backend {
    server pod-a.meetflow.svc.cluster.local:8001 max_fails=0;
    server pod-b.meetflow.svc.cluster.local:8001 max_fails=0;
    server pod-c.meetflow.svc.cluster.local:8001 max_fails=0;
    keepalive 256;
    keepalive_timeout 20s;     # MUST be shorter than uvicorn's --timeout-keep-alive
    keepalive_requests 1000;
}

server {
    listen 443 ssl http2;
    server_name meetflow.example.com;

    ssl_certificate     /etc/letsencrypt/live/.../fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/.../privkey.pem;

    # Retry the failed request transparently on the next upstream
    proxy_next_upstream error timeout http_502 http_503 http_504;
    proxy_next_upstream_tries 3;
    proxy_next_upstream_timeout 10s;

    location / {
        proxy_pass http://meetflow_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
        proxy_connect_timeout 5s;

        # WebSockets (chat, meeting signalling)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 2. Per-Pod uvicorn command

```bash
uvicorn server:app \
  --host 0.0.0.0 --port 8001 \
  --workers 8 \
  --backlog 4096 \
  --http httptools \
  --timeout-keep-alive 75 \
  --no-access-log
```

- `--workers 8` matches 8 vCPU pods. Rule of thumb: `workers = vCPU` for I/O-bound apps.
- `--timeout-keep-alive 75` MUST be greater than nginx's `keepalive_timeout` (20 s).
- `--http httptools` avoids the h11 `ConnectionClosed` keepalive race.

## 3. Required environment variables (all pods)

```env
MONGO_URL="mongodb://mongo-0.mongo.svc:27017,mongo-1.mongo.svc:27017,mongo-2.mongo.svc:27017/meetflow?replicaSet=rs0&readPreference=primaryPreferred"
DB_NAME="meetflow_prod"
REDIS_URL="redis://redis.meetflow.svc:6379/0"
JWT_SECRET="<strong random 64+ chars>"
RESEND_API_KEY="..."     # or SENDGRID_API_KEY / SMTP config via admin UI
VAPID_PRIVATE_KEY="..."
VAPID_PUBLIC_KEY="..."
LIVEKIT_API_KEY="..."
LIVEKIT_API_SECRET="..."
LIVEKIT_URL="wss://..."
```

> **Sticky sessions are NOT required** — the Redis broker handles cross-pod
> WebSocket fan-out transparently.

## 4. MongoDB 3-Member Replica Set

One-time init (run on mongo-0):

```bash
mongosh --host mongo-0 --eval '
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo-0.mongo.svc:27017", priority: 2 },
    { _id: 1, host: "mongo-1.mongo.svc:27017", priority: 1 },
    { _id: 2, host: "mongo-2.mongo.svc:27017", priority: 1 }
  ]
})'
```

Verify:

```bash
mongosh --host mongo-0 --eval 'rs.status().members.forEach(m => print(m.name, m.stateStr))'
# Expected: one PRIMARY, two SECONDARY
```

### 4.1 Application-level read-scaling (iter 187)

`backend/database.py` exposes **two** Motor handles:

- `db` → `primary` reads + all writes (default for "read-your-own-write" code).
- `read_db` → `secondaryPreferred` — used by HEAVY read-only endpoints
  that tolerate ~1 s replication lag (news-feed, surveys-list,
  meetings-list, dashboards, search, health metrics).

When the deployment uses a Replica-Set, this **doubles or triples** read
throughput by farming heavy queries out to SECONDARY nodes. On a
stand-alone MongoDB it is a transparent no-op (the only node IS the
primary, so reads stay local).

No code changes are required when you switch from stand-alone → RS;
just point `MONGO_URL` at the RS connection string above and the read
preference takes effect automatically. Verify with:

```bash
# On every backend pod, after a feed request:
mongosh "$MONGO_URL" --eval '
  db.adminCommand({serverStatus: 1}).opcountersRepl
  // → see counts increase on SECONDARY nodes
'
```

## 5. Redis

- Use a managed instance (AWS ElastiCache, DigitalOcean Redis, Upstash) OR a
  pod of `redis:7-alpine` with persistent volume (for durability) or a
  `save ""` / `appendonly no` config (pure-cache mode).
- **Single-node Redis is fine** for MeetFlow's pub/sub workload — we publish
  at ~100 msgs/sec peak. For HA, add a Redis Sentinel cluster.
- Connection count: each uvicorn worker opens 1 pub/sub connection (so 3 pods ×
  8 workers = 24 connections). Set Redis `maxclients` ≥ 128.

## 6. Scaling recommendations by load

| Concurrent Users | Pods × Workers | Redis      | MongoDB       |
|-----------------:|:--------------:|:----------:|:-------------:|
| ≤ 500            | 1 × 4          | optional   | single-node   |
| 500 – 2 000      | 2 × 8          | single-node| 3-member RS   |
| 2 000 – 10 000   | 4 × 8          | sentinel   | 3-member RS + read-replicas |
| > 10 000         | 6+ × 8         | cluster    | sharded       |

## 7. Rollout checklist

- [ ] MongoDB RS initialized, connectivity tested with `mongosh --host ... --eval 'db.runCommand({ping:1})'`
- [ ] Redis reachable: `redis-cli -u $REDIS_URL ping` returns `PONG`
- [ ] Each pod boots with log line: `[ws_broker] ✓ connected to Redis, pod_id=<hex>`
- [ ] nginx config reloaded: `nginx -t && nginx -s reload`
- [ ] `curl https://meetflow.example.com/api/health` returns `status:ok`
- [ ] WebSocket sanity: log in on two devices through different pods (check
      `X-Upstream` header if enabled), user A sees user B's presence + typing
- [ ] Run the load test against the live cluster:
      `API_URL=https://meetflow.example.com python3 /app/backend/tests/perf/load_test.py`
      Expect ≥ 300 RPS, ≤ 1 % error rate under the 500-user + 1000-burst scenario.

## 8. Monitoring

Key metrics to graph:
- **Redis pub/sub**: `redis-cli info stats | grep pubsub` — `pubsub_channels`, `pubsub_patterns`
- **Presence key size**: `redis-cli zcard meetflow:presence` (= # currently online users)
- **Broker health per pod**: all pods should log `connected to Redis` at startup
- **Mongo RS state**: `rs.status().members[*].stateStr` should be PRIMARY/SECONDARY
- **nginx upstream errors**: `grep "upstream prematurely closed" /var/log/nginx/error.log | wc -l`

## 9. Preview-to-production migration path

1. Deploy 1 pod + existing MongoDB (no RS) → same as preview, no behaviour change.
2. Add Redis → ws_broker activates automatically, still single-pod.
3. Scale to 2 pods + nginx LB → cross-pod chat/presence starts working.
4. Convert MongoDB to 3-member RS → durability + failover.
5. Add read-preference tuning → reads scale with secondaries.

Each step is independent and reversible.
