"""Chat-push utilities (iter 262).

Bisher mussten Nutzer für Push-Notifications News oder Tasks öffnen, damit die
Subscription registriert wird. Mit diesem Modul kann Push direkt aus dem Chat
heraus getestet werden, ohne News zu öffnen.
"""
from fastapi import APIRouter, HTTPException, Request

from database import db
from dependencies import get_current_user

router = APIRouter()


@router.post("/chat/push/test")
async def chat_push_self_test(request: Request):
    """Iter 262 — Schickt eine Test-Push an die registrierten Geräte des aktuellen
    Users im Chat-Style. Hilft beim Verifizieren, dass DM-Push funktioniert,
    bevor jemand eine echte Nachricht sendet.
    """
    user = await get_current_user(request)
    subs = await db.push_subscriptions.count_documents({"user_id": user["user_id"]})
    if subs == 0:
        raise HTTPException(
            status_code=400,
            detail="Kein Gerät registriert. Push erst aktivieren (Schritt-für-Schritt im Chat-Header)."
        )
    from services.news_push import send_push_to_user
    try:
        result = await send_push_to_user(
            user["user_id"],
            title=f"💬 Chat-Test · {user.get('name', '')}",
            body="Wenn du das siehst, funktioniert Push für Chat-Nachrichten auf diesem Gerät.",
            data={
                "tag": "chat-push-test",
                "url": "/chat",
                "kind": "chat_message",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Push-Versand fehlgeschlagen: {e}")
    return {"message": "Test-Push versendet", "subscriptions": subs, "result": result}
