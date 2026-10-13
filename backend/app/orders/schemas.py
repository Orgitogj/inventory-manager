import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.catalog.schemas import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PriceOut
from app.inventory.schemas import ProductRefOut, UserRefOut
from app.orders.models import OrderStatus

MAX_ITEMS = 100
MAX_QUANTITY = 1_000_000


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None

    return value


Notes = Annotated[
    Annotated[str, StringConstraints(max_length=1000)] | None,
    BeforeValidator(_blank_to_none),
]
ItemQuantity = Annotated[StrictInt, Field(ge=1, le=MAX_QUANTITY)]


class OrderItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_id: uuid.UUID
    quantity: ItemQuantity


class _ItemsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[OrderItemIn] = Field(default_factory=list, max_length=MAX_ITEMS)

    @field_validator("items")
    @classmethod
    def _products_are_unique(cls, items: list[OrderItemIn]) -> list[OrderItemIn]:
        product_ids = [item.product_id for item in items]

        if len(set(product_ids)) != len(product_ids):
            raise PydanticCustomError(
                "duplicate_product", "Each product can appear only once."
            )

        return items


class OrderCreate(_ItemsModel):
    customer_id: uuid.UUID
    notes: Notes = None


class OrderItemsReplace(_ItemsModel):
    pass


class OrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    customer_id: uuid.UUID | None = None
    notes: Notes = None

    @field_validator("customer_id", mode="before")
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


class OrderListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: OrderStatus | None = None
    customer_id: uuid.UUID | None = None
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(default=0, ge=0)


class CustomerRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product: ProductRefOut
    quantity: int
    unit_price: PriceOut

    @computed_field
    @property
    def line_total(self) -> str:
        return f"{self.unit_price * self.quantity:.2f}"


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    status: OrderStatus
    notes: str | None
    customer: CustomerRefOut
    created_by: UserRefOut
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    items: list[OrderItemOut]

    @computed_field
    @property
    def total_amount(self) -> str:
        total = sum(
            (item.unit_price * item.quantity for item in self.items), Decimal(0)
        )
        return f"{total:.2f}"


class OrderListOut(BaseModel):
    orders: list[OrderOut]
    total: int
    limit: int
    offset: int
