"""Kto widzi które leśnictwo. Wspólne dla czujników, alarmów i (później) wydań.

- leśniczy: tylko swoje leśnictwo; bez przypisanego leśnictwa nie widzi nic,
- nadleśniczy i admin: wszystko.
"""

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, false

from app.models import Sensor, User


def range_filter(user: User) -> ColumnElement[bool] | None:
    """Warunek WHERE na czujnikach widocznych dla użytkownika (None = bez ograniczeń)."""
    if user.role != "forester":
        return None
    if user.range_id is None:
        # `Sensor.range_id == None` dałoby IS NULL, czyli czujniki bez leśnictwa
        return false()
    return Sensor.range_id == user.range_id


def check_range_access(range_id: int | None, user: User, detail: str) -> None:
    """403, gdy leśniczy sięga po coś z cudzego leśnictwa."""
    if user.role == "forester" and (user.range_id is None or range_id != user.range_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail)
