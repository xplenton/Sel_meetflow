"""Regression test for iter 176.2 — cross-pod presence via Redis sorted-set."""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))


async def main():
    from services.ws_broker import RedisWsBroker

    a = RedisWsBroker()
    a.set_dispatcher(lambda e: None)
    await a.start()
    assert a.enabled

    b = RedisWsBroker()
    b.set_dispatcher(lambda e: None)
    await b.start()
    assert b.enabled

    # Pre-clean the sorted set
    await a._redis.delete(a._PRESENCE_KEY)

    # Pod A marks alice online; Pod B should see her online via Redis
    await a.mark_online("alice")
    assert await b.is_online("alice"), "Pod B could not see alice online"
    assert "alice" in (await b.online_users())
    print("✓ cross-pod online detection works")

    # Filter-by-user_ids
    await a.mark_online("bob")
    ids_online = await b.online_users()
    assert set(ids_online) >= {"alice", "bob"}
    print("✓ online_users() returns full set")

    # mark_offline from Pod A removes alice everywhere
    await a.mark_offline("alice")
    assert not await b.is_online("alice")
    print("✓ offline propagates")

    # Sweep removes stale entries
    import time as _t
    # Force a stale entry: set score to way in the past
    await a._redis.zadd(a._PRESENCE_KEY, {"zombie": _t.time() - 3600})
    removed = await a.sweep_presence()
    assert removed >= 1, f"sweep did not remove stale entry (removed={removed})"
    assert not await a.is_online("zombie")
    print("✓ sweep_presence drops stale entries")

    await a.mark_offline("bob")
    await a.stop()
    await b.stop()


if __name__ == "__main__":
    asyncio.run(main())
    print("ALL OK")
