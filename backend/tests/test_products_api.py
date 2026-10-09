import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.catalog.schemas import ProductListQuery
from app.catalog.service import list_products
from app.config import Settings
from app.users.models import UserRole
from app.users.schemas import StaffCreate
from app.users.service import create_user, violated_constraint

pytestmark = pytest.mark.db

PASSWORD = "long-enough-password"
PRODUCTS_URL = "/api/v1/products"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"
INSERT = text(
    "INSERT INTO products (id, sku, name, category_id, unit_price) "
    "VALUES (gen_random_uuid(), :sku, :name, :category_id, :unit_price)"
)


@pytest.fixture
def app(db_session_factory) -> Flask:
    app = create_app(Settings(app_env="testing", database_url=None, _env_file=None))
    app.extensions["database_sessionmaker"] = db_session_factory
    return app


def logged_in(app: Flask, db_session, email: str, role: UserRole):
    create_user(
        db_session,
        StaffCreate(email=email, full_name="Staff", password=PASSWORD, role=role),
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


def post(admin, url: str, **payload):
    client, csrf = admin
    return client.post(url, json=payload, headers=csrf)


def patch(admin, url: str, **payload):
    client, csrf = admin
    return client.patch(url, json=payload, headers=csrf)


def add_category(admin, name: str = "Pije") -> dict:
    response = post(admin, "/api/v1/categories", name=name)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def add_supplier(admin, name: str = "Alfa") -> dict:
    response = post(admin, "/api/v1/suppliers", name=name)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def archive(admin, kind: str, item: dict) -> None:
    response = patch(admin, f"/api/v1/{kind}/{item['id']}", is_archived=True)
    assert response.status_code == 200, response.get_json()


@pytest.fixture
def category(admin) -> dict:
    return add_category(admin)


@pytest.fixture
def supplier(admin) -> dict:
    return add_supplier(admin)


def create(admin, category: dict, **overrides):
    payload = {
        "sku": "UJE-05",
        "name": "Ujë 0.5L",
        "category_id": category["id"],
        "unit_price": "12.50",
    }
    payload.update(overrides)
    return post(admin, PRODUCTS_URL, **payload)


def add_product(admin, category: dict, **overrides) -> dict:
    response = create(admin, category, **overrides)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def product_url(product: dict) -> str:
    return f"{PRODUCTS_URL}/{product['id']}"


def error_code(response) -> str:
    return response.get_json()["error"]["code"]


def error_details(response) -> list[dict]:
    return response.get_json()["error"]["details"]


def skus(response) -> list[str]:
    assert response.status_code == 200, response.get_json()
    return [product["sku"] for product in response.get_json()["products"]]


def listed(admin, query: str = "") -> list[str]:
    client, _ = admin
    return skus(client.get(f"{PRODUCTS_URL}{query}"))


def test_admin_creates_a_product(admin, category, supplier):
    response = create(
        admin,
        category,
        sku="  uje-05 ",
        name="  Ujë 0.5L ",
        description="  Shishe  ",
        supplier_id=supplier["id"],
        unit_price=12.5,
    )

    assert response.status_code == 201
    body = response.get_json()
    assert set(body) == {
        "id",
        "sku",
        "name",
        "description",
        "unit_price",
        "is_archived",
        "created_at",
        "updated_at",
        "category",
        "supplier",
    }
    assert body["sku"] == "UJE-05"
    assert body["name"] == "Ujë 0.5L"
    assert body["description"] == "Shishe"
    assert body["unit_price"] == "12.50"
    assert body["is_archived"] is False
    assert body["category"] == {"id": category["id"], "name": "Pije"}
    assert body["supplier"] == {"id": supplier["id"], "name": "Alfa"}
    assert body["created_at"] == body["updated_at"]


def test_supplier_is_optional_and_whole_prices_get_two_decimals(admin, category):
    body = add_product(admin, category, unit_price="7")

    assert body["supplier"] is None
    assert body["description"] is None
    assert body["unit_price"] == "7.00"


def test_two_products_can_share_a_name(admin, category):
    add_product(admin, category, sku="A-1", name="Ujë")
    add_product(admin, category, sku="A-2", name="Ujë")

    assert listed(admin) == ["A-1", "A-2"]


def test_duplicate_sku_is_rejected_regardless_of_case(admin, category):
    add_product(admin, category, sku="UJE-05")

    response = create(admin, category, sku=" uje-05 ", name="Tjetër")

    assert response.status_code == 409
    assert error_code(response) == "sku_taken"
    assert listed(admin) == ["UJE-05"]


@pytest.mark.parametrize("field", ["category_id", "supplier_id"])
def test_unknown_reference_is_rejected(admin, category, field):
    response = create(admin, category, **{field: UNKNOWN_ID})

    assert response.status_code == 422
    assert error_code(response) == "invalid_reference"
    assert [detail["field"] for detail in error_details(response)] == [field]
    assert listed(admin) == []


def test_archived_category_is_rejected(admin, category):
    archive(admin, "categories", category)

    response = create(admin, category)

    assert response.status_code == 422
    assert error_code(response) == "archived_reference"
    assert [detail["field"] for detail in error_details(response)] == ["category_id"]


def test_archived_supplier_is_rejected(admin, category, supplier):
    archive(admin, "suppliers", supplier)

    response = create(admin, category, supplier_id=supplier["id"])

    assert response.status_code == 422
    assert error_code(response) == "archived_reference"
    assert [detail["field"] for detail in error_details(response)] == ["supplier_id"]
    assert listed(admin) == []


def test_invalid_input_returns_field_details_without_the_input(admin, category):
    response = create(admin, category, sku="bad sku!", unit_price="1.999", name=" ")

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    details = error_details(response)
    assert {detail["field"] for detail in details} == {"sku", "name", "unit_price"}
    assert all(set(detail) == {"field", "message"} for detail in details)
    assert "bad sku!" not in response.get_data(as_text=True)
    assert "1.999" not in response.get_data(as_text=True)


@pytest.mark.parametrize("role", [UserRole.WAREHOUSE, UserRole.SALES])
def test_staff_can_read_but_not_write(app, db_session, admin, category, role):
    product = add_product(admin, category)
    staff = logged_in(app, db_session, "staff@shop.al", role)
    client, _ = staff

    assert skus(client.get(PRODUCTS_URL)) == ["UJE-05"]
    assert client.get(product_url(product)).get_json()["sku"] == "UJE-05"

    created = create(staff, category, sku="NEW-1")
    assert created.status_code == 403
    assert error_code(created) == "forbidden"

    updated = patch(staff, product_url(product), unit_price="1.00")
    assert updated.status_code == 403
    assert error_code(updated) == "forbidden"

    assert client.get(product_url(product)).get_json()["unit_price"] == "12.50"
    assert listed(admin) == ["UJE-05"]


def test_anonymous_user_gets_401(app):
    client = app.test_client()

    assert client.get(PRODUCTS_URL).status_code == 401
    assert client.get(f"{PRODUCTS_URL}/{UNKNOWN_ID}").status_code == 401
    assert client.post(PRODUCTS_URL, json={"sku": "A-1"}).status_code == 401
    assert client.patch(f"{PRODUCTS_URL}/{UNKNOWN_ID}", json={}).status_code == 401


def test_write_without_csrf_is_rejected(admin, category):
    client, _ = admin
    product = add_product(admin, category)

    created = client.post(
        PRODUCTS_URL,
        json={
            "sku": "A-2",
            "name": "X",
            "category_id": category["id"],
            "unit_price": "1",
        },
    )
    updated = client.patch(product_url(product), json={"unit_price": "1.00"})

    assert created.status_code == 403
    assert error_code(created) == "csrf_failed"
    assert updated.status_code == 403
    assert error_code(updated) == "csrf_failed"
    assert listed(admin) == ["UJE-05"]


def test_list_is_sorted_by_name_ignoring_case_then_by_sku(admin, category):
    add_product(admin, category, sku="Z-1", name="alfa")
    add_product(admin, category, sku="B-2", name="Beta")
    add_product(admin, category, sku="B-1", name="beta")
    add_product(admin, category, sku="A-9", name="Gama")

    assert listed(admin) == ["Z-1", "B-1", "B-2", "A-9"]


def test_list_reports_total_limit_and_offset(admin, category):
    client, _ = admin
    add_product(admin, category)

    body = client.get(PRODUCTS_URL).get_json()

    assert set(body) == {"products", "total", "limit", "offset"}
    assert body["total"] == 1
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert body["products"][0]["category"] == {"id": category["id"], "name": "Pije"}


def test_filter_by_category_and_supplier(admin, category, supplier):
    food = add_category(admin, "Ushqim")
    beta = add_supplier(admin, "Beta")
    add_product(admin, category, sku="P-1", supplier_id=supplier["id"])
    add_product(admin, category, sku="P-2", supplier_id=beta["id"])
    add_product(admin, food, sku="U-1", supplier_id=supplier["id"])
    add_product(admin, food, sku="U-2")

    assert listed(admin, f"?category_id={category['id']}") == ["P-1", "P-2"]
    assert listed(admin, f"?supplier_id={supplier['id']}") == ["P-1", "U-1"]
    assert listed(admin, f"?category_id={food['id']}&supplier_id={supplier['id']}") == [
        "U-1"
    ]
    assert listed(admin, f"?category_id={UNKNOWN_ID}") == []


def test_search_matches_name_or_sku_ignoring_case(admin, category):
    add_product(admin, category, sku="UJE-05", name="Ujë 0.5L")
    add_product(admin, category, sku="LNG-1", name="Lëng molle")
    add_product(admin, category, sku="MOLLE-KG", name="Fruta")

    assert listed(admin, "?search=MOLLE") == ["MOLLE-KG", "LNG-1"]
    assert listed(admin, "?search=uje") == ["UJE-05"]
    assert listed(admin, "?search=%20lëng%20") == ["LNG-1"]
    assert listed(admin, "?search=nuk-ekziston") == []
    assert listed(admin, "?search=") == ["MOLLE-KG", "LNG-1", "UJE-05"]


def test_search_treats_wildcards_as_plain_text(admin, category):
    client, _ = admin
    add_product(admin, category, sku="A-1", name="Zbritje 50% sot")
    add_product(admin, category, sku="A-2", name="Zbritje 50 lekë")
    add_product(admin, category, sku="B_1", name="Kod me nënvizë")
    add_product(admin, category, sku="BX1", name="Kod pa nënvizë")
    add_product(admin, category, sku="C-1", name="Shteg C:\\temp")

    assert listed(admin, "?search=50%25") == ["A-1"]
    assert listed(admin, "?search=%25") == ["A-1"]
    assert listed(admin, "?search=B_1") == ["B_1"]
    assert listed(admin, "?search=_") == ["B_1"]
    assert listed(admin, "?search=%5C") == ["C-1"]
    assert client.get(f"{PRODUCTS_URL}?search=%25").get_json()["total"] == 1


def test_archived_products_are_hidden_by_default(admin, category):
    client, _ = admin
    old = add_product(admin, category, sku="OLD-1", name="I vjetër")
    add_product(admin, category, sku="NEW-1", name="I ri")

    response = patch(admin, product_url(old), is_archived=True)
    assert response.status_code == 200
    assert response.get_json()["is_archived"] is True

    assert listed(admin) == ["NEW-1"]
    assert client.get(PRODUCTS_URL).get_json()["total"] == 1
    assert listed(admin, "?include_archived=true") == ["NEW-1", "OLD-1"]
    assert listed(admin, "?include_archived=true&search=old") == ["OLD-1"]
    assert client.get(product_url(old)).status_code == 200


def test_pagination_returns_every_product_exactly_once(admin, category):
    client, _ = admin
    expected = [f"P-{number}" for number in range(1, 6)]
    for sku in expected:
        add_product(admin, category, sku=sku, name=f"Produkt {sku}")

    pages = [
        client.get(f"{PRODUCTS_URL}?limit=2&offset={offset}").get_json()
        for offset in (0, 2, 4, 6)
    ]

    assert [page["total"] for page in pages] == [5, 5, 5, 5]
    assert [page["limit"] for page in pages] == [2, 2, 2, 2]
    assert [page["offset"] for page in pages] == [0, 2, 4, 6]
    assert [len(page["products"]) for page in pages] == [2, 2, 1, 0]
    assert [
        product["sku"] for page in pages for product in page["products"]
    ] == expected


def test_total_counts_only_the_filtered_products(admin, category):
    client, _ = admin
    food = add_category(admin, "Ushqim")
    for number in range(3):
        add_product(admin, category, sku=f"P-{number}")
    add_product(admin, food, sku="U-1")

    body = client.get(
        f"{PRODUCTS_URL}?category_id={category['id']}&limit=1&offset=1"
    ).get_json()

    assert body["total"] == 3
    assert [product["sku"] for product in body["products"]] == ["P-1"]


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("?limit=0", "limit"),
        ("?limit=201", "limit"),
        ("?limit=abc", "limit"),
        ("?offset=-1", "offset"),
        ("?category_id=abc", "category_id"),
        ("?supplier_id=abc", "supplier_id"),
        ("?include_archived=maybe", "include_archived"),
        ("?sort=name", "sort"),
    ],
)
def test_invalid_query_params_are_rejected(admin, query, field):
    client, _ = admin

    response = client.get(f"{PRODUCTS_URL}{query}")

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    assert [detail["field"] for detail in error_details(response)] == [field]


