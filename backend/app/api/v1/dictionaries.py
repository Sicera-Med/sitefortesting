from fastapi import APIRouter

from app.domain.dictionaries import all_dictionaries

router = APIRouter(prefix="/dictionaries", tags=["dictionaries"])


# Публичный: справочники клиники не секретны, нужны уже на странице входа
@router.get("", summary="Все справочники: [{code, label}]")
async def dictionaries() -> dict[str, list[dict[str, str]]]:
    return all_dictionaries()
