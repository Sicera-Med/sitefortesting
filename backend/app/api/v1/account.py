from fastapi import APIRouter, Response, status

from app.api.deps import AccountServiceDep, CurrentUser
from app.schemas.account import AccountOut, AccountPatch, PasswordIn

router = APIRouter(prefix="/account", tags=["account"])


@router.get("", response_model=AccountOut, summary="Мой профиль")
async def get_account(user: CurrentUser, service: AccountServiceDep) -> AccountOut:
    return AccountOut.build(service.view(user))


@router.patch("", response_model=AccountOut, summary="Изменить контакты и каналы уведомлений")
async def update_account(
    body: AccountPatch, user: CurrentUser, service: AccountServiceDep
) -> AccountOut:
    data = body.model_dump(exclude_unset=True)
    return AccountOut.build(service.update(user, **data))


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT, summary="Сменить пароль")
async def change_password(
    body: PasswordIn, user: CurrentUser, service: AccountServiceDep
) -> Response:
    service.change_password(user, old=body.old_password, new=body.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