def test_list_does_not_run_a_query_per_product(admin, category, supplier, db_session):
    for number in range(5):
        add_product(admin, category, sku=f"P-{number}", supplier_id=supplier["id"])

    db_session.expire_all()
    statements: list[str] = []

    def record(_conn, _cursor, statement, *_rest):
        statements.append(statement)

    connection = db_session.connection()
    event.listen(connection, "before_cursor_execute", record)

    try:
        products, total = list_products(db_session, ProductListQuery())
        names = [(product.category.name, product.supplier.name) for product in products]
    finally:
        event.remove(connection, "before_cursor_execute", record)

    assert total == 5
    assert names == [("Pije", "Alfa")] * 5
    assert len([s for s in statements if s.lstrip().startswith("SELECT")]) == 2


def test_update_changes_fields_and_normalizes_them(admin, category, supplier):
    client, _ = admin
    food = add_category(admin, "Ushqim")
    product = add_product(admin, category)

    response = patch(
        admin,
        product_url(product),
        sku=" uje-15 ",
        name="  Ujë 1.5L ",
        description="  Shishe e madhe ",
        category_id=food["id"],
        supplier_id=supplier["id"],
        unit_price=30,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["sku"] == "UJE-15"
    assert body["name"] == "Ujë 1.5L"
    assert body["description"] == "Shishe e madhe"
    assert body["unit_price"] == "30.00"
    assert body["category"] == {"id": food["id"], "name": "Ushqim"}
    assert body["supplier"] == {"id": supplier["id"], "name": "Alfa"}
    assert client.get(product_url(product)).get_json() == body


def test_null_removes_the_supplier_and_keeps_the_rest(admin, category, supplier):
    client, _ = admin
    product = add_product(
        admin, category, supplier_id=supplier["id"], description="Shishe"
    )

    response = patch(admin, product_url(product), supplier_id=None)

    assert response.status_code == 200
    stored = client.get(product_url(product)).get_json()
    assert stored["supplier"] is None
    assert stored["description"] == "Shishe"
    assert stored["category"]["id"] == category["id"]
    assert stored["unit_price"] == "12.50"


def test_price_change_updates_updated_at_but_not_created_at(
    admin, category, db_session
):
    client, _ = admin
    product = add_product(admin, category)
    db_session.execute(
        text(
            "UPDATE products SET created_at = '2020-01-01T00:00:00Z', "
            "updated_at = '2020-01-01T00:00:00Z'"
        )
    )
    db_session.commit()
    before = client.get(product_url(product)).get_json()
    assert before["updated_at"].startswith("2020-01-01")

    response = patch(admin, product_url(product), unit_price="13.00")

    assert response.status_code == 200
    after = client.get(product_url(product)).get_json()
    assert after["unit_price"] == "13.00"
    assert after["created_at"] == before["created_at"]
    assert after["updated_at"] > before["updated_at"]
    assert not after["updated_at"].startswith("2020")


def test_rename_to_an_existing_sku_is_rejected(admin, category):
    client, _ = admin
    add_product(admin, category, sku="A-1")
    second = add_product(admin, category, sku="A-2")

    response = patch(admin, product_url(second), sku="a-1", name="Ndryshuar")

    assert response.status_code == 409
    assert error_code(response) == "sku_taken"
    stored = client.get(product_url(second)).get_json()
    assert stored["sku"] == "A-2"
    assert stored["name"] == "Ujë 0.5L"


@pytest.mark.parametrize(
    ("kind", "field"), [("categories", "category_id"), ("suppliers", "supplier_id")]
)
def test_update_rejects_unknown_and_archived_references(
    admin, category, supplier, kind, field
):
    client, _ = admin
    product = add_product(admin, category, supplier_id=supplier["id"])
    other = (
        add_category(admin, "Ushqim")
        if kind == "categories"
        else add_supplier(admin, "Beta")
    )
    archive(admin, kind, other)

    archived = patch(admin, product_url(product), **{field: other["id"]})
    unknown = patch(admin, product_url(product), **{field: UNKNOWN_ID})

    assert archived.status_code == 422
    assert error_code(archived) == "archived_reference"
    assert [detail["field"] for detail in error_details(archived)] == [field]
    assert unknown.status_code == 422
    assert error_code(unknown) == "invalid_reference"
    assert [detail["field"] for detail in error_details(unknown)] == [field]

    stored = client.get(product_url(product)).get_json()
    assert stored["category"]["id"] == category["id"]
    assert stored["supplier"]["id"] == supplier["id"]


def test_product_with_archived_references_can_still_be_edited(
    admin, category, supplier
):
    product = add_product(admin, category, supplier_id=supplier["id"])
    archive(admin, "categories", category)
    archive(admin, "suppliers", supplier)

    renamed = patch(admin, product_url(product), name="Emër i ri", unit_price="9.99")
    unchanged_references = patch(
        admin,
        product_url(product),
        category_id=category["id"],
        supplier_id=supplier["id"],
        description="Përshkrim",
    )

    assert renamed.status_code == 200
    assert renamed.get_json()["name"] == "Emër i ri"
    assert renamed.get_json()["unit_price"] == "9.99"
    assert unchanged_references.status_code == 200
    assert unchanged_references.get_json()["description"] == "Përshkrim"
    assert unchanged_references.get_json()["category"]["id"] == category["id"]


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({}, "body"),
        ({"sku": None}, "sku"),
        ({"name": None}, "name"),
        ({"category_id": None}, "category_id"),
        ({"unit_price": None}, "unit_price"),
        ({"unit_price": -1}, "unit_price"),
        ({"is_archived": "yes"}, "is_archived"),
        ({"stock": 5}, "stock"),
    ],
)
def test_invalid_update_is_rejected(admin, category, payload, field):
    client, _ = admin
    product = add_product(admin, category)

    response = patch(admin, product_url(product), **payload)

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    assert [detail["field"] for detail in error_details(response)] == [field]
    assert client.get(product_url(product)).get_json() == product


