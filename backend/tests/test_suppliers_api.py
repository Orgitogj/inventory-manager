import pytest
from flask import Flask
from flask.testing import FlaskClient
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
SUPPLIERS_URL = "/api/v1/suppliers"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"
INSERT = text(
    "INSERT INTO suppliers (id, name, email) VALUES (gen_random_uuid(), :name, :email)"
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


@pytest.fixture
def warehouse(app, db_session) -> tuple[FlaskClient, dict[str, str]]:
    return logged_in(app, db_session, "ana@shop.al", UserRole.WAREHOUSE)


def create(admin, **payload):
    client, csrf = admin
    return client.post(SUPPLIERS_URL, json=payload, headers=csrf)


def patch(admin, supplier_id: str, **payload):
    client, csrf = admin
    return client.patch(f"{SUPPLIERS_URL}/{supplier_id}", json=payload, headers=csrf)


def error_code(response) -> str:
    return response.get_json()["error"]["code"]


def names(response) -> list[str]:
    return [supplier["name"] for supplier in response.get_json()["suppliers"]]


def test_admin_creates_a_supplier_with_cleaned_values(admin):
    response = create(
        admin,
        name="  Alfa Sh.p.k. ",
        email="  Info@Alfa.AL ",
        phone=" +355 69 123 4567 ",
        notes="   ",
    )

    assert response.status_code == 201
    body = response.get_json()
    assert set(body) == {
        "id",
        "name",
        "email",
        "phone",
        "notes",
        "is_archived",
        "created_at",
    }
    assert body["name"] == "Alfa Sh.p.k."
    assert body["email"] == "info@alfa.al"
    assert body["phone"] == "+355 69 123 4567"
    assert body["notes"] is None
    assert body["is_archived"] is False


def test_two_suppliers_can_share_an_email(admin):
    assert create(admin, name="Alfa", email="info@alfa.al").status_code == 201
    assert create(admin, name="Beta", email="INFO@alfa.al").status_code == 201


def test_duplicate_name_is_rejected_regardless_of_case(admin):
    create(admin, name="Alfa")

    response = create(admin, name="  ALFA ")

    assert response.status_code == 409
    assert error_code(response) == "name_taken"


def test_invalid_input_returns_field_details_without_the_input(admin):
    response = create(admin, name="   ", email="not-an-email")

    assert response.status_code == 422
    assert error_code(response) == "validation_error"
    details = response.get_json()["error"]["details"]
    assert {detail["field"] for detail in details} == {"name", "email"}
    assert all(set(detail) == {"field", "message"} for detail in details)
    assert "not-an-email" not in response.get_data(as_text=True)


def test_staff_can_read_but_not_write(admin, warehouse):
    alfa = create(admin, name="Alfa").get_json()
    client, csrf = warehouse

    assert names(client.get(SUPPLIERS_URL)) == ["Alfa"]
    assert client.get(f"{SUPPLIERS_URL}/{alfa['id']}").get_json()["name"] == "Alfa"

    created = client.post(SUPPLIERS_URL, json={"name": "Beta"}, headers=csrf)
    assert created.status_code == 403
    assert error_code(created) == "forbidden"

    updated = patch(warehouse, alfa["id"], name="Gama")
    assert updated.status_code == 403
    assert error_code(updated) == "forbidden"
    assert names(client.get(SUPPLIERS_URL)) == ["Alfa"]


def test_anonymous_user_gets_401(app):
    client = app.test_client()

    assert client.get(SUPPLIERS_URL).status_code == 401
    assert client.get(f"{SUPPLIERS_URL}/{UNKNOWN_ID}").status_code == 401
    assert client.post(SUPPLIERS_URL, json={"name": "Alfa"}).status_code == 401


def test_write_without_csrf_is_rejected(admin):
    client, _ = admin

    response = client.post(SUPPLIERS_URL, json={"name": "Alfa"})

    assert response.status_code == 403
    assert error_code(response) == "csrf_failed"
    assert names(client.get(SUPPLIERS_URL)) == []


def test_list_is_sorted_by_name_ignoring_case(admin):
    client, _ = admin
    for name in ["beta", "Alfa", "Gama"]:
        create(admin, name=name)

    assert names(client.get(SUPPLIERS_URL)) == ["Alfa", "beta", "Gama"]


def test_archived_suppliers_are_hidden_by_default(admin):
    client, _ = admin
    alfa = create(admin, name="Alfa").get_json()
    create(admin, name="Beta")

    response = patch(admin, alfa["id"], is_archived=True)
    assert response.status_code == 200
    assert response.get_json()["is_archived"] is True

    assert names(client.get(SUPPLIERS_URL)) == ["Beta"]
    assert names(client.get(f"{SUPPLIERS_URL}?include_archived=true")) == [
        "Alfa",
        "Beta",
    ]
    assert client.get(f"{SUPPLIERS_URL}/{alfa['id']}").status_code == 200


def test_rename_to_an_existing_name_is_rejected(admin):
    client, _ = admin
    create(admin, name="Alfa")
    beta = create(admin, name="Beta").get_json()

    response = patch(admin, beta["id"], name="alfa")

    assert response.status_code == 409
    assert error_code(response) == "name_taken"
    assert client.get(f"{SUPPLIERS_URL}/{beta['id']}").get_json()["name"] == "Beta"


def test_supplier_can_be_renamed_to_a_different_case_of_its_own_name(admin):
    alfa = create(admin, name="alfa").get_json()

    response = patch(admin, alfa["id"], name="ALFA")

    assert response.status_code == 200
    assert response.get_json()["name"] == "ALFA"


def test_unknown_supplier_returns_404(admin):
    client, _ = admin

    found = client.get(f"{SUPPLIERS_URL}/{UNKNOWN_ID}")
    assert found.status_code == 404
    assert error_code(found) == "not_found"
    assert found.get_json()["error"]["message"] == "Supplier not found."

    assert patch(admin, UNKNOWN_ID, name="X").status_code == 404


def test_null_clears_optional_fields_and_keeps_the_rest(admin):
    client, _ = admin
    alfa = create(
        admin, name="Alfa", email="info@alfa.al", phone="069", notes="Shënim"
    ).get_json()

    response = patch(admin, alfa["id"], email=None)

    assert response.status_code == 200
    stored = client.get(f"{SUPPLIERS_URL}/{alfa['id']}").get_json()
    assert stored["email"] is None
    assert stored["phone"] == "069"
    assert stored["notes"] == "Shënim"
    assert stored["name"] == "Alfa"


def test_update_normalizes_the_email(admin):
    alfa = create(admin, name="Alfa").get_json()

    response = patch(admin, alfa["id"], email="  Sales@Alfa.AL ")

    assert response.status_code == 200
    assert response.get_json()["email"] == "sales@alfa.al"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({}, "body"),
        ({"name": None}, "name"),
        ({"is_archived": None}, "is_archived"),
        ({"is_archived": "yes"}, "is_archived"),
        ({"email": "not-an-email"}, "email"),
        ({"created_at": "2026-01-01T00:00:00Z"}, "created_at"),
    ],
)
def test_invalid_update_is_rejected(admin, payload, field):
    alfa = create(admin, name="Alfa", email="info@alfa.al").get_json()

    response = patch(admin, alfa["id"], **payload)

    assert response.status_code == 422
    details = response.get_json()["error"]["details"]
    assert [detail["field"] for detail in details] == [field]


