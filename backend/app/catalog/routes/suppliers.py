import uuid

from fastapi import APIRouter, Depends

from app.auth.dependencies import current_session, require_role
from app.catalog.schemas import (
    SupplierCreate,
    SupplierListOut,
    SupplierOut,
    SupplierUpdate,
)
from app.catalog.service import (
    SupplierNameTakenError,
    create_supplier,
    get_supplier,
    list_suppliers,
    update_supplier,
)
from app.database import DbSession
from app.errors import ApiError
from app.users.models import UserRole

router = APIRouter(prefix="/api/v1/suppliers", tags=["suppliers"])

LOGGED_IN = [Depends(current_session)]
ADMIN_ONLY = [Depends(require_role(UserRole.ADMIN))]


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Supplier not found.")


def name_taken() -> ApiError:
    return ApiError(409, "name_taken", "A supplier with this name already exists.")


@router.get("", response_model=SupplierListOut, dependencies=LOGGED_IN)
def list_all(db: DbSession, include_archived: bool = False) -> SupplierListOut:
    suppliers = list_suppliers(db, include_archived)
    return SupplierListOut(
        suppliers=[SupplierOut.model_validate(supplier) for supplier in suppliers]
    )


@router.get("/{supplier_id}", response_model=SupplierOut, dependencies=LOGGED_IN)
def get_one(supplier_id: uuid.UUID, db: DbSession) -> SupplierOut:
    supplier = get_supplier(db, supplier_id)

    if supplier is None:
        raise not_found()

    return SupplierOut.model_validate(supplier)


@router.post("", response_model=SupplierOut, status_code=201, dependencies=ADMIN_ONLY)
def create(data: SupplierCreate, db: DbSession) -> SupplierOut:
    try:
        supplier = create_supplier(db, data)
    except SupplierNameTakenError:
        raise name_taken() from None

    db.commit()
    return SupplierOut.model_validate(supplier)


@router.patch("/{supplier_id}", response_model=SupplierOut, dependencies=ADMIN_ONLY)
def update(supplier_id: uuid.UUID, data: SupplierUpdate, db: DbSession) -> SupplierOut:
    supplier = get_supplier(db, supplier_id)

    if supplier is None:
        raise not_found()

    try:
        update_supplier(db, supplier, data)
    except SupplierNameTakenError:
        raise name_taken() from None

    db.commit()
    return SupplierOut.model_validate(supplier)
