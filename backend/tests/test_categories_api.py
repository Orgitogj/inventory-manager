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
CATEGORIES_URL = "/api/v1/categories"
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
def warehouse(app, db_session) -> tuple[TestClient, dict[str, str]]:
    return logged_in(app, db_session, "ana@shop.al", UserRole.WAREHOUSE)


def create(admin, **payload):
    client, csrf = admin
    return client.post(CATEGORIES_URL, json=payload, headers=csrf)


def error_code(response) -> str:
    return response.json()["error"]["code"]


def names(response) -> list[str]:
    return [category["name"] for category in response.json()["categories"]]


def test_admin_creates_a_category(admin):
    response = create(admin, name="  Pije ", description="Freskuese")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Pije"
    assert body["description"] == "Freskuese"
    assert body["is_archived"] is False


def test_duplicate_name_is_rejected_regardless_of_case(admin):
    create(admin, name="Pije")

    response = create(admin, name="PIJE")

    assert response.status_code == 409
    assert error_code(response) == "name_taken"


def test_invalid_input_returns_field_details(admin):
    response = create(admin, name="   ")

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "name"


def test_staff_can_read_but_not_write(admin, warehouse):
    create(admin, name="Pije")
    client, csrf = warehouse

    assert client.get(CATEGORIES_URL).status_code == 200

    response = client.post(CATEGORIES_URL, json={"name": "Ushqim"}, headers=csrf)
    assert response.status_code == 403
    assert error_code(response) == "forbidden"


def test_anonymous_user_gets_401(app):
    assert TestClient(app).get(CATEGORIES_URL).status_code == 401


def test_write_without_csrf_is_rejected(admin):
    client, _ = admin

    response = client.post(CATEGORIES_URL, json={"name": "Pije"})

    assert response.status_code == 403
    assert error_code(response) == "csrf_failed"


def test_archived_categories_are_hidden_by_default(admin):
    client, csrf = admin
    pije = create(admin, name="Pije").json()
    create(admin, name="Ushqim")

    response = client.patch(
        f"{CATEGORIES_URL}/{pije['id']}", json={"is_archived": True}, headers=csrf
    )
    assert response.status_code == 200
    assert response.json()["is_archived"] is True

    assert names(client.get(CATEGORIES_URL)) == ["Ushqim"]
    assert names(client.get(f"{CATEGORIES_URL}?include_archived=true")) == [
        "Pije",
        "Ushqim",
    ]


def test_rename_to_an_existing_name_is_rejected(admin):
    client, csrf = admin
    create(admin, name="Pije")
    ushqim = create(admin, name="Ushqim").json()

    response = client.patch(
        f"{CATEGORIES_URL}/{ushqim['id']}", json={"name": "pije"}, headers=csrf
    )

    assert response.status_code == 409
    assert client.get(f"{CATEGORIES_URL}/{ushqim['id']}").json()["name"] == ("Ushqim")


def test_unknown_category_returns_404(admin):
    client, csrf = admin

    assert client.get(f"{CATEGORIES_URL}/{UNKNOWN_ID}").status_code == 404
    response = client.patch(
        f"{CATEGORIES_URL}/{UNKNOWN_ID}", json={"name": "X"}, headers=csrf
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("name", "constraint"),
    [
        (" Pije", "ck_categories_name_trimmed"),
        ("", "ck_categories_name_trimmed"),
    ],
)
def test_database_rejects_untrimmed_names(db_session, name, constraint):
    insert = text("INSERT INTO categories (id, name) VALUES (gen_random_uuid(), :name)")

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(insert, {"name": name})

    assert violated_constraint(error.value) == constraint


def test_database_rejects_case_insensitive_duplicates(db_session):
    insert = text("INSERT INTO categories (id, name) VALUES (gen_random_uuid(), :name)")
    db_session.execute(insert, {"name": "Pije"})

    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(insert, {"name": "pije"})

    assert violated_constraint(error.value) == "uq_categories_name_lower"
