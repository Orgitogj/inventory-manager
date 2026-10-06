import click
from flask import Flask, current_app
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


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
