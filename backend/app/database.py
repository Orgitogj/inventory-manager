import click
from flask import Flask, current_app
from sqlalchemy import Engine, MetaData, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_engine() -> Engine:
    engine = current_app.extensions.get("database_engine")

    if engine is None:
        raise RuntimeError("Database is not configured.")

    return engine


@click.command("db-check")
def db_check():
    try:
        with get_engine().connect() as connection:
            row = connection.execute(
                text("SELECT current_database(), current_user")
            ).one()
    except SQLAlchemyError, RuntimeError:
        raise click.ClickException(
            "Database connection failed. Check DATABASE_URL and PostgreSQL."
        ) from None

    click.echo(f"Database: {row[0]}")
    click.echo(f"User: {row[1]}")
    click.echo("Connection successful.")


def init_database(app: Flask) -> None:
    database_url = app.config["DATABASE_URL"]

    if database_url:
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5},
        )
        app.extensions["database_engine"] = engine

    app.cli.add_command(db_check)
