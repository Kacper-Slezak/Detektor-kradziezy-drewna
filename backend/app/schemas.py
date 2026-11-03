import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


# --- Czujniki ---

SensorState = Literal["ok", "muted", "alarm", "silent", "inactive"]

# ID czujnika = DevEUI: 16 znaków szesnastkowych. Na naklejkach bywa ze spacjami, myślnikami
# albo dwukropkami, więc je usuwamy i zamieniamy na wielkie litery.
SENSOR_ID_RE = re.compile(r"^[0-9A-F]{16}$")


def normalize_sensor_id(value: str) -> str:
    return re.sub(r"[\s:-]", "", value).upper()


class SensorOut(BaseModel):
    """Czujnik na mapie i w panelu admina. `state` wylicza backend (api.md, sekcja 2)."""

    id: str
    name: str | None
    lat: float | None
    lon: float | None
    range_id: int | None
    active: bool
    state: SensorState
    battery_pct: int | None
    last_seen: datetime | None
    muted_until: datetime | None
    open_alarm_id: int | None


class AlarmBrief(BaseModel):
    id: int
    detected_at: datetime
    status: str
    confidence: int


class ReleaseBrief(BaseModel):
    id: int
    starts_at: datetime
    ends_at: datetime
    carrier: str | None
    log_count: int | None


class SensorDetailOut(SensorOut):
    recent_alarms: list[AlarmBrief]
    recent_releases: list[ReleaseBrief]


class SensorCreate(BaseModel):
    """Rejestracja czujnika przez admina. Nowy czujnik jest nieaktywny do montażu."""

    id: str = Field(examples=["70B3D57ED0051234"])
    range_id: int
    name: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("id")
    @classmethod
    def _sensor_id(cls, v: str) -> str:
        v = normalize_sensor_id(v)
        if not SENSOR_ID_RE.fullmatch(v):
            raise ValueError("ID czujnika musi mieć 16 znaków szesnastkowych (DevEUI)")
        return v


class SensorPatch(BaseModel):
    """Zmiana nazwy, leśnictwa (tylko admin) albo włączenie/wyłączenie.

    `name: null` usuwa nazwę. Leśnictwa nie da się odpiąć (`range_id: null` → 422).
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    range_id: int | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def _no_nulls(self):
        for field in ("range_id", "active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"Pole {field} nie może być null")
        return self


# --- Alarmy ---

AlarmStatus = Literal["new", "theft", "false_alarm"]

# kod rodzaju zdarzenia z ramki ALARM -> nazwa w API. Listę ustala Kiryl (docs/protocol.md),
# nieznane kody pokazujemy jako "unknown", żeby nowy firmware nie psuł apki.
EVENT_TYPES = {0: "unknown", 1: "theft"}


class AlarmSensor(BaseModel):
    id: str
    name: str | None
    lat: float | None
    lon: float | None


class AlarmResponse(BaseModel):
    by: str
    at: datetime
    comment: str | None
    lat: float | None
    lon: float | None


class AlarmOut(BaseModel):
    id: int
    detected_at: datetime
    last_frame_at: datetime
    sensor: AlarmSensor
    event_type: str
    sources: list[str]
    confidence: int
    duration_s: int
    energy: int
    repeats: int
    possible_tampering: bool
    status: AlarmStatus
    response: AlarmResponse | None


class AlarmResponseIn(BaseModel):
    """Odpowiedź leśniczego po sprawdzeniu na miejscu. Pozycja z telefonu jest opcjonalna."""

    result: Literal["theft", "false_alarm"]
    comment: str | None = Field(default=None, max_length=500)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _both_or_none(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError("Podaj obie współrzędne (lat i lon) albo żadnej")
        return self
