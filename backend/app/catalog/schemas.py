import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    PlainSerializer,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

SKU_MAX_LENGTH = 64
SKU_PATTERN = re.compile(r"[A-Z0-9._-]+")
PRICE_STEP = Decimal("0.01")
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None

    return value


def _reject_null(value: object) -> object:
    if value is None:
        raise PydanticCustomError("null_not_allowed", "Value cannot be null.")

    return value


def _lowercase(value: str | None) -> str | None:
    return value.lower() if value is not None else None


def _normalize_sku(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


def _check_sku(value: str) -> str:
    if len(value) > SKU_MAX_LENGTH or not SKU_PATTERN.fullmatch(value):
        raise PydanticCustomError(
            "sku_format",
            "SKU must be 1 to {max_length} characters: "
            "letters, digits, '-', '_' or '.'.",
            {"max_length": SKU_MAX_LENGTH},
        )

    return value


def _two_decimal_places(value: Decimal) -> Decimal:
    return value.quantize(PRICE_STEP)


def _price_text(value: Decimal) -> str:
    return f"{value:.2f}"


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

SupplierName = _required_name(200)
SupplierEmail = Annotated[
    EmailStr | None, BeforeValidator(_blank_to_none), AfterValidator(_lowercase)
]
Phone = _optional_text(50)
Notes = _optional_text(1000)

Sku = Annotated[str, BeforeValidator(_normalize_sku), AfterValidator(_check_sku)]
ProductName = _required_name(200)
ProductDescription = _optional_text(1000)
UnitPrice = Annotated[
    Decimal,
    Field(max_digits=12, decimal_places=2, ge=0),
    AfterValidator(_two_decimal_places),
]
PriceOut = Annotated[Decimal, PlainSerializer(_price_text, return_type=str)]
SearchText = _optional_text(200)


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


class SupplierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: SupplierName
    email: SupplierEmail = None
    phone: Phone = None
    notes: Notes = None


class SupplierUpdate(_UpdateModel):
    name: SupplierName | None = None
    email: SupplierEmail = None
    phone: Phone = None
    notes: Notes = None
    is_archived: StrictBool | None = None

    _required_fields_not_null = field_validator("name", "is_archived", mode="before")(
        _reject_null
    )


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    notes: str | None
    is_archived: bool
    created_at: datetime


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sku: Sku
    name: ProductName
    description: ProductDescription = None
    category_id: uuid.UUID
    supplier_id: uuid.UUID | None = None
    unit_price: UnitPrice


class ProductUpdate(_UpdateModel):
    sku: Sku | None = None
    name: ProductName | None = None
    description: ProductDescription = None
    category_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    unit_price: UnitPrice | None = None
    is_archived: StrictBool | None = None

    _required_fields_not_null = field_validator(
        "sku", "name", "category_id", "unit_price", "is_archived", mode="before"
    )(_reject_null)


class NamedReferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    name: str
    description: str | None
    unit_price: PriceOut
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    category: NamedReferenceOut
    supplier: NamedReferenceOut | None


class ProductListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    search: SearchText = None
    include_archived: bool = False
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(default=0, ge=0)
