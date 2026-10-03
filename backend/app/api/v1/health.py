from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.api.deps import SettingsDep

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    env: str
    version: str


class VersionResponse(BaseModel):
    name: str
    version: str
    api_prefix: str


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    description="Возвращает 200, если процесс жив. Не проверяет зависимости.",
)
async def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        env=settings.APP_ENV,
        version=settings.APP_VERSION,
    )


@router.get(
    "/version",
    response_model=VersionResponse,
    status_code=status.HTTP_200_OK,
    summary="Метаданные сервиса",
)
async def version(settings: SettingsDep) -> VersionResponse:
    return VersionResponse(
        name=settings.APP_NAME,
        version=settings.APP_VERSION,
        api_prefix=settings.API_PREFIX,
    )
