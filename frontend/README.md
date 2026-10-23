# Frontend

**Odpowiedzialny:** Agata

Aplikacja webowa (React + TypeScript), docelowo PWA na Androida. Pełna dokumentacja: [docs/frontend/](../docs/frontend/README.md).

## Szybki start (Docker)

```bash
cd frontend
docker compose up --build
```

Aplikacja: http://localhost:5173. Zapytania `/api/...` idą do backendu na porcie 8000 (uruchom go osobno z `backend/`).

## Uruchomienie bez Dockera

Wymaga Node.js 22.

```bash
npm install
npm run dev
```

## Lint i build

```bash
npm run lint
npm run build
```

## Struktura

```
frontend/
├── src/
│   ├── components/ui/   # komponenty shadcn/ui
│   ├── lib/             # funkcje pomocnicze
│   ├── App.tsx
│   └── main.tsx         # punkt wejścia
├── public/
├── components.json      # konfiguracja shadcn/ui
├── Dockerfile
├── docker-compose.yml
├── package.json
└── vite.config.ts
```
