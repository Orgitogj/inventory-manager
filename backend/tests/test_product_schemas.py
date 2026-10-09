import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.catalog.schemas import (
    ProductCreate,
    ProductListQuery,
    ProductOut,
    ProductUpdate,
)

CATEGORY_ID = "11111111-1111-1111-1111-111111111111"
SUPPLIER_ID = "22222222-2222-2222-2222-222222222222"
SKU_MESSAGE = "SKU must be 1 to 64 characters: letters, digits, '-', '_' or '.'."


def payload(**overrides) -> dict:
    data = {
        "sku": "AB-12",
        "name": "Ujë 0.5L",
        "category_id": CATEGORY_ID,
        "unit_price": "12.50",
    }
    data.update(overrides)
    return data


def make(**overrides) -> ProductCreate:
    return ProductCreate.model_validate(payload(**overrides))


def error_fields(error: ValidationError) -> set[str]:
    return {".".join(str(part) for part in detail["loc"]) for detail in error.errors()}


def test_values_are_cleaned():
    data = make(
        sku="  ab-12 ",
        name="  Ujë 0.5L ",
        description="  Shishe plastike  ",
        supplier_id=SUPPLIER_ID,
    )

    assert data.sku == "AB-12"
    assert data.name == "Ujë 0.5L"
    assert data.description == "Shishe plastike"
    assert data.category_id == uuid.UUID(CATEGORY_ID)
    assert data.supplier_id == uuid.UUID(SUPPLIER_ID)


def test_supplier_and_description_are_optional():
    data = make()

    assert data.supplier_id is None
    assert data.description is None


@pytest.mark.parametrize("description", ["", "   ", None])
def test_blank_description_becomes_none(description):
    assert make(description=description).description is None


@pytest.mark.parametrize("sku", ["a", "A.B_C-1", "x" * 64, "  abc123  "])
def test_valid_sku_is_accepted_in_upper_case(sku):
    assert make(sku=sku).sku == sku.strip().upper()


@pytest.mark.parametrize(
    "sku", ["", "   ", "AB 12", "AB/12", "AB#12", "ÇA-1", "AB\n12", "x" * 65]
)
def test_invalid_sku_is_rejected_with_a_clear_message(sku):
    with pytest.raises(ValidationError) as error:
        make(sku=sku)

    details = error.value.errors()
    assert [detail["loc"] for detail in details] == [("sku",)]
    assert details[0]["msg"] == SKU_MESSAGE


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12.5", "12.50"),
        ("12.50", "12.50"),
        (12.5, "12.50"),
        (12, "12.00"),
        ("0", "0.00"),
        ("9999999999.99", "9999999999.99"),
    ],
)
def test_price_is_a_decimal_with_two_places(value, expected):
    price = make(unit_price=value).unit_price

    assert isinstance(price, Decimal)
    assert str(price) == expected


@pytest.mark.parametrize(
    "value",
    [
        1.999,
        "1.999",
        -1,
        "-0.01",
        "abc",
        "",
        None,
        "NaN",
        "Infinity",
        "-Infinity",
        "10000000000.00",
    ],
)
def test_invalid_price_is_rejected(value):
    with pytest.raises(ValidationError) as error:
        make(unit_price=value)

    assert error_fields(error.value) == {"unit_price"}


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"name": "   "}, "name"),
        ({"name": "x" * 201}, "name"),
        ({"description": "x" * 1001}, "description"),
        ({"category_id": "not-a-uuid"}, "category_id"),
        ({"category_id": None}, "category_id"),
        ({"supplier_id": "not-a-uuid"}, "supplier_id"),
        ({"is_archived": True}, "is_archived"),
        ({"stock": 5}, "stock"),
    ],
)
def test_invalid_create_input_is_rejected(overrides, field):
    with pytest.raises(ValidationError) as error:
        make(**overrides)

    assert error_fields(error.value) == {field}


