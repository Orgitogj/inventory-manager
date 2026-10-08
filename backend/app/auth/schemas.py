from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.users.schemas import PASSWORD_MAX_LENGTH


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
