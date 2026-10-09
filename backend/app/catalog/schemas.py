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


CategoryName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Description = Annotated[
    Annotated[str, StringConstraints(max_length=500)] | None,
    BeforeValidator(_blank_to_none),
]


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: CategoryName
    description: Description = None


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: CategoryName | None = None
    description: Description = None
    is_archived: StrictBool | None = None

    @field_validator("name", "is_archived", mode="before")
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


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    is_archived: bool
    created_at: datetime
