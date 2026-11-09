# Testowanie całego systemu

Uruchomienie backendu i frontendu, wysyłanie ramek (symulator, `curl`, płytka LoPy przez Wi-Fi) oraz sprawdzanie wyniku w bazie, w API i na mapie.

Komendy `docker compose` wykonuje się w folderze, którego dotyczą: `backend/` albo `frontend/`.

## Zakres

| Ścieżka | Stan |
|---|---|
| ramka → `POST /api/v1/ingest` → baza (`messages`, `alarms`, stan czujnika) | działa |
| symulator czujników → backend → mapa | działa |
| LoPy przez Wi-Fi → backend (bez TTN) | działa w tej samej sieci, przez tunel HTTPS (Cloudflare) i przez tunel TCP (bore), skrypt [firmware/przyklady/wyslij_wifi.py](../firmware/przyklady/wyslij_wifi.py) |
| logowanie, konta, rejestracja czujników w panelu admina, mapa | działa |
| lista alarmów i odpowiedź leśniczego | API gotowe (`/api/v1/alarms`), brak widoku w aplikacji; alarm widoczny jako czerwona pinezka |
| montaż czujnika, wydania drewna | API gotowe (`PUT /api/v1/sensors/{id}/mount`, `/api/v1/sensors/{id}/releases`, `/api/v1/releases`), widoki w aplikacji w przygotowaniu; do tego czasu Swagger |
| LoPy → TTN → webhook → backend | brak adaptera `/ingest/ttn` |
| powiadomienia push | brak |

## 1. Backend

```bash
cd backend
cp -n .env.example .env                                   # -n nie nadpisuje istniejącego .env
docker compose up -d --build
docker compose run --rm web alembic upgrade head          # tabele: przy nowej bazie i po każdej nowej migracji
docker compose run --rm web python -m app.seed --demo     # admin, konta demo, 10 czujników z historią 7 dni
curl localhost:8000/health                                # {"status":"ok"}
```

