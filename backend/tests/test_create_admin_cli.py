import pytest
from flask import Flask
from sqlalchemy import select

from app import create_app
from app.auth.passwords import verify_password
from app.config import Settings
from app.users.models import User, UserRole

PASSWORD = "long-enough-password"
ARGS = ["create-admin", "--email", " Boss@Shop.AL ", "--full-name", "Boss"]


def make_app() -> Flask:
    return create_app(Settings(app_env="testing", database_url=None, _env_file=None))


@pytest.fixture
def cli_app(db_session_factory) -> Flask:
    app = make_app()
    app.extensions["database_sessionmaker"] = db_session_factory
    return app


def run(app: Flask, password: str = PASSWORD, confirmation: str | None = None):
    confirmation = password if confirmation is None else confirmation
    return app.test_cli_runner().invoke(
        args=ARGS, input=f"{password}\n{confirmation}\n"
    )


def test_fails_cleanly_when_database_is_not_configured():
    result = make_app().test_cli_runner().invoke(args=ARGS)

    assert result.exit_code != 0
    assert "Database is not configured" in result.output
    assert "Traceback" not in result.output


@pytest.mark.db
def test_creates_the_first_admin(cli_app, db_session):
    result = run(cli_app)

    assert result.exit_code == 0, result.output
    assert "Admin created: boss@shop.al" in result.output

    admin = db_session.scalars(select(User)).one()

    assert admin.email == "boss@shop.al"
    assert admin.role is UserRole.ADMIN
    assert admin.is_active is True
    assert verify_password(admin.password_hash, PASSWORD)
    assert admin.password_hash not in result.output
    assert PASSWORD not in result.output


@pytest.mark.db
def test_refuses_when_an_admin_already_exists(cli_app, db_session):
    assert run(cli_app).exit_code == 0

    result = cli_app.test_cli_runner().invoke(
        args=["create-admin", "--email", "second@shop.al", "--full-name", "Second"]
    )

    assert result.exit_code != 0
    assert "An admin already exists" in result.output
    assert "Password" not in result.output
    assert len(db_session.scalars(select(User)).all()) == 1


@pytest.mark.db
def test_rejects_a_short_password_without_echoing_it(cli_app, db_session):
    result = run(cli_app, password="short-pw")

    assert result.exit_code != 0
    assert "password:" in result.output
    assert "short-pw" not in result.output
    assert "Traceback" not in result.output
    assert db_session.scalars(select(User)).all() == []


@pytest.mark.db
def test_reprompts_when_confirmation_does_not_match(cli_app, db_session):
    result = cli_app.test_cli_runner().invoke(
        args=ARGS,
        input=f"{PASSWORD}\nsomething-else-entirely\n{PASSWORD}\n{PASSWORD}\n",
    )

    assert result.exit_code == 0, result.output
    assert "do not match" in result.output
    assert len(db_session.scalars(select(User)).all()) == 1
