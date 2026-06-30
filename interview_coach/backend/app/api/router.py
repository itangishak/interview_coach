from fastapi import APIRouter

from app.api.endpoints import interview

api_router = APIRouter()
api_router.include_router(interview.router)