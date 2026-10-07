import pytest
from database_guard import UnsafeTestDatabaseError, require_test_database_url


def test_accepts_database_name_ending_with_test():
    url = require_test_database_url(
        "postgresql+psycopg://inventory:secret@127.0.0.1:55433/inventory_test"
    )

    assert url.database == "inventory_test"


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg://inventory:secret@127.0.0.1:55432/inventory_dev",
        "postgresql+psycopg://inventory:secret@127.0.0.1:55432/inventory",
        "postgresql+psycopg://inventory:secret@127.0.0.1:55433/inventory_testing",
        "postgresql+psycopg://inventory:secret@127.0.0.1:55433",
    ],
)
def test_refuses_database_name_not_ending_with_test(database_url):
    with pytest.raises(UnsafeTestDatabaseError):
        require_test_database_url(database_url)


def test_refusal_message_never_contains_password():
    with pytest.raises(UnsafeTestDatabaseError) as error:
        require_test_database_url(
            "postgresql+psycopg://inventory:top-secret@127.0.0.1:55432/inventory_dev"
        )

    assert "top-secret" not in str(error.value)
    assert "inventory_dev" in str(error.value)
