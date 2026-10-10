# Docker

Plik: `backend/docker-compose.yml`.

## Serwisy

| Serwis | Obraz / kontener | Port | Opis |
|---|---|---|---|
| `web` | `detektor-api` / `detektor_api` | 8000 | FastAPI, uvicorn z `--reload`, kod montowany z `backend/` |
| `timescaledb` | `timescale/timescaledb:latest-pg17` | 5432 | PostgreSQL + TimescaleDB, dane w wolumenie `timescaledb` |

`web` startuje dopiero, gdy healthcheck bazy (`pg_isready`) przejdzie.

## Komendy

```bash
docker compose up --build        # start (z przebudowaniem obrazu)
docker compose up -d             # w tle
docker compose logs -f web       # logi API
docker compose ps                # stan i healthcheck
docker compose down              # stop
docker compose down -v           # stop + usunięcie danych bazy
docker compose exec timescaledb psql -U detektor -d detektor
```

## Typowe problemy

- **Brak `POSTGRES_PASSWORD`** – skopiuj `.env.example` do `.env` i uzupełnij.
- **Zmieniłeś hasło, a baza dalej stare** – hasło jest ustawiane przy pierwszym utworzeniu wolumenu; użyj `docker compose down -v`.
- **Port 5432 zajęty** – zatrzymaj lokalnego Postgresa lub zmień mapowanie portu w compose.
- **`docker` nie działa w WSL** – włącz integrację WSL w Docker Desktop.
