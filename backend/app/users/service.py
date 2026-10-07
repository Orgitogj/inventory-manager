from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.users.models import User, UserRole
from app.users.schemas import StaffCreate

UNIQUE_EMAIL_CONSTRAINT = "uq_users_email"


class EmailAlreadyExistsError(Exception):
    def __init__(self, email: str) -> None:
        super().__init__(f"A user with email {email!r} already exists.")
        self.email = email


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
