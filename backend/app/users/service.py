import uuid

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.auth.service import end_all_sessions
from app.users.models import User, UserRole
from app.users.schemas import StaffCreate, StaffUpdate

UNIQUE_EMAIL_CONSTRAINT = "uq_users_email"


class EmailAlreadyExistsError(Exception):
    def __init__(self, email: str) -> None:
        super().__init__(f"A user with email {email!r} already exists.")
        self.email = email


class SelfModificationError(Exception):
    def __init__(self) -> None:
        super().__init__("You cannot change your own role or deactivate yourself.")


class LastAdminError(Exception):
    def __init__(self) -> None:
        super().__init__("The last active admin cannot be demoted or deactivated.")


def violated_constraint(error: IntegrityError) -> str | None:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def admin_exists(session: Session) -> bool:
    return session.scalar(select(exists().where(User.role == UserRole.ADMIN)))


def create_user(session: Session, data: StaffCreate) -> User:
    user = User(
        email=data.email,
        full_name=data.full_name,
        password_hash=hash_password(data.password.get_secret_value()),
        role=data.role,
    )

    try:
        with session.begin_nested():
            session.add(user)
    except IntegrityError as error:
        if violated_constraint(error) == UNIQUE_EMAIL_CONSTRAINT:
            raise EmailAlreadyExistsError(user.email) from None
        raise

    return user


def list_users(session: Session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.created_at, User.id)))


def get_user(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def lock_active_admin_ids(session: Session) -> set[uuid.UUID]:
    return set(
        session.scalars(
            select(User.id)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
            .order_by(User.id)
            .with_for_update()
        )
    )


def update_user(session: Session, actor: User, target: User, data: StaffUpdate) -> User:
    changes = data.model_dump(exclude_unset=True)
    new_role = changes.get("role", target.role)
    new_is_active = changes.get("is_active", target.is_active)

    if actor.id == target.id and (new_role != target.role or not new_is_active):
        raise SelfModificationError

    is_active_admin = target.role == UserRole.ADMIN and target.is_active
    stays_active_admin = new_role == UserRole.ADMIN and new_is_active

    if (
        is_active_admin
        and not stays_active_admin
        and lock_active_admin_ids(session) <= {target.id}
    ):
        raise LastAdminError

    was_active = target.is_active

    for field, value in changes.items():
        setattr(target, field, value)

    session.flush()

    if was_active and not target.is_active:
        end_all_sessions(session, target.id)

    return target
