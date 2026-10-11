from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["health"])


class HealthOut(BaseModel):
    status: Literal["ok"]
    service: str


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok", service="inventory-api")
