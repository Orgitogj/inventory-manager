import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.database import Base


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    WAREHOUSE = "warehouse"
    SALES = "sales"


def normalize_email(value: str) -> str:
    return value.strip().lower()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(btrim(email))", name="email_normalized"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda roles: [role.value for role in roles],
        )
    )
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @validates("email")
    def _normalize_email(self, _key: str, value: str) -> str:
        return normalize_email(value)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role}>"
