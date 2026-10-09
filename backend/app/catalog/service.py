import uuid

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog.models import Category, Product, Supplier
from app.catalog.schemas import (
    CategoryCreate,
    CategoryUpdate,
    ProductCreate,
    ProductListQuery,
    ProductUpdate,
    SupplierCreate,
    SupplierUpdate,
)
from app.database import violated_constraint

UNIQUE_CATEGORY_NAME_INDEX = "uq_categories_name_lower"
UNIQUE_SUPPLIER_NAME_INDEX = "uq_suppliers_name_lower"
UNIQUE_PRODUCT_SKU_CONSTRAINT = "uq_products_sku"
LIKE_ESCAPE = "\\"


class CategoryNameTakenError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"A category named {name!r} already exists.")
        self.name = name


class SupplierNameTakenError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"A supplier named {name!r} already exists.")
        self.name = name


class SkuTakenError(Exception):
    def __init__(self, sku: str) -> None:
        super().__init__(f"A product with SKU {sku!r} already exists.")
        self.sku = sku


class InvalidReferenceError(Exception):
    def __init__(self, field: str) -> None:
        super().__init__("Referenced record does not exist.")
        self.field = field


class ArchivedReferenceError(Exception):
    def __init__(self, field: str) -> None:
        super().__init__("Referenced record is archived.")
        self.field = field


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


def escape_like(value: str) -> str:
    return (
        value.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )


def require_usable_reference(
    session: Session,
    model: type[Category | Supplier],
    reference_id: uuid.UUID,
    field: str,
) -> None:
    referenced = session.get(model, reference_id)

    if referenced is None:
        raise InvalidReferenceError(field)

    if referenced.is_archived:
        raise ArchivedReferenceError(field)


def create_product(session: Session, data: ProductCreate) -> Product:
    require_usable_reference(session, Category, data.category_id, "category_id")

    if data.supplier_id is not None:
        require_usable_reference(session, Supplier, data.supplier_id, "supplier_id")

    product = Product(
        sku=data.sku,
        name=data.name,
        description=data.description,
        category_id=data.category_id,
        supplier_id=data.supplier_id,
        unit_price=data.unit_price,
    )

    try:
        with session.begin_nested():
            session.add(product)
    except IntegrityError as error:
        if violated_constraint(error) == UNIQUE_PRODUCT_SKU_CONSTRAINT:
            raise SkuTakenError(data.sku) from None
        raise

    return product


def product_conditions(filters: ProductListQuery) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []

    if not filters.include_archived:
        conditions.append(Product.is_archived.is_(False))

    if filters.category_id is not None:
        conditions.append(Product.category_id == filters.category_id)

    if filters.supplier_id is not None:
        conditions.append(Product.supplier_id == filters.supplier_id)

    if filters.search is not None:
        pattern = f"%{escape_like(filters.search)}%"
        conditions.append(
            or_(
                Product.name.ilike(pattern, escape=LIKE_ESCAPE),
                Product.sku.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )

    return conditions


def list_products(
    session: Session, filters: ProductListQuery
) -> tuple[list[Product], int]:
    conditions = product_conditions(filters)
    total = session.scalar(select(func.count()).select_from(Product).where(*conditions))
    products = session.scalars(
        select(Product)
        .where(*conditions)
        .order_by(func.lower(Product.name), Product.sku)
        .limit(filters.limit)
        .offset(filters.offset)
    )

    return list(products), total


def get_product(session: Session, product_id: uuid.UUID) -> Product | None:
    return session.get(Product, product_id)


def update_product(session: Session, product: Product, data: ProductUpdate) -> Product:
    changes = data.model_dump(exclude_unset=True)
    category_id = changes.get("category_id", product.category_id)
    supplier_id = changes.get("supplier_id", product.supplier_id)

    if category_id != product.category_id:
        require_usable_reference(session, Category, category_id, "category_id")

    if supplier_id is not None and supplier_id != product.supplier_id:
        require_usable_reference(session, Supplier, supplier_id, "supplier_id")

    try:
        with session.begin_nested():
            for field, value in changes.items():
                setattr(product, field, value)
    except IntegrityError as error:
        if violated_constraint(error) == UNIQUE_PRODUCT_SKU_CONSTRAINT:
            raise SkuTakenError(changes["sku"]) from None
        raise

    session.expire(product, ["category", "supplier"])
    return product
