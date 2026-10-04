from fastapi import APIRouter

from app.api.v1 import (
    account,
    ai,
    appointments,
    auth,
    dictionaries,
    health,
    metrics,
    notifications,
    staff,
    studies,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(account.router)
api_router.include_router(studies.router)
api_router.include_router(ai.router)
api_router.include_router(notifications.router)
api_router.include_router(appointments.router)
api_router.include_router(metrics.router)
api_router.include_router(staff.router)
api_router.include_router(dictionaries.router)
