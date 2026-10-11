import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.config import Settings
from app.database import violated_constraint
from app.users.models import UserRole
from app.users.schemas import StaffCreate
from app.users.service import create_user

pytestmark = pytest.mark.db

PASSWORD = "long-enough-password"
CUSTOMERS_URL = "/api/v1/customers"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"
INSERT = text(
    "INSERT INTO customers (id, name, email) VALUES (gen_random_uuid(), :name, :email)"
)


@pytest.fixture
def app(db_session_factory) -> FastAPI:
    app = create_app(Settings(app_env="testing", database_url=None, _env_file=None))
    app.state.session_factory = db_session_factory
    return app


def logged_in(app: FastAPI, db_session, email: str, role: UserRole):
    create_user(
        db_session,
        StaffCreate(email=email, full_name="Staff", password=PASSWORD, role=role),
    )
    db_session.commit()

    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    return client, {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture
def admin(app, db_session) -> tuple[TestClient, dict[str, str]]:
    return logged_in(app, db_session, "admin@shop.al", UserRole.ADMIN)


@pytest.fixture
def sales(app, db_session) -> tuple[TestClient, dict[str, str]]:
    return logged_in(app, db_session, "shitje@shop.al", UserRole.SALES)


@pytest.fixture
def warehouse(app, db_session) -> tuple[TestClient, dict[str, str]]:
    return logged_in(app, db_session, "magazina@shop.al", UserRole.WAREHOUSE)


def create(user, **payload):
    client, csrf = user
    return client.post(CUSTOMERS_URL, json=payload, headers=csrf)


def patch(user, customer_id: str, **payload):
    client, csrf = user
    return client.patch(f"{CUSTOMERS_URL}/{customer_id}", json=payload, headers=csrf)


def add_customer(user, name: str, **extra) -> dict:
    response = create(user, name=name, **extra)
    assert response.status_code == 201, response.json()
    return response.json()


def listed(user, query: str = "") -> list[str]:
    client, _ = user
    response = client.get(f"{CUSTOMERS_URL}{query}")
    assert response.status_code == 200, response.json()
    return [customer["name"] for customer in response.json()["customers"]]


def error_code(response) -> str:
    return response.json()["error"]["code"]


def error_fields(response) -> list[str]:
    return [detail["field"] for detail in response.json()["error"]["details"]]


def test_sales_creates_a_customer_with_cleaned_values(sales):
    response = create(
        sales,
        name="  Market Ana  ",
        email="  Ana@Market.AL ",
        phone=" 069 123 4567 ",
        address="  Rruga e Durrësit 10, Tiranë ",
        notes="   ",
    )
    body = response.json()

    assert response.status_code == 201
    assert body["name"] == "Market Ana"
    assert body["email"] == "ana@market.al"
    assert body["phone"] == "069 123 4567"
    assert body["address"] == "Rruga e Durrësit 10, Tiranë"
    assert body["notes"] is None
    assert body["is_archived"] is False


def test_two_customers_can_share_a_name(sales):
    add_customer(sales, "Ana Hoxha")
    add_customer(sales, "ana hoxha")

    assert sorted(listed(sales)) == ["Ana Hoxha", "ana hoxha"]


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({}, "name"),
        ({"name": "   "}, "name"),
        ({"name": "x" * 201}, "name"),
        ({"name": "Ana", "email": "not-an-email"}, "email"),
        ({"name": "Ana", "address": "x" * 501}, "address"),
        ({"name": "Ana", "is_archived": True}, "is_archived"),
    ],
)
def test_invalid_input_is_rejected(sales, payload, field):
    response = create(sales, **payload)

    assert response.status_code == 422
    assert error_fields(response) == [field]


def test_warehouse_can_read_but_not_write(admin, warehouse):
    customer = add_customer(admin, "Market Ana")

    assert listed(warehouse) == ["Market Ana"]
    assert create(warehouse, name="Tjetër").status_code == 403
    assert patch(warehouse, customer["id"], name="Tjetër").status_code == 403