Klucz dla `/ingest` (`INGEST_API_KEY` w `.env`, opis: [konfiguracja.md](backend/konfiguracja.md)): bez niego endpoint jest otwarty, co wystarcza tylko lokalnie. Przy wystawianiu backendu przez tunel klucz jest obowiązkowy:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"   # wynik wpisać w .env jako INGEST_API_KEY=...
docker compose up -d                                             # backend wczytuje nowy .env
```

- W `.env` muszą być ustawione `POSTGRES_PASSWORD` i `JWT_SECRET`. Zmiana `POSTGRES_PASSWORD` po utworzeniu bazy wymaga `docker compose down -v` (kasuje dane), bo hasło zapisuje się w wolumenie przy pierwszym starcie.
- Hasło admina: z `SEED_ADMIN_PASSWORD` w `.env`, a bez niego losowe, wypisane przez seed. Przy pierwszym logowaniu trzeba je zmienić.
- Konta demo, hasło `demo-haslo-1`:

  | Login | Rola | Zakres |
  |---|---|---|
  | `blazej` | leśniczy | Leśnictwo Dąbrowa (7 czujników) |
  | `ola` | leśniczy | Leśnictwo Olszyny (3 czujniki) |
  | `bogdan` | nadleśniczy | wszystkie czujniki |

- Stany czujników demo są liczone od chwili uruchomienia seeda, po kilku godzinach się zmieniają (np. `ok` → `silent`). Odświeżenie danych demo: `docker compose run --rm web python -m app.seed --demo --reset`.
- Swagger: http://localhost:8000/docs. Endpointy wymagające logowania: token z `POST /api/v1/auth/login` wklejony w **Authorize**.

## 2. Frontend

```bash
cd frontend
docker compose up -d --build
```

Aplikacja: http://localhost:5173. Zapytania `/api` przechodzą przez proxy Vite do backendu na porcie 8000.

| Konto | Ekran po zalogowaniu |
|---|---|
| leśniczy (`blazej`, `ola`) | mapa czujników własnego leśnictwa |
| nadleśniczy (`bogdan`) | mapa wszystkich czujników |
| `admin` | panel z menu bocznym: Użytkownicy, Czujniki (na wąskim ekranie menu pod ☰) |

Tabela czujników i rejestracja nowych czujników są tylko w panelu admina. Leśniczy i nadleśniczy nie mają dostępu do panelu.

Kolory pinezek:

| Kolor | Stan | Znaczenie |
|---|---|---|
| zielony | `ok` | czujnik działa |
| niebieski | `muted` | trwa wydanie drewna, alarmy wyłączone |
| czerwony, pulsujący | `alarm` | otwarty alarm bez odpowiedzi |
| żółty | `silent` | brak ramki od ponad 12 h |
| szary | `inactive` | czujnik wyłączony |

Czujniki bez lokalizacji nie mają pinezki, są liczone w legendzie jako „do montażu”.

Odświeżanie danych:

| Ekran | Odświeżanie |
|---|---|
| mapa | automatycznie co 60 s |
| panel admina (czujniki, konta) | tylko po przeładowaniu strony (F5) albo zmianie sekcji |

Praca bez backendu: `VITE_USE_MOCK=true`, opis w [frontend/README.md](../frontend/README.md).

## 3. Symulator czujników

Symulator wysyła ramki w formacie firmware: BOOT przy starcie, heartbeaty co `--interval` sekund, w scenariuszach alarmy (3 ramki, jak z urządzenia).

```bash
cd backend
docker compose --profile sim up simulator      # czujniki demo, heartbeat co 30 s, losowe kradzieże; Ctrl+C kończy
docker compose run --rm simulator --help       # wszystkie opcje
```

Scenariusze:

| Komenda | Konto do sprawdzenia | Oczekiwany efekt |
|---|---|---|
| `docker compose run --rm simulator --scenario theft --target 70B3D57ED00D0009 --once` | `ola` | „Skład na Kopcu” zmienia kolor na czerwony; w logu symulatora `NOWY ALARM #…` i dwa razy `powtórzenie alarmu` |
| `docker compose run --rm simulator --scenario false-alarm --target 70B3D57ED00D0008 --once` | `ola` | alarm z samych wibracji, w `GET /api/v1/alarms` pole `possible_tampering: true` |
| `docker compose run --rm simulator --scenario battery-drain --target 70B3D57ED00D0008 --interval 5` | `ola` | bateria w dymku pinezki spada o 5 pkt co 5 s, poniżej 20% wyświetlana na czerwono |
| `docker compose run --rm simulator --scenario duplicate --once` | – | w logu `duplicate`: backend odrzuca drugą kopię ramki |
| `docker compose run --rm simulator --scenario theft --target 70B3D57ED00D0003 --once` | `blazej` | czujnik z trwającym wydaniem zostaje niebieski; w logu `alarm pominięty (wyciszony/wyłączony)`, ramka zapisana bez alarmu |

Wydanie drewna na dowolnym czujniku (Swagger, konto leśniczego):

1. `POST /api/v1/sensors/70B3D57ED00D0009/releases` z body `{}` (jako `ola`): wydanie na 4 h, pinezka zmienia kolor na niebieski.
2. `docker compose run --rm simulator --scenario theft --target 70B3D57ED00D0009 --once`: w logu `alarm pominięty (wyciszony/wyłączony)`.
3. `POST /api/v1/releases/{id}/end`: koniec wydania; kolejny `theft` tworzy alarm.

Liczniki czujników są zapisywane w `backend/.simulator-state.json` (plik poza repozytorium). Po `seed --demo --reset` plik nie przeszkadza, bo symulator zawsze zaczyna od ramki BOOT.

## 4. Ręczne wysyłanie ramek

Endpoint `POST /api/v1/ingest` jest wspólny dla symulatora, płytki i testów ręcznych. Gdy w `backend/.env` jest ustawiony `INGEST_API_KEY`, każde zapytanie musi mieć nagłówek `X-Ingest-Key` z tym kluczem (bez niego: `401`). Przy pustym `INGEST_API_KEY` nagłówek nie jest wymagany.

