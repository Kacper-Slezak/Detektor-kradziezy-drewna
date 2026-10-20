# Docker

Plik: `frontend/docker-compose.yml`.

## Serwisy

| Serwis | Obraz / kontener | Port | Opis |
|---|---|---|---|
| `web` | `detektor-frontend` / `detektor_frontend` | 5173 | serwer deweloperski Vite, kod montowany z `frontend/` |

Zapytania na `/api/...` Vite przekazuje do backendu na `http://host.docker.internal:8000`, czyli do API uruchomionego z `backend/docker-compose.yml`. Backend trzeba uruchomić osobno.

## Komendy

```bash
docker compose up --build        # start (z przebudowaniem obrazu)
docker compose up -d             # w tle
docker compose logs -f web       # logi Vite
docker compose down              # stop
docker compose build --no-cache  # po zmianie package.json (nowe paczki)
```

## Zmienne środowiskowe

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `API_TARGET` | `http://localhost:8000` (bez Dockera) | adres backendu dla proxy `/api` |
| `CHOKIDAR_USEPOLLING` | `true` w compose | wykrywanie zmian plików odpytywaniem (potrzebne na Windowsie) |

## Typowe problemy

- **`/api/...` zwraca 502** – backend nie działa; uruchom `docker compose up` w `backend/`.
- **Zmiany w kodzie nie odświeżają strony** – sprawdź, czy w compose jest `CHOKIDAR_USEPOLLING: "true"`.
- **Nowa paczka z npm nie działa w kontenerze** – `node_modules` są w obrazie, więc po `npm install` przebuduj: `docker compose up --build`.
- **Port 5173 zajęty** – zatrzymaj lokalne `npm run dev` lub zmień mapowanie portu w compose.
- **`npm` w PowerShellu: „running scripts is disabled”** – użyj `npm.cmd` albo raz wykonaj `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
