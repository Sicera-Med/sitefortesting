from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.domain.dictionaries import all_dictionaries

router = APIRouter(prefix="/dictionaries", tags=["dictionaries"])


@router.get("", summary="Все справочники: [{code, label}]")
async def dictionaries(user: CurrentUser) -> dict[str, list[dict[str, str]]]:
    return all_dictionaries()
