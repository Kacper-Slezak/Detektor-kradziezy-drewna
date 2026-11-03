# Testowanie całego systemu

Jak odpalić backend z frontendem, puścić wirtualne czujniki albo prawdziwą płytkę i sprawdzić, że dane doszły: w bazie, w API i na mapie.

Wszystkie komendy `docker compose` wykonuj w folderze, którego dotyczą (`backend/` albo `frontend/`).

## Co da się dziś przetestować

| Ścieżka | Stan |
|---|---|
| ramka → `POST /api/v1/ingest` → baza (`messages`, `alarms`, stan czujnika) | działa |
| symulator czujników → backend → mapa w apce | działa |
| LoPy przez Wi-Fi → backend (bez TTN) | działa, [przykład](../firmware/przyklady/wyslij_wifi.py) |
| logowanie, konta, czujniki w panelu admina, mapa leśniczego i nadleśniczego | działa |
| lista alarmów i odpowiedź leśniczego | backend: PR #50, w apce jeszcze nie ma widoku (alarm widać jako czerwoną pinezkę) |
| montaż czujnika z telefonu, wydania drewna | jeszcze nie ma (obejście dla montażu w [sekcji 6](#6-test-z-płytki-przez-wi-fi)) |
| LoPy → TTN → webhook → backend | brakuje adaptera `/ingest/ttn` |
| powiadomienia push | jeszcze nie ma |

## 1. Backend

```bash
cd backend
cp .env.example .env     # tylko za pierwszym razem: ustaw POSTGRES_PASSWORD i JWT_SECRET
docker compose up -d --build
docker compose run --rm web alembic upgrade head          # tabele (świeża baza i po każdej nowej migracji)
docker compose run --rm web python -m app.seed --demo     # admin + konta demo + 10 czujników z historią
curl localhost:8000/health                                # {"status":"ok"}
```

- Seed wypisze hasło admina (jeśli nie ustawiłeś `SEED_ADMIN_PASSWORD`). Admin musi je zmienić przy pierwszym logowaniu.
- Konta demo: `blazej` (leśniczy, Dąbrowa), `ola` (leśniczy, Olszyny), `bogdan` (nadleśniczy). Hasło: `demo-haslo-1`.
- Stany czujników demo są liczone od chwili seeda, więc po kilku godzinach się „starzeją” (np. `ok` przechodzi w `silent`). Odświeżenie: `docker compose run --rm web python -m app.seed --demo --reset`.
- Swagger z całym API: http://localhost:8000/docs. Żeby wołać endpointy z logowaniem, zrób `POST /api/v1/auth/login`, skopiuj `token` i wklej go po kliknięciu **Authorize**.

## 2. Frontend

```bash
cd frontend
docker compose up -d --build
```

Apka: http://localhost:5173. Zapytania `/api` idą przez proxy Vite do backendu na porcie 8000, więc backend musi działać.

| Logujesz się jako | Widzisz |
|---|---|
| `blazej` / `ola` | mapa czujników swojego leśnictwa |
| `bogdan` | mapa wszystkich czujników |
| `admin` | panel: konta, czujniki (tabela ze stanami) |

Kolory pinezek: zielony `ok`, niebieski `muted` (trwa wydanie), czerwony pulsujący `alarm`, żółty `silent` (brak kontaktu > 12 h), szary `inactive`. Czujników bez lokalizacji nie ma na mapie, tylko w legendzie jako „do montażu”.

**Mapa odświeża się co 60 s.** Po wysłaniu ramki odczekaj chwilę albo odśwież stronę (F5).

Bez backendu da się pracować na mocku: `VITE_USE_MOCK=true` ([frontend/README.md](../frontend/README.md)).

## 3. Symulator: wirtualne czujniki na żywo

Symulator wysyła ramki tak jak firmware: BOOT na start, potem heartbeaty, a w scenariuszach alarmy (3 ramki, jak z prawdziwego urządzenia).

```bash
cd backend
docker compose --profile sim up simulator           # wszystkie czujniki demo, heartbeat co 30 s, czasem kradzież (Ctrl+C kończy)
docker compose run --rm simulator --help            # wszystkie opcje
```

Scenariusze do sprawdzenia na mapie (zaloguj się jako `ola`, to jej czujniki):

| Komenda | Co powinieneś zobaczyć |
|---|---|
| `docker compose run --rm simulator --scenario theft --target 70B3D57ED00D0009 --once` | „Skład na Kopcu” robi się czerwony; w logu symulatora `NOWY ALARM #…` i dwa razy `powtórzenie alarmu` |
| `docker compose run --rm simulator --scenario false-alarm --target 70B3D57ED00D0008 --once` | alarm z samych wibracji (`possible_tampering: true` w `GET /api/v1/alarms`) |
| `docker compose run --rm simulator --scenario battery-drain --target 70B3D57ED00D0008 --interval 5` | bateria w dymku pinezki spada o 5 pkt co 5 s, poniżej 20% na czerwono |
| `docker compose run --rm simulator --scenario duplicate --once` | w logu `duplicate`: backend odrzuca drugą kopię tej samej ramki |
| `docker compose run --rm simulator --scenario theft --target 70B3D57ED00D0003 --once` (trwa wydanie, zaloguj się jako `blazej`) | pinezka zostaje niebieska; w logu `alarm pominięty (wyciszony/wyłączony)`: ramka zapisana, alarmu brak |

Symulator pamięta liczniki w `backend/.simulator-state.json`. Po `seed --demo --reset` możesz go usunąć, ale nie musisz: symulator i tak zaczyna od BOOT.

## 4. Ręcznie: `curl` albo Swagger

Ten sam endpoint, z którego korzysta symulator i płytka:

```bash
curl -X POST localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"device": "70B3D57ED00D0008", "payload_hex": "1200FF5A0000"}'
```

`payload_hex` to ramka z protokołu w hexie. Kilka gotowych:

| Ramka | Co to |
|---|---|
| `130001010158` | BOOT, licznik 1, firmware 1, włączenie, bateria 88% |
| `1200FF5A0000` | HEARTBEAT, licznik 255, bateria 90% |
| `11002A0101570028B440` | ALARM, licznik 42, mikrofon, pewność 87, 40 s, bateria 64% (przykład z protokołu) |

Własną ramkę najprościej złożyć koderem z backendu:

```bash
docker compose run --rm web python -c "from app.protocol.encoder import encode_alarm; print(encode_alarm(300, sources=['microphone','vibration'], confidence=95, duration_s=120, energy=220, battery_pct=70).hex())"
```

A odczytać dekoderem:

```bash
docker compose run --rm web python -c "from app.protocol.decoder import decode_hex, to_dict; print(to_dict(decode_hex('11002A0101570028B440')))"
```

Odpowiedzi `/ingest`:

| Kod | `status` / `detail` | Znaczenie |
|---|---|---|
| 201 | `stored` | zapisane; przy ALARM `alarm_created: true` (nowy) albo `false` (doklejony do otwartego alarmu z ostatnich 10 min) |
| 201 | `stored` + `muted: true` | czujnik wyłączony albo trwa wydanie: ramka zapisana, alarmu brak |
| 200 | `duplicate` | licznik nie większy niż ostatni z tego czujnika; nic nie zapisano |
| 404 | `Nieznany czujnik` | ID nie ma w bazie: dodaj czujnik w panelu admina albo użyj czujnika demo |
| 422 | `Błędna ramka: …` | zła długość, wersja, typ albo procent > 100 |

**Licznik.** Ramka z licznikiem mniejszym lub równym ostatniemu wraca jako `duplicate`. Przy ręcznych testach albo zwiększaj licznik, albo najpierw wyślij BOOT: po BOOT backend przyjmuje licznik od nowa.

## 5. Czy się zapisało: baza i logi

Konsola bazy:

```bash
cd backend
docker compose exec timescaledb psql -U detektor -d detektor
```

Przydatne zapytania (w `psql`, `\q` wychodzi):

```sql
-- ostatnie ramki
SELECT received_at, sensor_id, msg_type, counter, payload_hex, rssi
FROM messages ORDER BY received_at DESC LIMIT 10;

-- ostatnie alarmy (repeats = z ilu ramek złożony)
SELECT id, sensor_id, started_at, repeats, confidence, sources, status
FROM alarms ORDER BY started_at DESC LIMIT 10;

-- stan jednego czujnika po ramce
SELECT id, name, battery_pct, last_seen, last_counter, active
FROM sensors WHERE id = '70B3D57ED00D0009';

-- co zdekodował backend (kolumna JSON)
SELECT received_at, decoded FROM messages
WHERE sensor_id = '70B3D57ED00D0009' ORDER BY received_at DESC LIMIT 3;

-- ile ramek z każdego czujnika
SELECT sensor_id, count(*) AS ramek, max(received_at) AS ostatnia
FROM messages GROUP BY sensor_id ORDER BY sensor_id;
```

Jednorazowo, bez wchodzenia do konsoli:

```bash
docker compose exec timescaledb psql -U detektor -d detektor -c "SELECT * FROM messages ORDER BY received_at DESC LIMIT 5;"
```

Logi backendu na żywo (widać tu duplikaty, zgubione ramki, pominięte alarmy i błędne ramki):

```bash
docker compose logs -f web
```

Przez API (po zalogowaniu w Swaggerze): `GET /api/v1/sensors/{id}` pokazuje stan, baterię, `last_seen` i ostatnie alarmy czujnika.

## 6. Test z płytki przez Wi-Fi

Najprostszy test sprzętu, bez TTN: LoPy łączy się z Wi-Fi i robi to samo co `curl` z sekcji 4. Gotowy skrypt: [firmware/przyklady/wyslij_wifi.py](../firmware/przyklady/wyslij_wifi.py). Wysyła BOOT, HEARTBEAT i ALARM 3 razy i wypisuje odpowiedzi backendu.

**Sieć.** Płytka i laptop muszą być w tej samej sieci. Najpewniej działa **hotspot z telefonu**: sieci uczelniane (eduroam) zwykle blokują ruch między urządzeniami.

**Laptop z Windows + WSL + Docker Desktop:**

1. IP laptopa: w PowerShellu `ipconfig`, adres IPv4 karty Wi-Fi (np. `192.168.43.20`).
2. Zapora: raz, w PowerShellu jako administrator:
   ```powershell
   New-NetFirewallRule -DisplayName "Detektor API 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
   ```
   Sieć hotspotu ustaw w Windows jako **prywatną**.
3. Sprawdź z telefonu w tej samej sieci: `http://<IP laptopa>:8000/health` ma pokazać `{"status":"ok"}`. Jak telefon nie dojdzie, płytka też nie.

**Na płytce:**

1. W skrypcie uzupełnij `WIFI_SSID`, `WIFI_HASLO`, `API_HOST` (IP z punktu 1) i `DEVICE_ID`.
2. Wgraj i uruchom (Pymakr: *Upload*, potem *Run*; albo w REPL `exec(open('wyslij_wifi.py').read())`).
3. W konsoli płytki powinno być `201 {"status":"stored", ...}`, a przy pierwszym alarmie `"alarm_created":true`.
4. Sprawdź bazę (sekcja 5) i mapę (sekcja 2).

Skrypt działa też na laptopie zwykłym Pythonem (`python firmware/przyklady/wyslij_wifi.py`), wtedy wysyła na `localhost`. Tak sprawdzisz, czy problem jest w sieci, czy w backendzie.

**Własne ID płytki zamiast czujnika demo.** DevEUI płytki wypiszesz w REPL: `from network import LoRa; import ubinascii; print(ubinascii.hexlify(LoRa().mac()).upper())`. Dodaj go w panelu admina (Czujniki → Dodaj). Nowy czujnik jest nieaktywny i bez lokalizacji, a endpointu montażu jeszcze nie ma, więc żeby pokazał się na mapie, ustaw lokalizację ręcznie w bazie:

```sql
UPDATE sensors SET lat = 50.0647, lon = 20.3105, active = true WHERE id = '<DevEUI>';
```

## 7. Na telefonie

Apkę z laptopa otworzysz na telefonie przez localtunnel albo USB: [docs/frontend/pwa.md](frontend/pwa.md). Tunel stawiasz tylko na port frontendu; `/api` przejdzie przez proxy Vite do backendu.

## 8. Testy automatyczne

```bash
cd backend
docker compose run --rm web pytest                                    # wszystkie testy (SQLite w pamięci, baza Dockera niepotrzebna)
docker compose run --rm web pytest --cov=app --cov-report=term-missing
docker compose run --rm web ruff check app tests tools

cd ../frontend
docker compose run --rm web npm test
docker compose run --rm web npm run lint
```

Kod jest montowany do kontenerów, więc po zmianie plików nie trzeba przebudowywać obrazów. Przebudowa (`docker compose up -d --build`) jest potrzebna tylko po zmianie `requirements.txt` albo `package.json`.

## 9. Typowe problemy

| Objaw | Przyczyna i co zrobić |
|---|---|
| `relation "ranges" does not exist`, symulator dostaje 500 | świeża baza bez tabel: `docker compose run --rm web alembic upgrade head` |
| `password authentication failed for user "detektor"` | `.env` ma inne hasło niż to, z którym powstał wolumen bazy: przywróć stare albo `docker compose down -v` (kasuje dane) |
| `/ingest` zwraca `duplicate` dla każdej ramki | licznik nie rośnie: wyślij najpierw BOOT albo zwiększ licznik |
| `/ingest` zwraca 404 | czujnika nie ma w bazie: `seed --demo` albo dodaj go w panelu |
| mapa się nie zmienia po alarmie | odświeżanie co 60 s; F5; sprawdź, czy logujesz się na konto z tego leśnictwa |
| front pokazuje błąd sieci / `/api` 502 | backend nie działa: `docker compose ps` w `backend/` |
| stany demo „dziwne” po kilku godzinach | `seed --demo --reset` |
| `curl localhost:8000/health` działa, a kontener stoi | na porcie 8000 siedzi lokalny `uvicorn` z `.venv`: `ss -ltnp \| grep 8000` i zamknij go |
| płytka nie łączy się z backendem | sprawdź `/health` z telefonu w tej samej sieci; zapora Windows; hotspot zamiast eduroam |
| `docker` nie istnieje w WSL | Docker Desktop → Settings → Resources → WSL integration |
