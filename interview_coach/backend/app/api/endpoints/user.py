from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database.db_manager import DatabaseManager

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    preferred_voice: str = Field(default="female", pattern="^(male|female)$")


@router.get("")
def list_users():
    db = DatabaseManager()
    users = db.list_users()
    return {
        "users": [
            {"id": user.id, "name": user.name, "preferred_voice": user.preferred_voice}
            for user in users
        ]
    }


@router.post("")
def create_user(payload: UserCreate):
    db = DatabaseManager()
    try:
        user = db.create_user(payload.name, preferred_voice=payload.preferred_voice)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": user.id, "name": user.name, "preferred_voice": user.preferred_voice}