import pytest
from pydantic import ValidationError

from app.users.models import UserRole
from app.users.schemas import StaffCreate, describe_validation_error

VALID = {
    "email": "ana@example.com",
    "full_name": "Ana Hoxha",
    "password": "long-enough-password",
    "role": "warehouse",
}


def make(**overrides) -> StaffCreate:
    return StaffCreate(**{**VALID, **overrides})


def error_fields(error: ValidationError) -> set[str]:
    return {str(detail["loc"][0]) for detail in error.errors()}


def test_valid_input_is_accepted():
    data = make(email="  Ana@Example.com ", full_name="  Ana Hoxha  ")

    assert data.email.lower() == "ana@example.com"
    assert data.full_name == "Ana Hoxha"
    assert data.role is UserRole.WAREHOUSE
    assert data.password.get_secret_value() == VALID["password"]


def test_password_is_hidden_in_repr():
    assert VALID["password"] not in repr(make())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("password", "x" * 11),
        ("password", "x" * 129),
        ("email", "not-an-email"),
        ("email", "ana@"),
        ("full_name", "   "),
        ("full_name", "x" * 201),
        ("role", "owner"),
        ("role", "ADMIN"),
    ],
)
def test_invalid_input_is_rejected(field, value):
    with pytest.raises(ValidationError) as error:
        make(**{field: value})

    assert error_fields(error.value) == {field}


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError) as error:
        make(is_active=False)

    assert error_fields(error.value) == {"is_active"}


def test_error_description_never_contains_the_password():
    secret = "short-pw"

    with pytest.raises(ValidationError) as error:
        make(password=secret)

    description = describe_validation_error(error.value)

    assert description.startswith("password:")
    assert secret not in description
