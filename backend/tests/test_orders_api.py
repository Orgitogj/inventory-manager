import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import create_app
from app.config import Settings
from app.users.models import UserRole
from app.users.schemas import StaffCreate
from app.users.service import create_user

pytestmark = pytest.mark.db

PASSWORD = "long-enough-password"
ORDERS_URL = "/api/v1/orders"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


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


def post(user, url: str, **payload):
    client, csrf = user
    return client.post(url, json=payload, headers=csrf)


def patch(user, url: str, **payload):
    client, csrf = user
    return client.patch(url, json=payload, headers=csrf)


def put(user, url: str, **payload):
    client, csrf = user
    return client.put(url, json=payload, headers=csrf)


def created(response) -> dict:
    assert response.status_code == 201, response.json()
    return response.json()


def error_code(response) -> str:
    return response.json()["error"]["code"]


def error_fields(response) -> list[str]:
    return [detail["field"] for detail in response.json()["error"]["details"]]


def order_url(order: dict) -> str:
    return f"{ORDERS_URL}/{order['id']}"


@pytest.fixture
def category(admin) -> dict:
    return created(post(admin, "/api/v1/categories", name="Pije"))


def add_product(admin, category: dict, sku: str, price: str, stock: int) -> dict:
    product = created(
        post(
            admin,
            "/api/v1/products",
            sku=sku,
            name=sku,
            category_id=category["id"],
            unit_price=price,
        )
    )
    created(
        post(
            admin,
            "/api/v1/inventory/movements",
            product_id=product["id"],
            kind="receipt",
            quantity=stock,
        )
    )
    return product


@pytest.fixture
def water(admin, category) -> dict:
    return add_product(admin, category, "UJE-05", "0.50", 10)


@pytest.fixture
def juice(admin, category) -> dict:
    return add_product(admin, category, "LENG-1", "1.20", 5)


@pytest.fixture
def customer(admin) -> dict:
    return created(post(admin, "/api/v1/customers", name="Market Ana"))


def create_order(user, customer: dict, *pairs, **extra):
    return post(
        user,
        ORDERS_URL,
        customer_id=customer["id"],
        items=[
            {"product_id": product["id"], "quantity": quantity}
            for product, quantity in pairs
        ],
        **extra,
    )


def stock_of(user, product: dict) -> int:
    client, _ = user
    response = client.get(f"/api/v1/inventory/stock?search={product['sku']}")
    assert response.status_code == 200, response.json()
    [row] = response.json()["stock"]
    return row["quantity"]


def test_sales_creates_a_draft_with_line_and_order_totals(
    sales, customer, water, juice
):
    response = create_order(sales, customer, (water, 3), (juice, 2), notes=" Shpejt ")
    body = response.json()

    assert response.status_code == 201
    assert body["status"] == "draft"
    assert body["number"] > 0
    assert body["notes"] == "Shpejt"
    assert body["customer"] == {"id": customer["id"], "name": "Market Ana"}
    assert body["created_by"]["full_name"] == "Staff"
    assert [
        (
            item["product"]["sku"],
            item["quantity"],
            item["unit_price"],
            item["line_total"],
        )
        for item in body["items"]
    ] == [("UJE-05", 3, "0.50", "1.50"), ("LENG-1", 2, "1.20", "2.40")]
    assert body["total_amount"] == "3.90"
    assert body["confirmed_at"] is None
    assert stock_of(sales, water) == 10


def test_invalid_order_input_is_rejected(sales, customer, water):
    duplicate = create_order(sales, customer, (water, 1), (water, 2))
    zero = create_order(sales, customer, (water, 0))
    missing_customer = post(sales, ORDERS_URL, items=[])

    for response, field in [
        (duplicate, "items"),
        (zero, "items.0.quantity"),
        (missing_customer, "customer_id"),
    ]:
        assert response.status_code == 422
        assert error_code(response) == "validation_error"
        assert error_fields(response) == [field]


def test_unknown_product_and_archived_customer_are_rejected(
    admin, sales, customer, water
):
    unknown = post(
        sales,
        ORDERS_URL,
        customer_id=customer["id"],
        items=[
            {"product_id": water["id"], "quantity": 1},
            {"product_id": UNKNOWN_ID, "quantity": 1},
        ],
    )

    assert unknown.status_code == 422
    assert error_code(unknown) == "invalid_reference"
    assert error_fields(unknown) == ["items.1.product_id"]

    archived = patch(admin, f"/api/v1/customers/{customer['id']}", is_archived=True)
    assert archived.status_code == 200

    response = create_order(sales, customer, (water, 1))

    assert response.status_code == 422
    assert error_code(response) == "archived_reference"
    assert error_fields(response) == ["customer_id"]


def test_warehouse_can_read_orders_but_not_change_them(
    sales, warehouse, customer, water
):
    order = created(create_order(sales, customer, (water, 1)))
    client, _ = warehouse

    assert client.get(ORDERS_URL).json()["total"] == 1
    assert client.get(order_url(order)).status_code == 200
    assert create_order(warehouse, customer, (water, 1)).status_code == 403
    assert post(warehouse, f"{order_url(order)}/confirm").status_code == 403
    assert patch(warehouse, order_url(order), notes="x").status_code == 403


