from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IngestIn(BaseModel):
    device: str = Field(min_length=1, max_length=32, examples=["70B3D57ED0051234"])
    payload_hex: str = Field(min_length=2, max_length=128, examples=["11002A0101570028B440"])
    # bez czasu = "teraz" (bramka może go nie podać)
    received_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), examples=["2026-10-16T10:00:00Z"]
    )
    rssi: int | None = Field(default=None, examples=[-112])

    @field_validator("payload_hex")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.replace(" ", "")

    @field_validator("received_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:  # bez strefy = przyjmujemy UTC
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)


class IngestOut(BaseModel):
    status: str
    message_id: int | None
    alarm_id: int | None
    alarm_created: bool
    muted: bool


# --- Logowanie i użytkownicy ---

Role = Literal["forester", "district_manager", "admin"]

Password = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=50, examples=["blazej"])
    password: str = Field(min_length=1, max_length=128)


class RangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ProfileOut(BaseModel):
    """Zalogowany użytkownik (login i /auth/me)."""

    id: int
    login: str
    full_name: str
    role: Role
    range: RangeOut | None
    must_change_password: bool


class LoginOut(BaseModel):
    token: str
    expires_at: datetime
    user: ProfileOut


class ChangePasswordIn(BaseModel):
    old_password: str = Field(max_length=128)
    new_password: str = Password


class UserOut(BaseModel):
    """Użytkownik w panelu admina."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    full_name: str
    role: Role
    range_id: int | None
    active: bool
    must_change_password: bool


class UserCreate(BaseModel):
    login: str = Field(min_length=1, max_length=50, examples=["nowy.lesniczy"])
    full_name: str = Field(min_length=1, max_length=100, examples=["Jan Nowy"])
    role: Role
    range_id: int | None = None
    password: str = Password


class UserPatch(BaseModel):
    """Zmiana roli, leśnictwa, nazwy albo dezaktywacja. `range_id: null` odpina leśnictwo."""

    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Role | None = None
    range_id: int | None = None
    active: bool | None = None


class TempPasswordOut(BaseModel):
    temporary_password: str
