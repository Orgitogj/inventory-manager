import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import current_session, require_role
from app.customers.schemas import (
    CustomerCreate,
    CustomerListOut,
    CustomerListQuery,
    CustomerOut,
    CustomerUpdate,
)
from app.customers.service import (
    create_customer,
    get_customer,
    list_customers,
    update_customer,
)
from app.database import DbSession
from app.errors import ApiError
from app.users.models import UserRole

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])

LOGGED_IN = [Depends(current_session)]
CAN_WRITE = [Depends(require_role(UserRole.ADMIN, UserRole.SALES))]


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Customer not found.")


@router.get("", response_model=CustomerListOut, dependencies=LOGGED_IN)
def list_all(
    filters: Annotated[CustomerListQuery, Query()], db: DbSession
) -> CustomerListOut:
    customers, total = list_customers(db, filters)
    return CustomerListOut(
        customers=[CustomerOut.model_validate(customer) for customer in customers],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get("/{customer_id}", response_model=CustomerOut, dependencies=LOGGED_IN)
def get_one(customer_id: uuid.UUID, db: DbSession) -> CustomerOut:
    customer = get_customer(db, customer_id)

    if customer is None:
        raise not_found()

    return CustomerOut.model_validate(customer)


@router.post("", response_model=CustomerOut, status_code=201, dependencies=CAN_WRITE)
def create(data: CustomerCreate, db: DbSession) -> CustomerOut:
    customer = create_customer(db, data)
    db.commit()
    return CustomerOut.model_validate(customer)


@router.patch("/{customer_id}", response_model=CustomerOut, dependencies=CAN_WRITE)
def update(customer_id: uuid.UUID, data: CustomerUpdate, db: DbSession) -> CustomerOut:
    customer = get_customer(db, customer_id)

    if customer is None:
        raise not_found()

    update_customer(db, customer, data)
    db.commit()
    return CustomerOut.model_validate(customer)
