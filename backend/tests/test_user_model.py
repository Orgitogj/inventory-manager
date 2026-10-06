import pytest

from app.users.models import User, UserRole


def make_user(**overrides) -> User:
    data = {
        "email": "ana@example.com",
        "full_name": "Ana",
        "password_hash": "not-a-real-hash",
        "role": UserRole.SALES,
    }
    data.update(overrides)
    return User(**data)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Ana@Example.COM ", "ana@example.com"),
        ("ana@example.com", "ana@example.com"),
        ("\tSALES@shop.al\n", "sales@shop.al"),
    ],
)
def test_email_is_normalized(raw, expected):
    assert make_user(email=raw).email == expected


def test_email_is_normalized_on_update():
    user = make_user()
    user.email = " New@Example.com "
    assert user.email == "new@example.com"


def test_role_values_match_database_values():
    assert [role.value for role in UserRole] == ["admin", "warehouse", "sales"]


def test_repr_never_contains_password_hash():
    user = make_user(password_hash="secret-hash-value")
    assert "secret-hash-value" not in repr(user)
