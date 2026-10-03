from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.store import Store

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_store(request: Request) -> Store:
    return request.app.state.store


StoreDep = Annotated[Store, Depends(get_store)]
