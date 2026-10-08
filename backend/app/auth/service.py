import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth.models import UserSession
from app.auth.passwords import hash_password, needs_rehash, verify_password
from app.users.models import User, normalize_email


class InvalidCredentialsError(Exception):
    pass


@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf_token: str
    expires_at: datetime


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@cache
def _dummy_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


def authenticate(session: Session, email: str, password: str) -> User:
    user = session.scalar(select(User).where(User.email == normalize_email(email)))

    if user is None:
        verify_password(_dummy_password_hash(), password)
        raise InvalidCredentialsError

    if not verify_password(user.password_hash, password) or not user.is_active:
        raise InvalidCredentialsError

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    return user


def start_session(session: Session, user: User, lifetime: timedelta) -> IssuedSession:
    issued = IssuedSession(
        token=secrets.token_urlsafe(32),
        csrf_token=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + lifetime,
    )
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(issued.token),
            csrf_token=issued.csrf_token,
            expires_at=issued.expires_at,
        )
    )
    session.flush()
    return issued


def find_active_session(session: Session, token: str) -> UserSession | None:
    return session.scalar(
        select(UserSession)
        .join(UserSession.user)
        .where(
            UserSession.token_hash == hash_token(token),
            UserSession.expires_at > func.now(),
            User.is_active.is_(True),
        )
    )


def end_session(session: Session, user_session: UserSession) -> None:
    session.delete(user_session)
    session.flush()


def end_all_sessions(session: Session, user_id: uuid.UUID) -> None:
    session.execute(delete(UserSession).where(UserSession.user_id == user_id))
