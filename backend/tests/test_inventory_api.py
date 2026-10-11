import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app
from app.config import Settings
from app.users.models import UserRole
from app.users.schemas import StaffCreate
from app.users.service import create_user

pytestmark = pytest.mark.db

PASSWORD = "long-enough-password"
STOCK_URL = "/api/v1/inventory/stock"
MOVEMENTS_URL = "/api/v1/inventory/movements"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def app(db_session_factory) -> Flask:
    app = create_app(Settings(app_env="testing", database_url=None, _env_file=None))
    app.extensions["database_sessionmaker"] = db_session_factory
    return app


def logged_in(app: Flask, db_session, email: str, role: UserRole):
    create_user(
        db_session,
        StaffCreate(
            email=email, full_name=role.value.title(), password=PASSWORD, role=role
        ),
    )
    db_session.commit()

    client = app.test_client()
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    return client, {"X-CSRF-Token": response.get_json()["csrf_token"]}


@pytest.fixture
def admin(app, db_session) -> tuple[FlaskClient, dict[str, str]]:
    return logged_in(app, db_session, "admin@shop.al", UserRole.ADMIN)


@pytest.fixture
def warehouse(app, db_session) -> tuple[FlaskClient, dict[str, str]]:
    return logged_in(app, db_session, "magazina@shop.al", UserRole.WAREHOUSE)


@pytest.fixture
def sales(app, db_session) -> tuple[FlaskClient, dict[str, str]]:
    return logged_in(app, db_session, "shitje@shop.al", UserRole.SALES)


def post(user, url: str, **payload):
    client, csrf = user
    return client.post(url, json=payload, headers=csrf)


def get(user, url: str):
    client, _ = user
    return client.get(url)


def created(response) -> dict:
    assert response.status_code == 201, response.get_json()
    return response.get_json()


@pytest.fixture
def category(admin) -> dict:
    return created(post(admin, "/api/v1/categories", name="Pije"))


def add_product(admin, category: dict, sku: str, name: str) -> dict:
    return created(
        post(
            admin,
            "/api/v1/products",
            sku=sku,
            name=name,
            category_id=category["id"],
            unit_price="0.50",
        )
    )


@pytest.fixture
def product(admin, category) -> dict:
    return add_product(admin, category, "UJE-05", "Ujë 0.5L")


def move(user, product: dict, kind: str, quantity, **extra):
    return post(
        user,
        MOVEMENTS_URL,
        product_id=product["id"],
        kind=kind,
        quantity=quantity,
        **extra,
    )


def stock_of(user, product: dict) -> int:
    response = get(user, f"{STOCK_URL}?search={product['sku']}")
    assert response.status_code == 200, response.get_json()
    [row] = response.get_json()["stock"]
    return row["quantity"]


def error_code(response) -> str:
    return response.get_json()["error"]["code"]


def error_fields(response) -> list[str]:
    return [detail["field"] for detail in response.get_json()["error"]["details"]]


def test_warehouse_records_a_receipt(warehouse, product):
    movement = created(move(warehouse, product, "receipt", 10))

    assert movement["kind"] == "receipt"
    assert movement["quantity_change"] == 10
    assert movement["quantity_after"] == 10
    assert movement["reason"] is None
    assert movement["product"] == {
        "id": product["id"],
        "sku": "UJE-05",
        "name": "Ujë 0.5L",
    }
    assert movement["created_by"]["full_name"] == "Warehouse"
    assert stock_of(warehouse, product) == 10


def test_issue_is_stored_as_a_negative_change(warehouse, product):
    created(move(warehouse, product, "receipt", 10))
    movement = created(move(warehouse, product, "issue", 3))

    assert movement["quantity_change"] == -3
    assert movement["quantity_after"] == 7


def test_adjustment_keeps_its_sign_and_reason(admin, product):
    created(move(admin, product, "receipt", 10))
    movement = created(move(admin, product, "adjustment", -2, reason="  E thyer  "))

    assert movement["quantity_change"] == -2
    assert movement["quantity_after"] == 8
    assert movement["reason"] == "E thyer"


def test_issue_beyond_stock_is_a_conflict(warehouse, product):
    created(move(warehouse, product, "receipt", 2))
    response = move(warehouse, product, "issue", 3)

    assert response.status_code == 409
    assert error_code(response) == "insufficient_stock"
    assert stock_of(warehouse, product) == 2