```bash
curl -X POST localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -H "X-Ingest-Key: <INGEST_API_KEY>" \
  -d '{"device": "70B3D57ED00D0008", "payload_hex": "1200FF5A0000"}'
```

W Swaggerze klucz wpisuje się w **Authorize** → `APIKeyHeader (X-Ingest-Key)`. Symulator bierze klucz z `INGEST_API_KEY` w `.env` (serwis `simulator` czyta ten plik) albo z opcji `--ingest-key`.

`payload_hex` to ramka z protokołu zapisana szesnastkowo. Przykłady:

| Ramka | Zawartość |
|---|---|
| `130001010158` | BOOT, licznik 1, firmware 1, zwykłe włączenie, bateria 88% |
| `1200FF5A0000` | HEARTBEAT, licznik 255, bateria 90% |
| `11002A0101570028B440` | ALARM, licznik 42, mikrofon, pewność 87, 40 s, bateria 64% |

Złożenie własnej ramki koderem backendu:

```bash
docker compose run --rm web python -c "from app.protocol.encoder import encode_alarm; print(encode_alarm(300, sources=['microphone','vibration'], confidence=95, duration_s=120, energy=220, battery_pct=70).hex())"
```

Odczytanie ramki dekoderem:

```bash
docker compose run --rm web python -c "from app.protocol.decoder import decode_hex, to_dict; print(to_dict(decode_hex('11002A0101570028B440')))"
```

Odpowiedzi `/ingest`:

| Kod | `status` / `detail` | Znaczenie |
|---|---|---|
| 201 | `stored` | zapisane; przy ALARM `alarm_created: true` (nowy alarm) albo `false` (doklejony do otwartego alarmu z ostatnich 10 min) |
| 201 | `stored`, `muted: true` | czujnik wyłączony albo trwa wydanie: ramka zapisana, alarm nie powstaje |
| 200 | `duplicate` | licznik nie większy niż ostatni zapisany dla czujnika; nic nie zapisano |
| 401 | `Brak lub zły klucz X-Ingest-Key` | ustawiony `INGEST_API_KEY`, a nagłówka brak albo klucz się nie zgadza |
| 404 | `Nieznany czujnik` | brak czujnika o tym ID w bazie |
| 422 | `Błędna ramka: …` | zła długość, wersja, typ albo wartość procentowa > 100 |

Licznik musi rosnąć. Ramka z licznikiem mniejszym lub równym ostatniemu jest traktowana jako duplikat. Wyjątek: po ramce BOOT backend przyjmuje licznik od nowa.

## 5. Sprawdzanie zapisu

Konsola bazy:

```bash
cd backend
docker compose exec timescaledb psql -U detektor -d detektor
```

Zapytania (wyjście z `psql`: `\q`):

```sql
-- ostatnie ramki
SELECT received_at, sensor_id, msg_type, counter, payload_hex, rssi
FROM messages ORDER BY received_at DESC LIMIT 10;

-- ostatnie alarmy (repeats = liczba scalonych ramek)
SELECT id, sensor_id, started_at, repeats, confidence, sources, status
FROM alarms ORDER BY started_at DESC LIMIT 10;

-- stan czujnika
SELECT id, name, battery_pct, last_seen, last_counter, active
FROM sensors WHERE id = '70B3D57ED00D0009';

-- zdekodowana zawartość ramek
SELECT received_at, decoded FROM messages
WHERE sensor_id = '70B3D57ED00D0009' ORDER BY received_at DESC LIMIT 3;

-- liczba ramek z każdego czujnika
SELECT sensor_id, count(*) AS ramek, max(received_at) AS ostatnia
FROM messages GROUP BY sensor_id ORDER BY sensor_id;
```

Pojedyncze zapytanie bez wchodzenia do konsoli:

```bash
docker compose exec timescaledb psql -U detektor -d detektor -c "SELECT * FROM messages ORDER BY received_at DESC LIMIT 5;"
```

Logi backendu (duplikaty, zgubione ramki, pominięte alarmy, błędne ramki):

