import logging
from fastapi import WebSocket

logger = logging.getLogger("server")


class ConnectionManager:
    def __init__(self):
        self.rooms: dict = {}

    async def connect(self, meeting_id: str, user_id: str, ws: WebSocket):
        await ws.accept()
        if meeting_id not in self.rooms:
            self.rooms[meeting_id] = {}
        existing = list(self.rooms[meeting_id].keys())
        self.rooms[meeting_id][user_id] = ws
        await ws.send_json({"type": "peers", "peers": existing})
        for uid, peer_ws in self.rooms[meeting_id].items():
            if uid != user_id:
                try:
                    await peer_ws.send_json({"type": "peer-joined", "peer_id": user_id})
                except Exception:
                    pass

    async def disconnect(self, meeting_id: str, user_id: str):
        if meeting_id in self.rooms:
            self.rooms[meeting_id].pop(user_id, None)
            for uid, ws in self.rooms[meeting_id].items():
                try:
                    await ws.send_json({"type": "peer-left", "peer_id": user_id})
                except Exception:
                    pass
            if not self.rooms[meeting_id]:
                del self.rooms[meeting_id]

    async def send_to(self, meeting_id: str, target_id: str, msg: dict):
        if meeting_id in self.rooms:
            ws = self.rooms[meeting_id].get(target_id)
            if ws:
                await ws.send_json(msg)

    async def _local_broadcast(self, meeting_id: str, msg: dict, exclude: str = None):
        """Pod-local fan-out only. Used by both broadcast() and the
        cross-pod dispatcher for incoming Redis envelopes."""
        if meeting_id in self.rooms:
            for uid, ws in self.rooms[meeting_id].items():
                if uid != exclude:
                    try:
                        await ws.send_json(msg)
                    except Exception:
                        pass

    async def broadcast(self, meeting_id: str, msg: dict, exclude: str = None):
        # iter 211 — Cross-pod fan-out via Redis Pub/Sub.
        # Without this, two participants landing on different FastAPI workers
        # never see each other's hand-raise / reaction / chat / whiteboard
        # events, because each worker only knew about the sockets it owned
        # locally. The broker degrades to no-op when REDIS_URL isn't set so
        # single-pod dev/preview is unaffected.
        await self._local_broadcast(meeting_id, msg, exclude)
        try:
            from services.ws_broker import ws_broker
            if ws_broker.enabled:
                await ws_broker.publish(
                    kind="meeting",
                    target=meeting_id,
                    data={"msg": msg, "exclude": exclude},
                )
        except Exception as e:
            # Never break the calling write path because of broker hiccups —
            # local fan-out already happened.
            logger.warning(f"ws_manager broker publish failed: {e!r}")


ws_manager = ConnectionManager()


async def _meeting_dispatcher(envelope: dict):
    """Receive a Redis envelope from another pod and re-dispatch locally.

    Registered with ws_broker at server startup. Only handles envelopes with
    kind='meeting'; other kinds (chat user/conversation) are owned by the
    chat manager which has its own dispatcher."""
    if envelope.get("kind") != "meeting":
        return
    meeting_id = envelope.get("target")
    payload = envelope.get("data") or {}
    msg = payload.get("msg")
    exclude = payload.get("exclude")
    if not meeting_id or not isinstance(msg, dict):
        return
    await ws_manager._local_broadcast(meeting_id, msg, exclude)
