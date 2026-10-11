import uuid

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.catalog.service import LIKE_ESCAPE, escape_like
from app.customers.models import Customer
from app.customers.schemas import CustomerCreate, CustomerListQuery, CustomerUpdate


def create_customer(session: Session, data: CustomerCreate) -> Customer:
    customer = Customer(**data.model_dump())
    session.add(customer)
    session.flush()
    return customer


def customer_conditions(filters: CustomerListQuery) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []

    if not filters.include_archived:
        conditions.append(Customer.is_archived.is_(False))

    if filters.search is not None:
        pattern = f"%{escape_like(filters.search)}%"
        conditions.append(
            or_(
                Customer.name.ilike(pattern, escape=LIKE_ESCAPE),
                Customer.email.ilike(pattern, escape=LIKE_ESCAPE),
                Customer.phone.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )

    return conditions


def list_customers(
    session: Session, filters: CustomerListQuery
) -> tuple[list[Customer], int]:
    conditions = customer_conditions(filters)
    total = session.scalar(
        select(func.count()).select_from(Customer).where(*conditions)
    )
    customers = session.scalars(
        select(Customer)
        .where(*conditions)
        .order_by(func.lower(Customer.name), Customer.created_at, Customer.id)
        .limit(filters.limit)
        .offset(filters.offset)
    )

    return list(customers), total


def get_customer(session: Session, customer_id: uuid.UUID) -> Customer | None:
    return session.get(Customer, customer_id)


def update_customer(
    session: Session, customer: Customer, data: CustomerUpdate
) -> Customer:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)

    session.flush()
    return customer