```bash
docker compose logs -f web
```

W API: `GET /api/v1/sensors/{id}` zwraca stan, baterię, `last_seen` oraz ostatnie alarmy i wydania czujnika.

## 6. Płytka LoPy przez Wi-Fi

Test sprzętu bez TTN: LoPy łączy się z Wi-Fi i wysyła ramki na `POST /api/v1/ingest`, tak jak `curl` w sekcji 4. Skrypt [firmware/przyklady/wyslij_wifi.py](../firmware/przyklady/wyslij_wifi.py) wysyła BOOT, HEARTBEAT i 3 ramki ALARM, a w konsoli wypisuje odpowiedzi backendu.

### Sieć

Płytka musi dosięgnąć backendu. Adres ustawia się w `API_URL` w skrypcie. Są trzy sposoby:

| Sposób | `API_URL` | Kiedy |
|---|---|---|
| A. tunel Cloudflare (zalecany) | `https://<losowa-nazwa>.trycloudflare.com` | płytka w dowolnej sieci z internetem (hotspot, eduroam); bez konfiguracji Windows |
| B. ta sama sieć | `http://<IP laptopa>:8000` | gdy TLS na płytce nie działa albo nie ma internetu; laptop i płytka w jednej sieci |
| C. tunel bore (TCP, bez TLS) | `http://bore.pub:<port>` | gdy TLS na płytce nie działa (np. `MBEDTLS_ERR_SSL_ALLOC_FAILED`), a płytka i laptop są w różnych sieciach |

#### A. Tunel Cloudflare (quick tunnel)

Quick tunnel daje tymczasowy publiczny adres HTTPS prowadzący do backendu na laptopie. Nie wymaga konta ani hasła (w przeciwieństwie do localtunnel). Adres zmienia się przy każdym uruchomieniu, a tunel działa, dopóki działa komenda.