@pytest.mark.parametrize(
    ("name", "email", "constraint"),
    [
        (" Alfa", None, "ck_suppliers_name_trimmed"),
        ("Alfa ", None, "ck_suppliers_name_trimmed"),
        ("", None, "ck_suppliers_name_trimmed"),
        ("Alfa", "Info@Alfa.AL", "ck_suppliers_email_normalized"),
        ("Alfa", " info@alfa.al", "ck_suppliers_email_normalized"),
    ],
)
def test_database_rejects_unnormalized_values(db_session, name, email, constraint):
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(INSERT, {"name": name, "email": email})

    assert violated_constraint(error.value) == constraint


def test_database_rejects_case_insensitive_duplicate_names(db_session):
    db_session.execute(INSERT, {"name": "Alfa", "email": None})

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(INSERT, {"name": "alfa", "email": None})

    assert violated_constraint(error.value) == "uq_suppliers_name_lower"


def test_database_allows_missing_and_shared_emails(db_session):
    db_session.execute(INSERT, {"name": "Alfa", "email": None})
    db_session.execute(INSERT, {"name": "Beta", "email": "info@alfa.al"})
    db_session.execute(INSERT, {"name": "Gama", "email": "info@alfa.al"})

    assert db_session.scalar(text("SELECT count(*) FROM suppliers")) == 3
