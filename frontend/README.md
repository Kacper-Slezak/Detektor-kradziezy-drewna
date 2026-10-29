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

## Backend i mock

Domyślnie front łączy się z backendem: zapytania `/api` idą na `localhost:8000` (uruchomienie backendu: [backend/README.md](../backend/README.md)).

Bez backendu można użyć mocka z kontami testowymi opisanymi na górze `src/api/mock.ts` (np. `admin` / `admin123`, `blazej` / `tajne123`):

```powershell
$env:VITE_USE_MOCK = 'true'   # bash: VITE_USE_MOCK=true npm run dev
npm run dev
```

Flaga jest wpisywana w kod przy budowaniu, więc przy `npm run build` też trzeba ją ustawić przed buildem. Testy (`npm test`) zawsze działają na mocku.

## PWA (instalacja na Androidzie)

Przycisk „Zainstaluj aplikację” działa tylko w zbudowanej wersji, nie w `npm run dev`:

```bash
npm run build
npm run preview -- --host 127.0.0.1
```

Przez zwykłe Wi‑Fi (`http://<IP>:4173`) instalacja nie zadziała, bo potrzebne jest HTTPS albo `localhost`. Test na telefonie (przez USB albo localtunnel) i ikony: [docs/frontend/pwa.md](../docs/frontend/pwa.md).

## Panel admina i motyw

Admin po zalogowaniu trafia do panelu z menu bocznym (w stylu Grafany), gdzie zakłada konta leśniczych. Cała aplikacja ma motyw jasny, ciemny albo systemowy. Szczegóły: [docs/frontend/panel-admina.md](../docs/frontend/panel-admina.md).

## Struktura

```
frontend/
├── src/
│   ├── api/             # zapytania do backendu, typy, mock
│   ├── components/      # komponenty aplikacji (rama panelu admina, formularz konta, przełączniki)
│   │   └── ui/          # komponenty shadcn/ui (sheet.tsx: panel wysuwany z prawej)
│   ├── lib/             # funkcje pomocnicze (motyw, login z nazwiska, hasło tymczasowe)
│   ├── locales/         # tłumaczenia pl.json, en.json
│   ├── pages/           # ekrany (logowanie, zmiana hasła, użytkownicy)
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
