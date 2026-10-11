import click
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.database import DatabaseNotConfiguredError, build_session_factory
from app.users.models import UserRole
from app.users.schemas import StaffCreate, describe_validation_error
from app.users.service import EmailAlreadyExistsError, admin_exists, create_user


def get_session_factory(context: click.Context) -> sessionmaker[Session]:
    options = context.obj or {}
    session_factory = options.get("session_factory")

    if session_factory is not None:
        return session_factory

    settings = options.get("settings") or Settings()

    if not settings.database_url:
        raise DatabaseNotConfiguredError("Database is not configured.")

    return build_session_factory(settings.database_url)


@click.group()
def cli() -> None:
    pass


@cli.command(
    "create-admin",
    help="Create the first admin user. Works only while no admin exists.",
)
@click.option("--email", required=True, help="Email address of the first admin.")
@click.option("--full-name", required=True, help="Full name of the first admin.")
@click.pass_context
def create_admin(context: click.Context, email: str, full_name: str) -> None:
    try:
        session_factory = get_session_factory(context)
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


@cli.command("db-check", help="Check the connection to the configured database.")
@click.pass_context
def db_check(context: click.Context) -> None:
    try:
        with get_session_factory(context)() as session:
            row = session.execute(text("SELECT current_database(), current_user")).one()
    except SQLAlchemyError, DatabaseNotConfiguredError:
        raise click.ClickException(
            "Database connection failed. Check DATABASE_URL and PostgreSQL."
        ) from None

    click.echo(f"Database: {row[0]}")
    click.echo(f"User: {row[1]}")
    click.echo("Connection successful.")


if __name__ == "__main__":
    cli()