@pytest.mark.parametrize("field", ["sku", "name", "category_id", "unit_price"])
def test_required_fields_cannot_be_missing(field):
    data = payload()
    del data[field]

    with pytest.raises(ValidationError) as error:
        ProductCreate.model_validate(data)

    assert error_fields(error.value) == {field}


def test_update_keeps_only_sent_fields_and_cleans_them():
    data = ProductUpdate.model_validate({"sku": " ab-13 ", "unit_price": "7"})

    assert data.model_dump(exclude_unset=True) == {
        "sku": "AB-13",
        "unit_price": Decimal("7.00"),
    }
    assert str(data.unit_price) == "7.00"


@pytest.mark.parametrize("field", ["description", "supplier_id"])
def test_update_allows_clearing_optional_fields(field):
    data = ProductUpdate.model_validate({field: None})

    assert data.model_dump(exclude_unset=True) == {field: None}


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({}, ""),
        ({"sku": None}, "sku"),
        ({"name": None}, "name"),
        ({"category_id": None}, "category_id"),
        ({"unit_price": None}, "unit_price"),
        ({"is_archived": None}, "is_archived"),
        ({"is_archived": 1}, "is_archived"),
        ({"sku": "bad sku"}, "sku"),
        ({"unit_price": "1.999"}, "unit_price"),
        ({"created_at": "2026-01-01T00:00:00Z"}, "created_at"),
    ],
)
def test_invalid_update_input_is_rejected(data, field):
    with pytest.raises(ValidationError) as error:
        ProductUpdate.model_validate(data)

    assert error_fields(error.value) == {field}


def product_like(**overrides):
    values = {
        "id": uuid.uuid4(),
        "sku": "AB-12",
        "name": "Ujë",
        "description": None,
        "unit_price": Decimal("12.5"),
        "is_archived": False,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 2, tzinfo=UTC),
        "category": {"id": uuid.UUID(CATEGORY_ID), "name": "Pije"},
        "supplier": None,
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        (Decimal("12.5"), "12.50"),
        (Decimal(12), "12.00"),
        (Decimal("0.10"), "0.10"),
        (Decimal("1234567890.12"), "1234567890.12"),
    ],
)
def test_price_is_serialized_as_a_string_with_two_places(price, expected):
    body = ProductOut.model_validate(product_like(unit_price=price)).model_dump(
        mode="json"
    )

    assert body["unit_price"] == expected
    assert body["category"] == {"id": CATEGORY_ID, "name": "Pije"}
    assert body["supplier"] is None


def test_list_query_defaults():
    query = ProductListQuery.model_validate({})

    assert query.model_dump() == {
        "category_id": None,
        "supplier_id": None,
        "search": None,
        "include_archived": False,
        "limit": 50,
        "offset": 0,
    }


def test_list_query_parses_strings_from_the_url():
    query = ProductListQuery.model_validate(
        {
            "category_id": CATEGORY_ID,
            "search": "  ujë ",
            "include_archived": "true",
            "limit": "200",
            "offset": "10",
        }
    )

    assert query.category_id == uuid.UUID(CATEGORY_ID)
    assert query.search == "ujë"
    assert query.include_archived is True
    assert query.limit == 200
    assert query.offset == 10


def test_blank_search_means_no_search():
    assert ProductListQuery.model_validate({"search": "   "}).search is None


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"limit": "0"}, "limit"),
        ({"limit": "201"}, "limit"),
        ({"limit": "abc"}, "limit"),
        ({"offset": "-1"}, "offset"),
        ({"category_id": "abc"}, "category_id"),
        ({"supplier_id": "abc"}, "supplier_id"),
        ({"include_archived": "maybe"}, "include_archived"),
        ({"search": "x" * 201}, "search"),
        ({"sort": "name"}, "sort"),
    ],
)
def test_invalid_list_query_is_rejected(data, field):
    with pytest.raises(ValidationError) as error:
        ProductListQuery.model_validate(data)

    assert error_fields(error.value) == {field}
