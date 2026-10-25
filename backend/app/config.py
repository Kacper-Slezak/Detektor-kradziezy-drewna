from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://detektor:detektor@localhost:5432/detektor"

    # Powtórzenia ALARM (wysyłane 3x) z tego okna scalamy w jeden alarm.
    alarm_merge_window_s: int = 600


settings = Settings()
