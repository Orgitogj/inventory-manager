import click
from flask.cli import with_appcontext
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.database import DatabaseNotConfiguredError, get_session_factory
from app.users.models import UserRole
from app.users.schemas import StaffCreate, describe_validation_error
from app.users.service import EmailAlreadyExistsError, admin_exists, create_user


@click.command(
    "create-admin",
    help="Create the first admin user. Works only while no admin exists.",
)
@click.option("--email", required=True, help="Email address of the first admin.")
@click.option("--full-name", required=True, help="Full name of the first admin.")
@with_appcontext
def create_admin(email: str, full_name: str) -> None:
    try:
        session_factory = get_session_factory()
    except DatabaseNotConfiguredError:
        raise click.ClickException(
            "Database is not configured. Check DATABASE_URL."
        ) from None

    try:
        with session_factory() as session:
            if admin_exists(session):
                raise click.ClickException(
                    "An admin already exists. "
                    "New admins must be created by an existing admin."
                )

            password = click.prompt(
                "Password", hide_input=True, confirmation_prompt=True
            )

            try:
                data = StaffCreate(
                    email=email,
                    full_name=full_name,
                    password=password,
                    role=UserRole.ADMIN,
                )
            except ValidationError as error:
                raise click.ClickException(
                    "Invalid input:\n" + describe_validation_error(error)
                ) from None

            try:
                user = create_user(session, data)
            except EmailAlreadyExistsError as error:
                raise click.ClickException(str(error)) from None

            session.commit()
            click.echo(f"Admin created: {user.email}")
    except OperationalError:
        raise click.ClickException(
            "Database connection failed. Check DATABASE_URL and PostgreSQL."
        ) from None