def test_unknown_product_returns_404(admin):
    client, _ = admin

    found = client.get(f"{PRODUCTS_URL}/{UNKNOWN_ID}")
    updated = patch(admin, f"{PRODUCTS_URL}/{UNKNOWN_ID}", name="X")

    assert found.status_code == 404
    assert error_code(found) == "not_found"
    assert found.get_json()["error"]["message"] == "Product not found."
    assert updated.status_code == 404
    assert error_code(updated) == "not_found"


def test_delete_is_not_supported(admin, category):
    client, csrf = admin
    product = add_product(admin, category)

    assert client.delete(product_url(product), headers=csrf).status_code == 405
    assert listed(admin) == ["UJE-05"]


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"unit_price": "-0.01"}, "ck_products_unit_price_non_negative"),
        ({"sku": "uje-05"}, "ck_products_sku_format"),
        ({"sku": "UJE 05"}, "ck_products_sku_format"),
        ({"sku": ""}, "ck_products_sku_format"),
        ({"name": " Ujë"}, "ck_products_name_trimmed"),
        ({"name": ""}, "ck_products_name_trimmed"),
        ({"category_id": UNKNOWN_ID}, "fk_products_category_id_categories"),
    ],
)
def test_database_rejects_invalid_rows(admin, category, db_session, values, constraint):
    row = {
        "sku": "UJE-05",
        "name": "Ujë",
        "category_id": category["id"],
        "unit_price": "12.50",
    }
    row.update(values)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(INSERT, row)

    assert violated_constraint(error.value) == constraint


def test_database_rejects_duplicate_sku(admin, category, db_session):
    row = {
        "sku": "UJE-05",
        "name": "Ujë",
        "category_id": category["id"],
        "unit_price": "1",
    }
    db_session.execute(INSERT, row)

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(INSERT, row)

    assert violated_constraint(error.value) == "uq_products_sku"


@pytest.mark.parametrize(
    ("table", "constraint"),
    [
        ("categories", "fk_products_category_id_categories"),
        ("suppliers", "fk_products_supplier_id_suppliers"),
    ],
)
def test_database_restricts_deleting_referenced_rows(
    admin, category, supplier, db_session, table, constraint
):
    add_product(admin, category, supplier_id=supplier["id"])
    referenced = category if table == "categories" else supplier

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(
            text(f"DELETE FROM {table} WHERE id = :id"), {"id": referenced["id"]}
        )

    assert violated_constraint(error.value) == constraint
    assert listed(admin) == ["UJE-05"]
