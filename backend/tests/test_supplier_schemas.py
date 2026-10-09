import pytest
from pydantic import ValidationError

from app.catalog.schemas import SupplierCreate, SupplierUpdate


def error_fields(error: ValidationError) -> set[str]:
    return {".".join(str(part) for part in detail["loc"]) for detail in error.errors()}


def test_all_fields_are_cleaned():
    data = SupplierCreate(
        name="  Alfa Sh.p.k.  ",
        email="  Info@Alfa.AL ",
        phone="  +355 69 123 4567 ",
        notes="  Dorëzim të hënave  ",
    )

    assert data.name == "Alfa Sh.p.k."
    assert data.email == "info@alfa.al"
    assert data.phone == "+355 69 123 4567"
    assert data.notes == "Dorëzim të hënave"


def test_only_name_is_required():
    data = SupplierCreate(name="Alfa")

    assert data.model_dump() == {
        "name": "Alfa",
        "email": None,
        "phone": None,
        "notes": None,
    }


@pytest.mark.parametrize("field", ["email", "phone", "notes"])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_blank_optional_fields_become_none(field, value):
    data = SupplierCreate.model_validate({"name": "Alfa", field: value})

    assert getattr(data, field) is None


@pytest.mark.parametrize("email", ["not-an-email", "info@", "@alfa.al", "info alfa.al"])
def test_invalid_email_is_rejected(email):
    with pytest.raises(ValidationError) as error:
        SupplierCreate(name="Alfa", email=email)

    assert error_fields(error.value) == {"email"}


def test_length_limits_are_inclusive():
    data = SupplierCreate(name="x" * 200, phone="1" * 50, notes="n" * 1000)

    assert len(data.name) == 200
    assert len(data.phone) == 50
    assert len(data.notes) == 1000


def test_length_is_measured_after_stripping():
    data = SupplierCreate(name=f"  {'x' * 200}  ", phone=f"  {'1' * 50}  ")

    assert len(data.name) == 200
    assert len(data.phone) == 50


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({}, "name"),
        ({"name": "   "}, "name"),
        ({"name": "x" * 201}, "name"),
        ({"name": "Alfa", "phone": "1" * 51}, "phone"),
        ({"name": "Alfa", "notes": "n" * 1001}, "notes"),
        ({"name": "Alfa", "is_archived": True}, "is_archived"),
        ({"name": "Alfa", "unknown": "x"}, "unknown"),
    ],
)
def test_invalid_create_input_is_rejected(payload, field):
    with pytest.raises(ValidationError) as error:
        SupplierCreate.model_validate(payload)

    assert error_fields(error.value) == {field}


def test_update_keeps_only_sent_fields():
    data = SupplierUpdate.model_validate({"email": " Sales@Alfa.AL "})

    assert data.model_dump(exclude_unset=True) == {"email": "sales@alfa.al"}


@pytest.mark.parametrize("field", ["email", "phone", "notes"])
@pytest.mark.parametrize("value", [None, "", "  "])
def test_update_allows_clearing_optional_fields(field, value):
    data = SupplierUpdate.model_validate({field: value})

    assert data.model_dump(exclude_unset=True) == {field: None}


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({}, ""),
        ({"name": None}, "name"),
        ({"name": "  "}, "name"),
        ({"is_archived": None}, "is_archived"),
        ({"is_archived": 1}, "is_archived"),
        ({"email": "not-an-email"}, "email"),
        ({"unknown": "x"}, "unknown"),
    ],
)
def test_invalid_update_input_is_rejected(payload, field):
    with pytest.raises(ValidationError) as error:
        SupplierUpdate.model_validate(payload)

    assert error_fields(error.value) == {field}
