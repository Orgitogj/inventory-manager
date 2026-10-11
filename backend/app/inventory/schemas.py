import uuid
from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

from app.catalog.schemas import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.inventory.models import MovementKind

MAX_QUANTITY = 1_000_000


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None

    return value


Quantity = Annotated[StrictInt, Field(ge=-MAX_QUANTITY, le=MAX_QUANTITY)]
Reason = Annotated[
    Annotated[str, StringConstraints(max_length=500)] | None,
    BeforeValidator(_blank_to_none),
]


class MovementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_id: uuid.UUID
    kind: MovementKind
    quantity: Quantity
    reason: Reason = Field(default=None, validate_default=True)

    @field_validator("reason")
    @classmethod
    def _adjustment_needs_reason(cls, reason: str | None, info: ValidationInfo):
        if info.data.get("kind") is MovementKind.ADJUSTMENT and reason is None:
            raise PydanticCustomError(
                "reason_required", "A reason is required for adjustments."
            )

        return reason


class MovementListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_id: uuid.UUID | None = None
    kind: MovementKind | None = None
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(default=0, ge=0)


class ProductRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    name: str


class UserRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class StockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product: ProductRefOut
    quantity: int


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: MovementKind
    quantity_change: int
    quantity_after: int
    reason: str | None
    created_at: datetime
    product: ProductRefOut
    created_by: UserRefOut


class StockListOut(BaseModel):
    stock: list[StockOut]
    total: int
    limit: int
    offset: int


class MovementListOut(BaseModel):
    movements: list[MovementOut]
    total: int
    limit: int
    offset: int
