from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


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
