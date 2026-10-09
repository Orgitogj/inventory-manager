import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None

    return value


def _reject_null(value: object) -> object:
    if value is None:
        raise PydanticCustomError("null_not_allowed", "Value cannot be null.")

    return value


def _required_name(max_length: int):
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length),
    ]


def _optional_text(max_length: int):
    return Annotated[
        Annotated[str, StringConstraints(max_length=max_length)] | None,
        BeforeValidator(_blank_to_none),
    ]


CategoryName = _required_name(100)
Description = _optional_text(500)


class _UpdateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _require_a_change(self) -> Self:
        if not self.model_fields_set:
            raise PydanticCustomError(
                "no_changes", "At least one field must be provided."
            )

        return self


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: CategoryName
    description: Description = None


class CategoryUpdate(_UpdateModel):
    name: CategoryName | None = None
    description: Description = None
    is_archived: StrictBool | None = None

    _required_fields_not_null = field_validator("name", "is_archived", mode="before")(
        _reject_null
    )


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    is_archived: bool
    created_at: datetime