def test_anonymous_user_gets_401(app):
    assert TestClient(app).get(ORDERS_URL).status_code == 401


def test_confirm_requires_csrf_token(sales, customer, water):
    order = created(create_order(sales, customer, (water, 1)))
    client, _ = sales

    response = client.post(f"{order_url(order)}/confirm")

    assert response.status_code == 403
    assert error_code(response) == "csrf_failed"


def test_confirm_issues_the_stock(sales, customer, water, juice):
    order = created(create_order(sales, customer, (water, 3), (juice, 5)))

    response = post(sales, f"{order_url(order)}/confirm")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "confirmed"
    assert body["confirmed_at"] is not None
    assert stock_of(sales, water) == 7
    assert stock_of(sales, juice) == 0


def test_confirm_without_enough_stock_changes_nothing(sales, customer, water, juice):
    order = created(create_order(sales, customer, (water, 3), (juice, 6)))

    response = post(sales, f"{order_url(order)}/confirm")

    assert response.status_code == 409
    assert error_code(response) == "insufficient_stock"
    assert error_fields(response) == ["items.1.quantity"]
    assert "LENG-1" in response.json()["error"]["message"]
    assert stock_of(sales, water) == 10
    assert stock_of(sales, juice) == 5

    client, _ = sales
    assert client.get(order_url(order)).json()["status"] == "draft"


def test_empty_order_cannot_be_confirmed(sales, customer):
    order = created(post(sales, ORDERS_URL, customer_id=customer["id"]))

    response = post(sales, f"{order_url(order)}/confirm")

    assert order["total_amount"] == "0.00"
    assert response.status_code == 409
    assert error_code(response) == "empty_order"


def test_draft_can_be_edited(sales, customer, water, juice):
    other = created(post(sales, "/api/v1/customers", name="Bar Drini"))
    order = created(create_order(sales, customer, (water, 3)))

    updated = patch(sales, order_url(order), customer_id=other["id"], notes="Telefon")
    replaced = put(
        sales,
        f"{order_url(order)}/items",
        items=[{"product_id": juice["id"], "quantity": 2}],
    )
    body = replaced.json()

    assert updated.status_code == 200
    assert updated.json()["customer"]["name"] == "Bar Drini"
    assert updated.json()["notes"] == "Telefon"
    assert replaced.status_code == 200
    assert [(item["product"]["sku"], item["quantity"]) for item in body["items"]] == [
        ("LENG-1", 2)
    ]
    assert body["total_amount"] == "2.40"


def test_confirmed_order_cannot_be_edited(sales, customer, water):
    order = created(create_order(sales, customer, (water, 1)))
    assert post(sales, f"{order_url(order)}/confirm").status_code == 200

    for response in (
        patch(sales, order_url(order), notes="x"),
        put(sales, f"{order_url(order)}/items", items=[]),
        post(sales, f"{order_url(order)}/confirm"),
    ):
        assert response.status_code == 409
        assert error_code(response) == "invalid_order_status"

    assert stock_of(sales, water) == 9


def test_cancelling_a_confirmed_order_returns_the_stock(sales, customer, water):
    order = created(create_order(sales, customer, (water, 4)))
    assert post(sales, f"{order_url(order)}/confirm").status_code == 200
    assert stock_of(sales, water) == 6

    response = post(sales, f"{order_url(order)}/cancel")
    again = post(sales, f"{order_url(order)}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancelled_at"] is not None
    assert stock_of(sales, water) == 10
    assert again.status_code == 409
    assert error_code(again) == "invalid_order_status"


def test_orders_are_listed_newest_first_and_can_be_filtered(sales, customer, water):
    other = created(post(sales, "/api/v1/customers", name="Bar Drini"))
    first = created(create_order(sales, customer, (water, 1)))
    second = created(create_order(sales, other, (water, 1)))
    assert post(sales, f"{order_url(first)}/confirm").status_code == 200

    client, _ = sales
    everything = client.get(ORDERS_URL).json()
    confirmed = client.get(f"{ORDERS_URL}?status=confirmed").json()
    by_customer = client.get(f"{ORDERS_URL}?customer_id={other['id']}").json()

    assert everything["total"] == 2
    assert [order["id"] for order in everything["orders"]] == [
        second["id"],
        first["id"],
    ]
    assert [order["id"] for order in confirmed["orders"]] == [first["id"]]
    assert [order["id"] for order in by_customer["orders"]] == [second["id"]]


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("?status=shipped", "status"),
        ("?customer_id=abc", "customer_id"),
        ("?limit=0", "limit"),
        ("?sort=number", "sort"),
    ],
)
def test_invalid_query_params_are_rejected(sales, query, field):
    client, _ = sales

    response = client.get(f"{ORDERS_URL}{query}")

    assert response.status_code == 422
    assert error_fields(response) == [field]


def test_unknown_order_returns_404(sales):
    client, _ = sales
    url = f"{ORDERS_URL}/{UNKNOWN_ID}"

    assert client.get(url).status_code == 404
    assert post(sales, f"{url}/confirm").status_code == 404
    assert post(sales, f"{url}/cancel").status_code == 404
    assert patch(sales, url, notes="x").status_code == 404
