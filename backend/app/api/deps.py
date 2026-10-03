from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.ai.base import AIProvider
from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.domain.enums import Role
from app.domain.models import User
from app.services.ai_service import AIService
from app.services.appointments import AppointmentService
from app.services.auth import AuthService
from app.services.metrics import MetricsService
from app.services.notifications import NotificationService
from app.services.studies import StudyService
from app.store import Store

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_store(request: Request) -> Store:
    return request.app.state.store


StoreDep = Annotated[Store, Depends(get_store)]


def get_ai_provider(request: Request) -> AIProvider:
    return request.app.state.ai


# --- Сервисы ---


def get_auth_service(store: StoreDep, settings: SettingsDep) -> AuthService:
    return AuthService(store, settings)


def get_ai_service(
    store: StoreDep, settings: SettingsDep, provider: AIProvider = Depends(get_ai_provider)
) -> AIService:
    return AIService(provider, store, timeout_s=settings.AI_TIMEOUT_S)


def get_study_service(store: StoreDep, ai: AIService = Depends(get_ai_service)) -> StudyService:
    return StudyService(store, ai)


def get_notification_service(store: StoreDep) -> NotificationService:
    return NotificationService(store)


def get_appointment_service(store: StoreDep, settings: SettingsDep) -> AppointmentService:
    return AppointmentService(store, tz=settings.CLINIC_TZ)


def get_metrics_service(store: StoreDep, settings: SettingsDep) -> MetricsService:
    return MetricsService(store, high_confidence=settings.AI_HIGH_CONFIDENCE)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
AIServiceDep = Annotated[AIService, Depends(get_ai_service)]
StudyServiceDep = Annotated[StudyService, Depends(get_study_service)]
NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]
AppointmentServiceDep = Annotated[AppointmentService, Depends(get_appointment_service)]
MetricsServiceDep = Annotated[MetricsService, Depends(get_metrics_service)]

# --- Текущий пользователь и роли ---

_bearer = HTTPBearer(auto_error=False, description="JWT из POST /auth/login")


def get_current_user(
    auth: AuthServiceDep,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Требуется авторизация")
    return auth.user_from_token(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[[User], User]:
    def dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ForbiddenError("Недостаточно прав для этого действия")
        return user

    return dependency


StaffUser = Annotated[User, Depends(require_roles(Role.DOCTOR, Role.HEAD))]
DoctorUser = Annotated[User, Depends(require_roles(Role.DOCTOR))]
HeadUser = Annotated[User, Depends(require_roles(Role.HEAD))]
PatientUser = Annotated[User, Depends(require_roles(Role.PATIENT))]