def test_anonymous_user_gets_401(app):
    assert TestClient(app).get(CUSTOMERS_URL).status_code == 401


def test_write_without_csrf_is_rejected(sales):
    client, _ = sales
    response = client.post(CUSTOMERS_URL, json={"name": "Ana"})

    assert response.status_code == 403
    assert error_code(response) == "csrf_failed"


def test_search_matches_name_email_or_phone(sales):
    add_customer(sales, "Market Ana", email="ana@market.al")
    add_customer(sales, "Bar Drini", phone="0691112222")
    add_customer(sales, "Furra 100%")

    assert listed(sales, "?search=MARKET") == ["Market Ana"]
    assert listed(sales, "?search=ana@") == ["Market Ana"]
    assert listed(sales, "?search=111") == ["Bar Drini"]
    assert listed(sales, "?search=100%25") == ["Furra 100%"]
    assert listed(sales, "?search=%25") == ["Furra 100%"]


def test_list_is_paginated_and_sorted_by_name(sales):
    for name in ["Cikli", "ana", "Besa"]:
        add_customer(sales, name)

    client, _ = sales
    body = client.get(f"{CUSTOMERS_URL}?limit=2&offset=1").json()

    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert [customer["name"] for customer in body["customers"]] == ["Besa", "Cikli"]


def test_archived_customers_are_hidden_by_default(sales):
    customer = add_customer(sales, "Market Ana")
    add_customer(sales, "Bar Drini")

    response = patch(sales, customer["id"], is_archived=True)

    assert response.status_code == 200
    assert listed(sales) == ["Bar Drini"]
    assert listed(sales, "?include_archived=true") == ["Bar Drini", "Market Ana"]


def test_get_returns_one_customer(sales):
    customer = add_customer(sales, "Market Ana")
    client, _ = sales

    response = client.get(f"{CUSTOMERS_URL}/{customer['id']}")

    assert response.status_code == 200
    assert response.json() == customer


def test_unknown_customer_returns_404(sales):
    client, _ = sales

    assert client.get(f"{CUSTOMERS_URL}/{UNKNOWN_ID}").status_code == 404
    assert patch(sales, UNKNOWN_ID, name="Ana").status_code == 404


def test_null_clears_optional_fields_and_keeps_the_rest(sales):
    customer = add_customer(
        sales, "Market Ana", email="ana@market.al", phone="069", address="Tiranë"
    )

    response = patch(sales, customer["id"], email=None, address=None)
    body = response.json()

    assert response.status_code == 200
    assert body["name"] == "Market Ana"
    assert body["email"] is None
    assert body["phone"] == "069"
    assert body["address"] is None


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({}, "body"),
        ({"name": None}, "name"),
        ({"name": ""}, "name"),
        ({"is_archived": None}, "is_archived"),
        ({"is_archived": "yes"}, "is_archived"),
        ({"created_at": "2026-01-01"}, "created_at"),
    ],
)
def test_invalid_update_is_rejected(sales, payload, field):
    customer = add_customer(sales, "Market Ana")

    response = patch(sales, customer["id"], **payload)

    assert response.status_code == 422
    assert error_fields(response) == [field]


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("?limit=0", "limit"),
        ("?limit=201", "limit"),
        ("?offset=-1", "offset"),
        ("?include_archived=maybe", "include_archived"),
        ("?sort=name", "sort"),
    ],
)
def test_invalid_query_params_are_rejected(sales, query, field):
    client, _ = sales
    response = client.get(f"{CUSTOMERS_URL}{query}")

    assert response.status_code == 422
    assert error_fields(response) == [field]


@pytest.mark.parametrize(
    ("name", "email", "constraint"),
    [
        (" Ana", None, "ck_customers_name_trimmed"),
        ("", None, "ck_customers_name_trimmed"),
        ("Ana", "Ana@Market.al", "ck_customers_email_normalized"),
    ],
)
def test_database_rejects_unnormalized_values(db_session, name, email, constraint):
    with pytest.raises(IntegrityError) as error:
        db_session.execute(INSERT, {"name": name, "email": email})

    assert violated_constraint(error.value) == constraint
