from pydantic import BaseModel, Field

from app.domain.enums import Role
from app.schemas.common import UserOut


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=72)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class DemoAccountOut(BaseModel):
    email: str
    password: str
    full_name: str
    role: Role
    specialty: str | None
