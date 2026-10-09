import pytest
from pydantic import ValidationError

from app.catalog.schemas import CategoryCreate, CategoryUpdate


def error_fields(error: ValidationError) -> set[str]:
    return {".".join(str(part) for part in detail["loc"]) for detail in error.errors()}


def test_name_and_description_are_cleaned():
    data = CategoryCreate(name="  Pije  ", description="  Freskuese  ")

    assert data.name == "Pije"
    assert data.description == "Freskuese"


@pytest.mark.parametrize("description", ["", "   ", None])
def test_blank_description_becomes_none(description):
    assert CategoryCreate(name="Pije", description=description).description is None


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"name": "   "}, "name"),
        ({"name": "x" * 101}, "name"),
        ({"name": "Pije", "description": "x" * 501}, "description"),
        ({"name": "Pije", "is_archived": True}, "is_archived"),
        ({}, "name"),
    ],
)
def test_invalid_create_input_is_rejected(payload, field):
    with pytest.raises(ValidationError) as error:
        CategoryCreate.model_validate(payload)

    assert error_fields(error.value) == {field}


def test_update_keeps_only_sent_fields():
    data = CategoryUpdate.model_validate({"is_archived": True})

    assert data.model_dump(exclude_unset=True) == {"is_archived": True}


def test_update_allows_clearing_the_description():
    data = CategoryUpdate.model_validate({"description": None})

    assert data.model_dump(exclude_unset=True) == {"description": None}


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({}, ""),
        ({"name": None}, "name"),
        ({"is_archived": None}, "is_archived"),
        ({"is_archived": 1}, "is_archived"),
        ({"unknown": "x"}, "unknown"),
    ],
)
def test_invalid_update_input_is_rejected(payload, field):
    with pytest.raises(ValidationError) as error:
        CategoryUpdate.model_validate(payload)

    assert error_fields(error.value) == {field}
