from fastapi import APIRouter, Request
from database import db
from dependencies import get_current_user

router = APIRouter()


@router.get("/meetings/{meeting_id}/whiteboard")
async def get_whiteboard_strokes(meeting_id: str, request: Request):
    await get_current_user(request)
    strokes = await db.whiteboard_strokes.find(
        {"meeting_id": meeting_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(2000)
    return strokes

@router.delete("/meetings/{meeting_id}/whiteboard")
async def clear_whiteboard(meeting_id: str, request: Request):
    await get_current_user(request)
    result = await db.whiteboard_strokes.delete_many({"meeting_id": meeting_id})
    await db.whiteboard_notes.delete_many({"meeting_id": meeting_id})
    return {"deleted": result.deleted_count}

@router.get("/meetings/{meeting_id}/whiteboard/notes")
async def get_whiteboard_notes(meeting_id: str, request: Request):
    await get_current_user(request)
    notes = await db.whiteboard_notes.find(
        {"meeting_id": meeting_id}, {"_id": 0}
    ).to_list(200)
    return notes



