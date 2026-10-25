from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://detektor:detektor@localhost:5432/detektor"

    # Klucz do podpisywania tokenów JWT (.env).
    jwt_secret: str = ""
    jwt_expire_hours: int = 24

    # Konto admina tworzone przez `python -m app.seed`. Bez hasła zostanie wylosowane.
    seed_admin_login: str = "admin"
    seed_admin_password: str = ""

    # Powtórzenia ALARM (wysyłane 3x) z tego okna scalamy w jeden alarm.
    alarm_merge_window_s: int = 600


settings = Settings()
