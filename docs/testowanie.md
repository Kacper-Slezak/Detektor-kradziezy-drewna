# Testowanie całego systemu

Uruchomienie backendu i frontendu, wysyłanie ramek (symulator, `curl`, płytka LoPy przez Wi-Fi) oraz sprawdzanie wyniku w bazie, w API i na mapie.

Komendy `docker compose` wykonuje się w folderze, którego dotyczą: `backend/` albo `frontend/`.

## Zakres

| Ścieżka | Stan |
|---|---|
| ramka → `POST /api/v1/ingest` → baza (`messages`, `alarms`, stan czujnika) | działa |
| symulator czujników → backend → mapa | działa |
| LoPy przez Wi-Fi → backend (bez TTN) | działa, skrypt [firmware/przyklady/wyslij_wifi.py](../firmware/przyklady/wyslij_wifi.py) |
| logowanie, konta, rejestracja czujników w panelu admina, mapa | działa |
| lista alarmów i odpowiedź leśniczego | API gotowe (`/api/v1/alarms`), brak widoku w aplikacji; alarm widoczny jako czerwona pinezka |
| montaż czujnika (lokalizacja z telefonu), wydania drewna | brak; montaż można zastąpić zapytaniem SQL ([sekcja 6](#6-płytka-lopy-przez-wi-fi)) |
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

Liczniki czujników są zapisywane w `backend/.simulator-state.json` (plik poza repozytorium). Po `seed --demo --reset` plik nie przeszkadza, bo symulator zawsze zaczyna od ramki BOOT.

## 4. Ręczne wysyłanie ramek

Endpoint `POST /api/v1/ingest` jest wspólny dla symulatora, płytki i testów ręcznych:

```bash
curl -X POST localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"device": "70B3D57ED00D0008", "payload_hex": "1200FF5A0000"}'
```

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

Płytka i laptop muszą być w jednej sieci. Sieci uczelniane (eduroam) zwykle blokują ruch między urządzeniami, dlatego zalecany jest hotspot z telefonu.

Konfiguracja laptopa (Windows + WSL + Docker Desktop):

1. Adres IP laptopa: `ipconfig` w PowerShellu, adres IPv4 karty Wi-Fi (np. `192.168.43.20`).
2. Reguła zapory (jednorazowo, PowerShell jako administrator):
   ```powershell
   New-NetFirewallRule -DisplayName "Detektor API 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
   ```
   Sieć hotspotu musi mieć w Windows profil **prywatny**.
3. Kontrola: `http://<IP laptopa>:8000/health` otwarty na telefonie w tej samej sieci zwraca `{"status":"ok"}`. Bez tego płytka również nie połączy się z backendem.

### Uruchomienie na płytce

1. W skrypcie ustawić `WIFI_SSID`, `WIFI_HASLO`, `API_HOST` (IP laptopa) i `DEVICE_ID`.
2. Wgrać i uruchomić: Pymakr (*Upload*, *Run*) albo w REPL `exec(open('wyslij_wifi.py').read())`.
3. Oczekiwane odpowiedzi w konsoli płytki: `201 {"status":"stored", ...}`, przy pierwszym alarmie `"alarm_created":true`.
4. Wynik w bazie: [sekcja 5](#5-sprawdzanie-zapisu), na mapie: [sekcja 2](#2-frontend).

Ten sam skrypt uruchomiony zwykłym Pythonem na laptopie (`python firmware/przyklady/wyslij_wifi.py`) wysyła ramki na `localhost`, co pozwala oddzielić problemy sieci od problemów backendu.

### Własne ID płytki

DevEUI płytki (REPL):

```python
from network import LoRa; import ubinascii; print(ubinascii.hexlify(LoRa().mac()).upper())
```

Czujnik z tym ID rejestruje się w panelu admina (Czujniki → Dodaj czujnik). Nowy czujnik jest nieaktywny i bez lokalizacji. Do czasu wprowadzenia montażu (`PUT /api/v1/sensors/{id}/mount`) lokalizację i włączenie ustawia się w bazie:

```sql
UPDATE sensors SET lat = 50.0647, lon = 20.3105, active = true, name = 'Czujnik testowy'
WHERE id = '<DevEUI>';
```

## 7. Telefon

Dostęp do aplikacji z telefonu (localtunnel albo USB): [docs/frontend/pwa.md](frontend/pwa.md). Tunel obejmuje tylko port frontendu, zapytania `/api` przechodzą przez proxy Vite.

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
| `/ingest` zwraca 404 | brak czujnika w bazie | `seed --demo` albo rejestracja w panelu admina |
| mapa nie pokazuje nowego alarmu | odświeżanie co 60 s albo konto z innego leśnictwa | odczekać lub F5; konto właściwego leśnictwa |
| tabela czujników w panelu się nie zmienia | panel nie odświeża się automatycznie | F5 |
| frontend: błąd sieci, `/api` zwraca 502 | backend nie działa | `docker compose ps` w `backend/` |
| nietypowe stany czujników demo po kilku godzinach | dane demo liczone od chwili seeda | `seed --demo --reset` |
| `curl localhost:8000/health` działa przy zatrzymanym kontenerze | port 8000 zajęty przez lokalny `uvicorn` | `ss -ltnp \| grep 8000`, zatrzymać proces |
| płytka nie łączy się z backendem | inna sieć, zapora, izolacja klientów w sieci | test `/health` z telefonu; reguła zapory; hotspot |
| `docker` nie istnieje w WSL | brak integracji WSL | Docker Desktop → Settings → Resources → WSL integration |
