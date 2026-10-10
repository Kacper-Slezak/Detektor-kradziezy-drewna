# Backend

**Odpowiedzialny:** Kacper

API (FastAPI) + baza TimescaleDB. Pełna dokumentacja: [docs/backend/](../docs/backend/README.md).

## Szybki start (Docker)

```bash
cd backend
cp .env.example .env        # ustaw POSTGRES_PASSWORD
docker compose up --build
curl localhost:8000/health  # {"status":"ok"}
```

Dokumentacja API (Swagger): http://localhost:8000/docs

## Uruchomienie bez Dockera

Wymaga działającej bazy (np. `docker compose up timescaledb`) i odkomentowanego `DATABASE_URL` z `localhost` w `.env`.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Testy i lint

```bash
pytest #Do wykonania w przyszłych tygodniach
ruff check .
```

## Struktura

```
backend/
├── app/            # kod aplikacji (punkt wejścia: app/main.py)
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
