# Iter 202 — Cache-Effectiveness Benchmark for /user/permissions

**Setup:** 200 concurrent users × 5 permissions calls each = 1000 total
**Elapsed:** 9.5s · **Throughput:** 105 req/s

## Cold (cache miss — first call per user)
- count: 200
- p50: 2600 ms · p95: 4370 ms · p99: 4445 ms · max: 4469 ms · mean: 2560 ms

## Warm (cache hit — subsequent calls within 60s TTL)
- count: 800
- **p50: 91 ms · p95: 219 ms · p99: 221 ms · max: 222 ms · mean: 100 ms**

## Verdict
Cache speedup: **28×** at p50 · **20×** at p99
Target: warm p99 < 100 ms — **🟡 220 ms**