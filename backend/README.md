# Backend

**Odpowiedzialny:** Kacper

API (FastAPI) + baza TimescaleDB. Pełna dokumentacja: [docs/backend/](../docs/backend/README.md).
Jak przetestować całość (frontend, symulator, płytka, baza): [docs/testowanie.md](../docs/testowanie.md).

## Szybki start (Docker)

```bash
cd backend
cp -n .env.example .env     # -n: nie nadpisze istniejącego .env; ustaw POSTGRES_PASSWORD i JWT_SECRET
docker compose up --build
docker compose run --rm web alembic upgrade head   # schemat bazy (przy pierwszym uruchomieniu i po zmianach)
docker compose run --rm web python -m app.seed     # konto admina (JWT_SECRET musi być w .env)
curl localhost:8000/health  # {"status":"ok"}
```

Dokumentacja API (Swagger): http://localhost:8000/docs

## Dane demo i wirtualne czujniki

Żeby mapa i panel nie były puste bez sprzętu:

```bash
docker compose run --rm web alembic upgrade head               # najpierw tabele (świeża baza / po zmianach)
docker compose run --rm web python -m app.seed --demo          # konta demo + 10 czujników + historia 7 dni
docker compose run --rm web python -m app.seed --demo --reset  # od nowa (stany "starzeją się" po kilku godzinach)
```

| login | rola | leśnictwo |
|---|---|---|
| `blazej` | leśniczy | Dąbrowa (7 czujników) |
| `ola` | leśniczy | Olszyny (3 czujniki) |
| `bogdan` | nadleśniczy | wszystkie |

Hasło wszystkich kont demo: `demo-haslo-1` (zmiana: `SEED_DEMO_PASSWORD` w `.env`). Czujniki demo mają ID `70B3D57ED00D....` i pokrywają każdy stan: ok, alarm, wyciszony (trwa wydanie), milczy, niska bateria, wyłączony, niezamontowany. Historia (heartbeaty, alarmy z odpowiedziami, wydania) przechodzi przez `/ingest`, tak jak prawdziwe ramki.

Symulator wysyła ramki na żywo, spakowane jak w firmware ([tools/simulator.py](tools/simulator.py)):

```bash
docker compose --profile sim up simulator                       # czujniki demo, heartbeat co 30 s, czasem kradzież
docker compose run --rm simulator --scenario theft --target 70B3D57ED00D0009
docker compose run --rm simulator --scenario battery-drain --interval 5
```

Scenariusze: `normal`, `theft`, `false-alarm`, `battery-drain`, `silent`, `duplicate`. Wszystkie opcje: `docker compose run --rm simulator --help`. Liczniki czujników są zapisywane w `backend/.simulator-state.json` (poza repo).

## Uruchomienie bez Dockera

Wymaga działającej bazy (np. `docker compose up timescaledb`) i odkomentowanego `DATABASE_URL` z `localhost` w `.env`.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

## Testy i lint

```bash
pytest                                           # testy
pytest --cov=app --cov-report=term-missing       # testy + pokrycie (brakujące linie)
pytest --junitxml=reports/junit.xml              # raport XML (np. dla CI)
ruff check .
```

W kontenerze (po `docker compose build web`):

```bash
docker compose run --rm web pytest --cov=app --cov-report=term-missing
docker compose run --rm web ruff check app tests tools
```

Kod jest montowany z `backend/`, więc po zmianie plików `.py` nie trzeba przebudowywać obrazu. Przebudowa (`docker compose build web`) jest potrzebna tylko po zmianie `requirements.txt`.

## Struktura

```
backend/
├── app/            # kod aplikacji (punkt wejścia: app/main.py)
├── tools/          # narzędzia deweloperskie (symulator czujników)
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
