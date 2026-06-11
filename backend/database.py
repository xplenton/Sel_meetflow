from dotenv import load_dotenv
load_dotenv()

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.read_preferences import ReadPreference
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

mongo_url = os.environ["MONGO_URL"]
# Iter 335 — Explicit connection pool tuning so 4 uvicorn workers ×
# ~50 concurrent in-flight requests don't exhaust the default pool of
# 100 connections (which led to queueing + timeouts under load).
client = AsyncIOMotorClient(
    mongo_url,
    maxPoolSize=200,
    minPoolSize=10,
    maxIdleTimeMS=30000,
    serverSelectionTimeoutMS=5000,
)
db = client[os.environ["DB_NAME"]]

# Iter 187 — read-scaled DB handle for HEAVY read-only endpoints.
# When the deployment uses a Replica-Set (RS), reads are routed to a
# SECONDARY when available, freeing the PRIMARY for writes. On a
# stand-alone MongoDB this is a transparent no-op (the only node is
# also the primary).
#
# Use `read_db` in handlers that ONLY read and tolerate slightly stale
# data (a few seconds at most): list endpoints, dashboards, search,
# health metrics, etc. NEVER use it for read-then-write transactions
# or "read your own write" semantics — for those keep using `db`.
read_db = client.get_database(
    os.environ["DB_NAME"],
    read_preference=ReadPreference.SECONDARY_PREFERRED,
)
