import uuid
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    SecretStr,
    StringConstraints,
    ValidationError,
    field_validator,
)
from pydantic_core import PydanticCustomError

from app.users.models import UserRole

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128


def _check_password_length(value: SecretStr) -> SecretStr:
    length = len(value.get_secret_value())

    if not PASSWORD_MIN_LENGTH <= length <= PASSWORD_MAX_LENGTH:
        raise PydanticCustomError(
            "password_length",
            "Password must be between {min_length} and {max_length} characters.",
            {"min_length": PASSWORD_MIN_LENGTH, "max_length": PASSWORD_MAX_LENGTH},
        )

    return value


Password = Annotated[SecretStr, AfterValidator(_check_password_length)]


class StaffCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    email: EmailStr
    full_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    password: Password
    role: UserRole

    @field_validator("email", mode="before")
    @classmethod
    def _strip_email(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole


def describe_validation_error(error: ValidationError) -> str:
    return "\n".join(
        f"{'.'.join(str(part) for part in detail['loc'])}: {detail['msg']}"
        for detail in error.errors(include_input=False, include_url=False)
    )