@pytest.mark.parametrize(
    ("kind", "quantity", "extra", "field"),
    [
        ("receipt", "5", {}, "quantity"),
        ("receipt", 1.5, {}, "quantity"),
        ("receipt", True, {}, "quantity"),
        ("receipt", 1_000_001, {}, "quantity"),
        ("transfer", 5, {}, "kind"),
        ("adjustment", 5, {}, "reason"),
        ("adjustment", 5, {"reason": "   "}, "reason"),
        ("receipt", 5, {"reason": "x" * 501}, "reason"),
        ("receipt", 5, {"note": "x"}, "note"),
    ],
)
def test_invalid_movement_input_is_rejected(
    warehouse, product, kind, quantity, extra, field
):
    response = move(warehouse, product, kind, quantity, **extra)

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    assert error_fields(response) == [field]


@pytest.mark.parametrize(("kind", "quantity"), [("receipt", 0), ("issue", -1)])
def test_quantity_must_match_the_kind(warehouse, product, kind, quantity):
    response = move(warehouse, product, kind, quantity)

    assert response.status_code == 422
    assert error_code(response) == "invalid_quantity"
    assert error_fields(response) == ["quantity"]


def test_unknown_product_is_rejected(warehouse):
    response = move(warehouse, {"id": UNKNOWN_ID}, "receipt", 1)

    assert response.status_code == 422
    assert error_code(response) == "invalid_reference"
    assert error_fields(response) == ["product_id"]


def test_archived_product_is_rejected(admin, product):
    client, csrf = admin
    archived = client.patch(
        f"/api/v1/products/{product['id']}", json={"is_archived": True}, headers=csrf
    )
    assert archived.status_code == 200

    response = move(admin, product, "receipt", 1)

    assert response.status_code == 422
    assert error_code(response) == "archived_reference"


def test_sales_can_read_but_not_record_movements(sales, warehouse, product):
    created(move(warehouse, product, "receipt", 4))

    response = move(sales, product, "issue", 1)

    assert response.status_code == 403
    assert error_code(response) == "forbidden"
    assert stock_of(sales, product) == 4
    assert get(sales, MOVEMENTS_URL).get_json()["total"] == 1


def test_recording_requires_csrf_token(warehouse, product):
    client, _ = warehouse
    response = client.post(
        MOVEMENTS_URL,
        json={"product_id": product["id"], "kind": "receipt", "quantity": 1},
    )

    assert response.status_code == 403
    assert error_code(response) == "csrf_failed"


@pytest.mark.parametrize("url", [STOCK_URL, MOVEMENTS_URL])
def test_anonymous_user_gets_401(app, url):
    response = app.test_client().get(url)

    assert response.status_code == 401


def test_stock_lists_products_without_movements_as_zero(admin, category, product):
    add_product(admin, category, "LENG-1", "Lëng 1L")
    created(move(admin, product, "receipt", 6))

    response = get(admin, STOCK_URL)
    body = response.get_json()

    assert response.status_code == 200
    assert body["total"] == 2
    assert [(row["product"]["sku"], row["quantity"]) for row in body["stock"]] == [
        ("LENG-1", 0),
        ("UJE-05", 6),
    ]


def test_stock_reuses_product_filters(admin, category, product):
    add_product(admin, category, "LENG-1", "Lëng 1L")

    body = get(admin, f"{STOCK_URL}?search=leng&limit=1").get_json()

    assert body["total"] == 1
    assert body["limit"] == 1
    assert [row["product"]["sku"] for row in body["stock"]] == ["LENG-1"]


def test_movements_are_listed_newest_first(warehouse, product):
    created(move(warehouse, product, "receipt", 5))
    created(move(warehouse, product, "issue", 2))
    created(move(warehouse, product, "receipt", 1))

    body = get(warehouse, MOVEMENTS_URL).get_json()

    assert body["total"] == 3
    assert [row["quantity_after"] for row in body["movements"]] == [4, 3, 5]


def test_movements_can_be_filtered(admin, category, product):
    other = add_product(admin, category, "LENG-1", "Lëng 1L")
    created(move(admin, product, "receipt", 5))
    created(move(admin, product, "issue", 1))
    created(move(admin, other, "receipt", 2))

    by_product = get(admin, f"{MOVEMENTS_URL}?product_id={other['id']}").get_json()
    by_kind = get(admin, f"{MOVEMENTS_URL}?kind=issue").get_json()

    assert [row["product"]["sku"] for row in by_product["movements"]] == ["LENG-1"]
    assert [row["quantity_change"] for row in by_kind["movements"]] == [-1]


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("?kind=transfer", "kind"),
        ("?product_id=abc", "product_id"),
        ("?limit=0", "limit"),
        ("?offset=-1", "offset"),
        ("?sort=asc", "sort"),
    ],
)
def test_invalid_movement_filters_are_rejected(admin, query, field):
    response = get(admin, f"{MOVEMENTS_URL}{query}")

    assert response.status_code == 422
    assert error_fields(response) == [field]
