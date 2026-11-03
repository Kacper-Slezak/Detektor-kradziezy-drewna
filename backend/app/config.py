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
    # Wspólne hasło kont demo z `python -m app.seed --demo`. Tylko do testów i prezentacji!
    seed_demo_password: str = "demo-haslo-1"

    # Powtórzenia ALARM (wysyłane 3x) z tego okna scalamy w jeden alarm.
    alarm_merge_window_s: int = 600

    # Brak ramki dłużej niż tyle godzin = stan "silent" (heartbeat co ~6 h, więc 2 zgubione).
    sensor_silent_after_h: int = 12


settings = Settings()
