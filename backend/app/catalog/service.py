import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog.models import Category, Supplier
from app.catalog.schemas import (
    CategoryCreate,
    CategoryUpdate,
    SupplierCreate,
    SupplierUpdate,
)
from app.users.service import violated_constraint

UNIQUE_CATEGORY_NAME_INDEX = "uq_categories_name_lower"
UNIQUE_SUPPLIER_NAME_INDEX = "uq_suppliers_name_lower"


class CategoryNameTakenError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"A category named {name!r} already exists.")
        self.name = name


class SupplierNameTakenError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"A supplier named {name!r} already exists.")
        self.name = name


def create_category(session: Session, data: CategoryCreate) -> Category:
    category = Category(name=data.name, description=data.description)

    try:
        with session.begin_nested():
            session.add(category)
    except IntegrityError as error:
        if violated_constraint(error) == UNIQUE_CATEGORY_NAME_INDEX:
            raise CategoryNameTakenError(data.name) from None
        raise

    return category


def list_categories(session: Session, include_archived: bool = False) -> list[Category]:
    query = select(Category).order_by(func.lower(Category.name))

    if not include_archived:
        query = query.where(Category.is_archived.is_(False))

    return list(session.scalars(query))


def get_category(session: Session, category_id: uuid.UUID) -> Category | None:
    return session.get(Category, category_id)


def update_category(
    session: Session, category: Category, data: CategoryUpdate
) -> Category:
    changes = data.model_dump(exclude_unset=True)

    try:
        with session.begin_nested():
            for field, value in changes.items():
                setattr(category, field, value)
    except IntegrityError as error:
        if violated_constraint(error) == UNIQUE_CATEGORY_NAME_INDEX:
            raise CategoryNameTakenError(changes["name"]) from None
        raise

    return category


def create_supplier(session: Session, data: SupplierCreate) -> Supplier:
    supplier = Supplier(
        name=data.name, email=data.email, phone=data.phone, notes=data.notes
    )

    try:
        with session.begin_nested():
            session.add(supplier)
    except IntegrityError as error:
        if violated_constraint(error) == UNIQUE_SUPPLIER_NAME_INDEX:
            raise SupplierNameTakenError(data.name) from None
        raise

    return supplier


def list_suppliers(session: Session, include_archived: bool = False) -> list[Supplier]:
    query = select(Supplier).order_by(func.lower(Supplier.name))

    if not include_archived:
        query = query.where(Supplier.is_archived.is_(False))

    return list(session.scalars(query))


def get_supplier(session: Session, supplier_id: uuid.UUID) -> Supplier | None:
    return session.get(Supplier, supplier_id)


def update_supplier(
    session: Session, supplier: Supplier, data: SupplierUpdate
) -> Supplier:
    changes = data.model_dump(exclude_unset=True)

    try:
        with session.begin_nested():
            for field, value in changes.items():
                setattr(supplier, field, value)
    except IntegrityError as error:
        if violated_constraint(error) == UNIQUE_SUPPLIER_NAME_INDEX:
            raise SupplierNameTakenError(changes["name"]) from None
        raise

    return supplier
