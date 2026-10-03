from fastapi import APIRouter

from app.api.v1 import ai, auth, dictionaries, health, studies

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(studies.router)
api_router.include_router(ai.router)
api_router.include_router(dictionaries.router)
