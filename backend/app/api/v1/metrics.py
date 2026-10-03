from fastapi import APIRouter

from app.api.deps import HeadUser, MetricsServiceDep
from app.schemas.metrics import DashboardOut

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/dashboard", response_model=DashboardOut, summary="Дашборд заведующего")
async def dashboard(user: HeadUser, service: MetricsServiceDep) -> DashboardOut:
    return DashboardOut.model_validate(service.dashboard())
