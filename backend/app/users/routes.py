import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_role
from app.database import DbSession
from app.errors import ApiError
from app.users.models import User, UserRole
from app.users.schemas import StaffCreate, StaffListOut, StaffOut, StaffUpdate
from app.users.service import (
    EmailAlreadyExistsError,
    LastAdminError,
    SelfModificationError,
    create_user,
    get_user,
    list_users,
    update_user,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])

AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]
ADMIN_ONLY = [Depends(require_role(UserRole.ADMIN))]


def not_found() -> ApiError:
    return ApiError(404, "not_found", "User not found.")


@router.post("", response_model=StaffOut, status_code=201, dependencies=ADMIN_ONLY)
def create_staff(data: StaffCreate, db: DbSession) -> StaffOut:
    try:
        user = create_user(db, data)
    except EmailAlreadyExistsError:
        raise ApiError(
            409, "email_taken", "A user with this email already exists."
        ) from None

    db.commit()
    return StaffOut.model_validate(user)


@router.get("", response_model=StaffListOut, dependencies=ADMIN_ONLY)
def list_staff(db: DbSession) -> StaffListOut:
    return StaffListOut(
        users=[StaffOut.model_validate(user) for user in list_users(db)]
    )


@router.get("/{user_id}", response_model=StaffOut, dependencies=ADMIN_ONLY)
def get_staff(user_id: uuid.UUID, db: DbSession) -> StaffOut:
    user = get_user(db, user_id)

    if user is None:
        raise not_found()

    return StaffOut.model_validate(user)


@router.patch("/{user_id}", response_model=StaffOut)
def update_staff(
    user_id: uuid.UUID, data: StaffUpdate, db: DbSession, actor: AdminUser
) -> StaffOut:
    user = get_user(db, user_id)

    if user is None:
        raise not_found()

    try:
        update_user(db, actor, user, data)
    except SelfModificationError as error:
        raise ApiError(409, "self_modification", str(error)) from None
    except LastAdminError as error:
        raise ApiError(409, "last_admin", str(error)) from None

    db.commit()
    return StaffOut.model_validate(user)
