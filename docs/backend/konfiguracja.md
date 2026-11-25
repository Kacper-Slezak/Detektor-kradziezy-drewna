# Konfiguracja

Zmienne trzymamy w `backend/.env` (poza repo). Wzór: `backend/.env.example`.

| Zmienna | Opis |
|---|---|
| `POSTGRES_PASSWORD` | Hasło użytkownika `detektor` w bazie; używane przez compose |
| `DATABASE_URL` | Adres bazy dla aplikacji (sterownik async: `postgresql+asyncpg://`) |
| `INGEST_API_KEY` | Klucz dla `POST /api/v1/ingest`: urządzenia, bramka i symulator wysyłają go w nagłówku `X-Ingest-Key`, bez niego dostają `401`. Pusty = endpoint bez zabezpieczenia, dopuszczalne tylko lokalnie (backend ostrzega przy starcie). Wygeneruj: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Klucz trzymamy tylko w `.env` (nie w repo) |
| `FRAME_AES_KEY` | Klucz AES-128 do odszyfrowania ramek z urządzeń: 32 znaki hex (16 B), ten sam co na płytce. **Ustawiony** = `/ingest` przyjmuje tylko ramki zaszyfrowane (16 B), jawne dostają `422`, także z symulatora i `curl`. **Pusty** = bez szyfrowania, ramki jawne (lokalnie, z symulatorem). Zły klucz → `422`. Wygeneruj: `python -c "import secrets; print(secrets.token_hex(16))"`. Klucz trzymamy tylko w `.env` i na płytce (nie w repo). Opis: [szyfrowanie.md](szyfrowanie.md) |
| `TTN_WEBHOOK_SECRET` | Sekret webhooka z The Things Network |
| `VAPID_PUBLIC_KEY` | Klucz publiczny Web Push (VAPID), base64url. Front pobiera go z `GET /api/v1/push/vapid-public-key` jako `applicationServerKey`. Para kluczy: `python -m tools.generate_vapid_keys` (w kontenerze: `docker compose run --rm web python -m tools.generate_vapid_keys`) albo `npx web-push generate-vapid-keys`. Puste = backend działa bez powiadomień, a `GET /push/vapid-public-key` zwraca `503` |
| `VAPID_PRIVATE_KEY` | Klucz prywatny VAPID z tej samej pary; podpisuje wysyłane pushe. Tylko w `.env`, nigdy we froncie ani w repo. Zmiana pary unieważnia wszystkie subskrypcje |
| `VAPID_SUBJECT` | Kontakt dla usług push przeglądarek, `mailto:adres@…` albo `https://…`. Wszystkie trzy zmienne `VAPID_*` muszą być ustawione, inaczej pushe nie są wysyłane |
| `JWT_SECRET` | Klucz do podpisywania tokenów JWT (wymagany, bez niego logowanie zwraca błąd 500). Wygeneruj: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Zmiana klucza wylogowuje wszystkich. |
| `SEED_ADMIN_LOGIN` | Login admina tworzonego przez `python -m app.seed` (domyślnie `admin`) |
| `SEED_ADMIN_PASSWORD` | Hasło tego admina. Puste = wylosowane i wypisane w konsoli. Konto i tak musi je zmienić przy pierwszym logowaniu |
| `SEED_DEMO_PASSWORD` | Wspólne hasło kont demo z `python -m app.seed --demo` (domyślnie `demo-haslo-1`). Konta demo nie muszą zmieniać hasła, więc **nie używaj `--demo` na serwerze z prawdziwymi danymi** |
| `LOGIN_MAX_FAILURES` | Ile nieudanych logowań na jeden login w oknie `LOGIN_WINDOW_S`, zanim kolejne próby dostaną `429` (domyślnie `5`) |
| `LOGIN_WINDOW_S` | Okno liczenia nieudanych logowań w sekundach (domyślnie `900`, czyli 15 min). Liczniki są w pamięci backendu: restart je zeruje |
| `SENSOR_SILENT_AFTER_H` | Po ilu godzinach bez żadnej ramki czujnik dostaje stan `silent` (domyślnie `12`, heartbeat leci co ~6 h) |
| `BATTERY_LOW_PCT` | Poniżej tylu % bateria jest słaba i leśniczy dostaje push `low_battery` (domyślnie `20`, ten sam próg co na mapie) |
| `NOTIFY_CHECK_INTERVAL_S` | Co ile sekund backend sprawdza czujniki bez kontaktu i zakończone wydania, żeby wysłać push `silent` / `release_ended` (domyślnie `300`) |
| `RELEASE_DEFAULT_HOURS` | Długość wydania drewna (wyciszenia), gdy apka nie poda końca (domyślnie `4`) |
| `RELEASE_MAX_HOURS` | Najdłuższe dopuszczalne wydanie w godzinach (domyślnie `24`); dłuższe → `422` |
| `BOOT_ID_REQUIRED` | `true` przyjmuje tylko BOOT z `boot_id` (ramka wersji 2), inny → `422`. Włącz, gdy wszystkie płytki go wysyłają ([boot-id.md](boot-id.md)); domyślnie `false` |

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
