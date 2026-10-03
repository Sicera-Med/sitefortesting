from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)

# Здесь будут добавляться роутеры по мере этапов:
# api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
# api_router.include_router(studies.router, prefix="/studies", tags=["studies"])
# ...
