import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    SecretStr,
    StrictBool,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
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


FullName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Password = Annotated[SecretStr, AfterValidator(_check_password_length)]


class StaffCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    email: EmailStr
    full_name: FullName
    password: Password
    role: UserRole

    @field_validator("email", mode="before")
    @classmethod
    def _strip_email(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class StaffUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    full_name: FullName | None = None
    role: UserRole | None = None
    is_active: StrictBool | None = None

    @field_validator("full_name", "role", "is_active", mode="before")
    @classmethod
    def _reject_null(cls, value: object) -> object:
        if value is None:
            raise PydanticCustomError("null_not_allowed", "Value cannot be null.")

        return value

    @model_validator(mode="after")
    def _require_a_change(self) -> Self:
        if not self.model_fields_set:
            raise PydanticCustomError(
                "no_changes", "At least one field must be provided."
            )

        return self


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole


class StaffOut(UserOut):
    is_active: bool
    created_at: datetime


def validation_error_details(error: ValidationError) -> list[dict[str, str]]:
    return [
        {
            "field": ".".join(str(part) for part in detail["loc"]) or "body",
            "message": detail["msg"],
        }
        for detail in error.errors(
            include_input=False, include_url=False, include_context=False
        )
    ]


def describe_validation_error(error: ValidationError) -> str:
    return "\n".join(
        f"{detail['field']}: {detail['message']}"
        for detail in validation_error_details(error)
    )