1. Klucz `INGEST_API_KEY` ustawiony w `backend/.env` ([sekcja 1](#1-backend)). Tunel wystawia `/ingest` do internetu.
2. Tunel (osobny terminal, Docker, bez instalacji):
   ```bash
   docker run --rm --network host cloudflare/cloudflared:2025.10.0 tunnel --no-autoupdate --url http://127.0.0.1:8000
   ```
   W logu pojawi się adres, np. `https://oct-commitment-vital-satellite.trycloudflare.com`.
3. Kontrola z laptopa (ten sam skrypt, zwykły Python):
   ```bash
   python3 firmware/przyklady/wyslij_wifi.py https://<adres>.trycloudflare.com <INGEST_API_KEY>
   ```
   Oczekiwane: pięć linii `-> 201`.

Skrypt na płytce łączy się po TLS z SNI (`ussl.wrap_socket(..., server_hostname=...)`), bez sprawdzania certyfikatu (brak pliku CA na płytce). Połączenie jest szyfrowane, więc klucz nie idzie otwartym tekstem.

#### B. Ta sama sieć

Sieci uczelniane (eduroam) zwykle blokują ruch między urządzeniami, dlatego zalecany jest hotspot z telefonu.

Konfiguracja laptopa (Windows + WSL + Docker Desktop):

1. Adres IP laptopa: `ipconfig` w PowerShellu, adres IPv4 karty Wi-Fi (np. `192.168.43.20`).
2. Reguła zapory (jednorazowo, PowerShell jako administrator):
   ```powershell
   New-NetFirewallRule -DisplayName "Detektor API 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
   ```
   Sieć hotspotu musi mieć w Windows profil **prywatny**.
3. Kontrola: `http://<IP laptopa>:8000/health` otwarty na telefonie w tej samej sieci zwraca `{"status":"ok"}`. Bez tego płytka również nie połączy się z backendem.

#### C. Tunel bore (bez TLS)

[bore](https://github.com/ekzhang/bore) przekazuje zwykły TCP przez publiczny serwer `bore.pub`, bez konta. Płytka łączy się po zwykłym HTTP, więc TLS na płytce nie jest potrzebny. Port zmienia się przy każdym uruchomieniu.

Ruch nie jest szyfrowany: ramki i `X-Ingest-Key` idą otwartym tekstem przez cudzy serwer. Tylko do testów, z osobnym kluczem testowym w `INGEST_API_KEY`, zmienionym po testach.

1. Tunel (osobny terminal, Docker, bez instalacji):
   ```bash
   docker run --rm -it --init --network host ekzhang/bore:0.6.0 local 8000 --local-host 127.0.0.1 --to bore.pub
   ```
   W logu pojawi się adres, np. `listening at bore.pub:41235`.
2. Kontrola z laptopa:
   ```bash
   python3 firmware/przyklady/wyslij_wifi.py http://bore.pub:41235 <INGEST_API_KEY>
   ```
3. Na płytce `API_URL = "http://bore.pub:41235"`.

### Uruchomienie na płytce

1. W skrypcie ustawić `WIFI_SSID`, `WIFI_HASLO`, `API_URL` (adres tunelu albo `http://<IP laptopa>:8000`), `DEVICE_ID` i `INGEST_KEY` (wartość `INGEST_API_KEY` z `backend/.env`, pusty, gdy backend działa bez klucza).
2. Wgrać i uruchomić: Pymakr (*Upload*, *Run*) albo w REPL `exec(open('wyslij_wifi.py').read())`.
3. Oczekiwane odpowiedzi w konsoli płytki: `201 {"status":"stored", ...}`, przy pierwszym alarmie `"alarm_created":true`.
4. Wynik w bazie: [sekcja 5](#5-sprawdzanie-zapisu), na mapie: [sekcja 2](#2-frontend).

Ten sam skrypt uruchomiony zwykłym Pythonem na laptopie wysyła ramki na podany adres (domyślnie `http://127.0.0.1:8000`), co pozwala oddzielić problemy sieci i płytki od problemów backendu:

```bash
python3 firmware/przyklady/wyslij_wifi.py                                  # lokalny backend, bez klucza
python3 firmware/przyklady/wyslij_wifi.py http://127.0.0.1:8000 <klucz>
python3 firmware/przyklady/wyslij_wifi.py https://<adres>.trycloudflare.com <klucz>
```

### Własne ID płytki

DevEUI płytki (REPL):

```python
from network import LoRa; import ubinascii; print(ubinascii.hexlify(LoRa().mac()).upper())
```

Czujnik z tym ID rejestruje się w panelu admina (Czujniki → Dodaj czujnik). Nowy czujnik jest nieaktywny i bez lokalizacji. Montaż (nazwa, lokalizacja, włączenie) robi leśniczy tego leśnictwa albo admin; do czasu ekranu montażu w aplikacji przez Swagger, `PUT /api/v1/sensors/{id}/mount`:

```json
{ "name": "Czujnik testowy", "lat": 50.0647, "lon": 20.3105 }
```

Po montażu czujnik ma pinezkę na mapie (stan `silent` do pierwszej ramki).

## 7. Telefon

Dostęp do aplikacji z telefonu (tunel Cloudflare, localtunnel albo USB): [docs/frontend/pwa.md](frontend/pwa.md). Tunel obejmuje tylko port frontendu, zapytania `/api` przechodzą przez proxy Vite. Do płytki służy osobny tunel na port backendu ([sekcja 6](#6-płytka-lopy-przez-wi-fi)).

## 8. Testy automatyczne

```bash
cd backend
docker compose run --rm web pytest                                    # SQLite w pamięci, baza z Dockera niepotrzebna
docker compose run --rm web pytest --cov=app --cov-report=term-missing
docker compose run --rm web ruff check app tests tools

cd ../frontend
docker compose run --rm web npm test
docker compose run --rm web npm run lint
```

Kod jest montowany do kontenerów, zmiany w plikach nie wymagają przebudowy obrazu. Przebudowa jest potrzebna po zmianie zależności:

| Zmiana | Komenda |
|---|---|
| `backend/requirements.txt` | `docker compose up -d --build` |
| `frontend/package.json` | `docker compose up -d --build --renew-anon-volumes` (paczki są w osobnym wolumenie, który przetrwa samo `--build`) |

## 9. Typowe problemy

| Objaw | Przyczyna | Rozwiązanie |
|---|---|---|
| `relation "ranges" does not exist`, symulator dostaje 500 | baza bez tabel | `docker compose run --rm web alembic upgrade head` |
| `password authentication failed for user "detektor"` | hasło w `.env` inne niż przy tworzeniu wolumenu (np. `.env` nadpisany przez `cp`) | przywrócić poprzednie hasło albo `docker compose down -v` (kasuje dane) |
| `Failed to resolve import "leaflet/..."` (albo innej paczki) we frontendzie | stare `node_modules` w wolumenie kontenera | `docker compose up -d --build --renew-anon-volumes` w `frontend/` |
| brak hasła admina | hasło wypisane tylko przy pierwszym seedzie | `SEED_ADMIN_PASSWORD` w `.env` i nowa baza (`down -v`) albo reset hasła w bazie |
| brak tabeli czujników po zalogowaniu | konto nie jest adminem | logowanie jako `admin` |
| `/ingest` zwraca `duplicate` dla każdej ramki | licznik nie rośnie | ramka BOOT przed pozostałymi albo większy licznik |
| `/ingest` zwraca 401 | brak nagłówka `X-Ingest-Key` albo inny klucz niż `INGEST_API_KEY` w `backend/.env` | nagłówek z kluczem; w symulatorze `INGEST_API_KEY` w `.env` albo `--ingest-key`; na płytce `INGEST_KEY`; po zmianie `.env`: `docker compose up -d` |
| wydanie (`POST …/releases`) zwraca 409 | czujnik niezamontowany albo wydanie dla niego już trwa (`id` w `detail`) | montaż przez `PUT /api/v1/sensors/{id}/mount`; trwające wydanie zakończyć `POST /api/v1/releases/{id}/end` |
| `/ingest` zwraca 404 | brak czujnika w bazie | `seed --demo` albo rejestracja w panelu admina |
| mapa nie pokazuje nowego alarmu | odświeżanie co 60 s albo konto z innego leśnictwa | odczekać lub F5; konto właściwego leśnictwa |
| tabela czujników w panelu się nie zmienia | panel nie odświeża się automatycznie | F5 |
| frontend: błąd sieci, `/api` zwraca 502 | backend nie działa | `docker compose ps` w `backend/` |
| nietypowe stany czujników demo po kilku godzinach | dane demo liczone od chwili seeda | `seed --demo --reset` |
| `curl localhost:8000/health` działa przy zatrzymanym kontenerze | port 8000 zajęty przez lokalny `uvicorn` | `ss -ltnp \| grep 8000`, zatrzymać proces |
| płytka nie łączy się z backendem (`http://IP:8000`) | inna sieć, zapora, izolacja klientów w sieci | test `/health` z telefonu; reguła zapory; hotspot albo tunel |
| skrypt przez tunel: `Connection refused`, 502 albo 530 | tunel zamknięty, nieaktualny adres albo backend nie działa | uruchomić tunel ponownie i wziąć nowy adres z logu; `curl localhost:8000/health` |
| płytka: `TypeError` przy `wrap_socket` albo `OSError` przy `connect` po `https://` | stary firmware Pycom (brak SNI, stary mbedTLS) | aktualizacja firmware (Pycom Firmware Updater); wersja: `import os; os.uname()` w REPL; awaryjnie sposób C albo B (`http://`) |
| płytka: `MemoryError` albo `MBEDTLS_ERR_SSL_ALLOC_FAILED` przy `https://` | za mało RAM na bufory TLS (mbedTLS, ok. 40–50 KB) | uruchomić skrypt zaraz po resecie, bez innego kodu w `main.py`; jeśli dalej to samo: sposób C (bore) albo B, oba bez TLS |
| `docker` nie istnieje w WSL | brak integracji WSL | Docker Desktop → Settings → Resources → WSL integration |
