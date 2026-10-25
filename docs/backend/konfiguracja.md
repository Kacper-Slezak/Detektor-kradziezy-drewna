# Konfiguracja

Zmienne trzymamy w `backend/.env` (poza repo). Wzór: `backend/.env.example`.

| Zmienna | Opis |
|---|---|
| `POSTGRES_PASSWORD` | Hasło użytkownika `detektor` w bazie; używane przez compose |
| `DATABASE_URL` | Adres bazy dla aplikacji (sterownik async: `postgresql+asyncpg://`) |
| `TTN_WEBHOOK_SECRET` | Sekret webhooka z The Things Network |
| `FIREBASE_CREDENTIALS_PATH` | Ścieżka do poświadczeń Firebase (powiadomienia) |
| `JWT_SECRET` | Klucz do podpisywania tokenów JWT (wymagany, bez niego logowanie zwraca błąd 500). Wygeneruj: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Zmiana klucza wylogowuje wszystkich. |
| `SEED_ADMIN_LOGIN` | Login admina tworzonego przez `python -m app.seed` (domyślnie `admin`) |
| `SEED_ADMIN_PASSWORD` | Hasło tego admina. Puste = wylosowane i wypisane w konsoli. Konto i tak musi je zmienić przy pierwszym logowaniu |

## Konto admina (seed)

Po `alembic upgrade head` utwórz pierwszego admina:

```bash
docker compose run --rm web python -m app.seed      # w Dockerze
python -m app.seed                                  # bez Dockera
```

Komenda jest bezpieczna do powtarzania: jeśli admin już istnieje, nic nie zmienia. Zaloguj się nim przez `POST /api/v1/auth/login` (lub **Authorize** w Swaggerze), zmień hasło przez `POST /api/v1/auth/change-password`, a potem zakładaj użytkowników przez `POST /api/v1/users`.

## DATABASE_URL: Docker vs lokalnie

- **W Dockerze** compose nadpisuje wartość na `postgresql+asyncpg://detektor:${POSTGRES_PASSWORD}@timescaledb:5432/detektor` – host to nazwa serwisu, nie `localhost`.
- **Bez Dockera** ustaw w `.env`: `postgresql+asyncpg://detektor:<hasło>@localhost:5432/detektor`.

Przedrostek `+asyncpg` jest wymagany, bo używamy async SQLAlchemy.

Nigdy nie commituj `.env`.
