import uuid
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

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
