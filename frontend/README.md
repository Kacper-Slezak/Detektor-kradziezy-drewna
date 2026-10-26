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

## Lint, testy i build

```bash
npm run lint
npm test              # Vitest, jednorazowo
npm run test:watch    # Vitest, po każdej zmianie
npm run build
```

## Logowanie na mocku

Backend nie ma jeszcze `/auth`, więc domyślnie działa mock z kontami testowymi opisanymi na górze `src/api/mock.ts` (np. `blazej` / `tajne123`). Prawdziwe API: `VITE_USE_MOCK=false`.

## PWA (instalacja na Androidzie)

Przycisk „Zainstaluj aplikację” działa tylko w zbudowanej wersji, nie w `npm run dev`:

```bash
npm run build
npm run preview -- --host 127.0.0.1
```

Przez zwykłe Wi‑Fi (`http://<IP>:4173`) instalacja nie zadziała, bo potrzebne jest HTTPS albo `localhost`. Test na telefonie (przez USB albo localtunnel) i ikony: [docs/frontend/pwa.md](../docs/frontend/pwa.md).

## Struktura

```
frontend/
├── src/
│   ├── api/             # zapytania do backendu, typy, mock logowania
│   ├── components/      # komponenty aplikacji (przełącznik języka, przycisk instalacji)
│   │   └── ui/          # komponenty shadcn/ui
│   ├── lib/             # funkcje pomocnicze
│   ├── locales/         # tłumaczenia pl.json, en.json
│   ├── pages/           # ekrany (logowanie, zmiana hasła)
│   ├── test/            # konfiguracja testów
│   ├── App.tsx
│   ├── i18n.ts          # konfiguracja tłumaczeń
│   └── main.tsx         # punkt wejścia
├── public/              # logo.svg i wygenerowane ikony PWA
├── components.json      # konfiguracja shadcn/ui
├── Dockerfile
├── docker-compose.yml
├── package.json
├── pwa-assets.config.ts # generator ikon PWA
└── vite.config.ts
```
