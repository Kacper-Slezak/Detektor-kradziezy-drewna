# Konfiguracja

Zmienne trzymamy w `backend/.env` (poza repo). Wzór: `backend/.env.example`.

| Zmienna | Opis |
|---|---|
| `POSTGRES_PASSWORD` | Hasło użytkownika `detektor` w bazie; używane przez compose |
| `DATABASE_URL` | Adres bazy dla aplikacji (sterownik async: `postgresql+asyncpg://`) |
| `TTN_WEBHOOK_SECRET` | Sekret webhooka z The Things Network |
| `FIREBASE_CREDENTIALS_PATH` | Ścieżka do poświadczeń Firebase (powiadomienia) |
| `JWT_SECRET` | Klucz do podpisywania tokenów JWT |

## DATABASE_URL: Docker vs lokalnie

- **W Dockerze** compose nadpisuje wartość na `postgresql+asyncpg://detektor:${POSTGRES_PASSWORD}@timescaledb:5432/detektor` – host to nazwa serwisu, nie `localhost`.
- **Bez Dockera** ustaw w `.env`: `postgresql+asyncpg://detektor:<hasło>@localhost:5432/detektor`.

Przedrostek `+asyncpg` jest wymagany, bo używamy async SQLAlchemy.

Nigdy nie commituj `.env`.
