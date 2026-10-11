import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.catalog.schemas import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Notes,
    Phone,
    SearchText,
    SupplierEmail,
)

CustomerName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Email = SupplierEmail


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None

    return value


def _reject_null(value: object) -> object:
    if value is None:
        raise PydanticCustomError("null_not_allowed", "Value cannot be null.")

    return value


Address = Annotated[
    Annotated[str, StringConstraints(max_length=500)] | None,
    BeforeValidator(_blank_to_none),
]


class CustomerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: CustomerName
    email: Email = None
    phone: Phone = None
    address: Address = None
    notes: Notes = None


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: CustomerName | None = None
    email: Email = None
    phone: Phone = None
    address: Address = None
    notes: Notes = None
    is_archived: StrictBool | None = None

    _required_fields_not_null = field_validator("name", "is_archived", mode="before")(
        _reject_null
    )

    @model_validator(mode="after")
    def _require_a_change(self) -> Self:
        if not self.model_fields_set:
            raise PydanticCustomError(
                "no_changes", "At least one field must be provided."
            )

        return self


class CustomerListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    search: SearchText = None
    include_archived: bool = False
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(default=0, ge=0)


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    address: str | None
    notes: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class CustomerListOut(BaseModel):
    customers: list[CustomerOut]
    total: int
    limit: int
    offset: int
