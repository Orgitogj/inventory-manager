import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import translate_unique_violation, violated_constraint

UNIQUE_NAME_INDEX = "uq_categories_name_lower"
INSERT = text("INSERT INTO categories (id, name) VALUES (gen_random_uuid(), :name)")


class NameTakenError(Exception):
    pass


def insert(session, name: str) -> None:
    with (
        translate_unique_violation(UNIQUE_NAME_INDEX, lambda: NameTakenError(name)),
        session.begin_nested(),
    ):
        session.execute(INSERT, {"name": name})


def count_categories(session) -> int:
    return session.scalar(text("SELECT count(*) FROM categories"))


def test_errors_other_than_integrity_errors_pass_through_unchanged():
    original = ValueError("unrelated")

    with pytest.raises(ValueError) as error, translate_unique_violation("uq", KeyError):
        raise original

    assert error.value is original


def test_error_factory_is_not_called_without_a_violation():
    calls: list[str] = []

    with translate_unique_violation("uq", lambda: calls.append("called")):
        pass

    assert calls == []


@pytest.mark.db
def test_block_without_a_violation_runs_normally(db_session):
    insert(db_session, "Pije")

    assert count_categories(db_session) == 1


@pytest.mark.db
def test_expected_violation_becomes_the_domain_error(db_session):
    insert(db_session, "Pije")

    with pytest.raises(NameTakenError) as error:
        insert(db_session, "pije")

    assert str(error.value) == "pije"
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True


@pytest.mark.db
def test_other_violation_keeps_the_original_integrity_error(db_session):
    with pytest.raises(IntegrityError) as error:
        insert(db_session, " Pije")

    assert violated_constraint(error.value) == "ck_categories_name_trimmed"


@pytest.mark.db
def test_violation_of_another_unique_constraint_is_not_translated(db_session):
    insert(db_session, "Pije")

    with (
        pytest.raises(IntegrityError) as error,
        translate_unique_violation("uq_some_other_constraint", NameTakenError),
        db_session.begin_nested(),
    ):
        db_session.execute(INSERT, {"name": "pije"})

    assert violated_constraint(error.value) == UNIQUE_NAME_INDEX


@pytest.mark.db
def test_session_stays_usable_after_a_translated_error(db_session):
    insert(db_session, "Pije")

    with pytest.raises(NameTakenError):
        insert(db_session, "PIJE")

    insert(db_session, "Ushqim")
    db_session.commit()

    assert count_categories(db_session) == 2


@pytest.mark.db
def test_session_stays_usable_after_an_untranslated_error(db_session):
    with pytest.raises(IntegrityError):
        insert(db_session, "")

    insert(db_session, "Pije")

    assert count_categories(db_session) == 1


def test_violated_constraint_is_none_without_database_diagnostics():
    error = IntegrityError("INSERT", {}, Exception("no diagnostics"))

    assert violated_constraint(error) is None
