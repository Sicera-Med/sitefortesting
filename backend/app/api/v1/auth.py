from fastapi import APIRouter

from app.api.deps import AuthServiceDep, CurrentUser, SettingsDep
from app.core.errors import NotFoundError
from app.schemas.auth import DemoAccountOut, LoginIn, TokenOut
from app.schemas.common import UserOut
from app.seed import DEMO_PASSWORD

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut, summary="Вход по email и паролю")
async def login(body: LoginIn, auth: AuthServiceDep) -> TokenOut:
    token, user = auth.login(body.email, body.password)
    return TokenOut(access_token=token, user=UserOut.build(user, auth.patient_profile(user)))


@router.get("/me", response_model=UserOut, summary="Текущий пользователь")
async def me(user: CurrentUser, auth: AuthServiceDep) -> UserOut:
    return UserOut.build(user, auth.patient_profile(user))


@router.get(
    "/demo-users",
    response_model=list[DemoAccountOut],
    summary="Демо-аккаунты для кнопок быстрого входа (не в prod)",
)
async def demo_users(auth: AuthServiceDep, settings: SettingsDep) -> list[DemoAccountOut]:
    if settings.APP_ENV == "prod":
        raise NotFoundError("Not Found")
    return [
        DemoAccountOut(
            email=u.email,
            password=DEMO_PASSWORD,
            full_name=u.full_name,
            role=u.role,
            specialty=u.specialty,
        )
        for u in auth.demo_accounts()
    ]
