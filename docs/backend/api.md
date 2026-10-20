# API backendu – kontrakt dla frontendu

> v2, po review Agaty (PR #20). Nazwy ścieżek i pól po angielsku (tak jak w kodzie), opisy po polsku.
> Na żywo, gdy backend chodzi: dokumentacja Swagger pod `http://localhost:8000/docs`.

## Model w skrócie

- **Jeden czujnik = jedno miejsce składowania drewna** (kilka mygieł przy drodze). Czujnik działa obszarowo, więc nie przypisujemy go do konkretnej mygły.
- **Na mapie są tylko czujniki.** Pozycję zapisujemy przy montażu z GPS telefonu leśniczego.
- **Wydanie drewna = wyciszenie czujnika** na czas wywozu. Leśniczy potwierdza wydanie w apce, czujnik w tym oknie nie generuje alarmów, a po jego końcu wraca do pracy.

## Ogólne zasady

- **Adres lokalnie:** `http://localhost:8000`, wszystkie ścieżki z prefiksem `/api/v1`
- **Format:** JSON, czas w UTC (`2026-10-16T10:25:00Z`), współrzędne jako `lat` / `lon` 
- **Logowanie:** po `POST /auth/login` każde zapytanie wysyła nagłówek `Authorization: Bearer <token>`
- **Odświeżanie:** apka odpytuje listy co kilkadziesiąt sekund, bez WebSocketów. Nowe alarmy i tak przychodzą pushem
- **Role:**
  - `forester` (leśniczy): widzi i obsługuje czujniki swojego leśnictwa, dostaje pushe
  - `district_manager` (nadleśniczy): widzi całe nadleśnictwo i raporty, bez pushy
  - `admin`: zarządza kontami


### Czujnik: ID vs nazwa

- **`id`** to identyfikator czujnika. Nadajemy go my i nie zmienia się.
- **`name`** nadaje leśniczy, np. „Skład przy drodze 5”, i może ją zmieniać.

### Stan czujnika (`stan`)

Wylicza go backend, a frontend tylko koloruje pinezkę:

| wartość | kiedy |
|---|---|
| `ok` | czuwa, działa, nic się nie dzieje |
| `muted` | trwa wydanie drewna, alarmy wyłączone do `muted_until` |
| `alarm` | jest otwarty alarm (bez odpowiedzi leśniczego) |
| `silent` | brak heartbeatu dłużej niż ~12 h (zerwany, rozładowany, poza zasięgiem) |
| `inactive` | czujnik wyłączony w apce albo jeszcze niezamontowany (brak lokalizacji) |



### Status alarmu (`status`)

| wartość | znaczenie |
|---|---|
| `new` | czeka na reakcję leśniczego |
| `theft` | leśniczy potwierdził kradzież |
| `false_alarm` | fałszywy alarm |

### Błędy

Każdy błąd ma ten sam kształt:

```json
{ "detail": "Czujnik o id 70B3D57ED0051234 nie istnieje" }
```

| kod | kiedy |
|---|---|
| 400 / 422 | złe dane w zapytaniu (422 zwraca FastAPI z listą błędnych pól) |
| 401 | brak tokena albo wygasł → przekieruj do logowania |
| 403 | brak uprawnień (np. czujnik z cudzego leśnictwa) |
| 404 | nie ma takiego obiektu |
| 409 | konflikt (np. wydanie już trwa, alarm ma już odpowiedź) |

---

## 1. Logowanie i hasło

### `POST /api/v1/auth/login`

```json
// zapytanie
{ "login": "blazej", "password": "tajne123" }
```
 
```json
// 200
{
  "token": "eyJhbGciOi...",
  "expires_at": "2026-10-17T10:25:00Z",
  "user": {
    "id": 3,
    "login": "blazej",
    "full_name": "Błażej Kowalski",
    "role": "forester",
    "range": { "id": 1, "name": "Leśnictwo Dąbrowa" },
    "must_change_password": false
  }
}
```

Złe hasło → `401`.

### `GET /api/v1/auth/me`

Zwraca zalogowanego użytkownika (ten sam obiekt `user`). Przydaje się po odświeżeniu apki.

### `POST /api/v1/auth/change-password`
 
Zmiana własnego hasła (także wymuszona przy pierwszym logowaniu).
 
```json
// zapytanie
{ "old_password": "Tymczasowe123!", "new_password": "MojeNoweHaslo2026" }
```
 
Odpowiedź `204`. Złe stare hasło → `400`. Po zmianie `must_change_password` = `false`.
 


---

## 2. Czujniki (mapa)

### `GET /api/v1/czujniki`

Parametry (opcjonalne): `?state=alarm&range_id=1&unmounted=true`

Leśniczy dostaje tylko swoje leśnictwo, a nadleśniczy wszystko. `unmounted=true` zwraca czujniki bez lokalizacji (do listy przy montażu).
 
```json
// 200
[
  {
    "id": "70B3D57ED0051234",
    "name": "Skład przy drodze 5",
    "lat": 50.0647,
    "lon": 19.9450,
    "range_id": 1,
    "active": true,
    "state": "alarm",
    "battery_pct": 64,
    "last_seen": "2026-10-16T09:58:12Z",
    "muted_until": null,
    "open_alarm_id": 41
  },
  {
    "id": "70B3D57ED0055678",
    "name": "Skład przy szlabanie",
    "lat": 50.0712,
    "lon": 19.9533,
    "range_id": 1,
    "active": true,
    "state": "muted",
    "battery_pct": 91,
    "last_seen": "2026-10-16T10:01:00Z",
    "muted_until": "2026-10-16T18:00:00Z",
    "open_alarm_id": null
  },
  {
    "id": "70B3D57ED0059ABC",
    "name": null,
    "lat": null,
    "lon": null,
    "range_id": null,
    "active": false,
    "state": "inactive",
    "battery_pct": 100,
    "last_seen": "2026-10-16T08:30:00Z",
    "muted_until": null,
    "open_alarm_id": null
  }
]
```
 
### `GET /api/v1/sensors/{id}`
 
Jeden czujnik, ten sam kształt + ostatnie alarmy i wydania:
 
```json
{
  "id": "70B3D57ED0051234",
  "name": "Skład przy drodze 5",
  "state": "alarm",
  "...": "pozostałe pola jak wyżej",
  "recent_alarms": [
    { "id": 41, "detected_at": "2026-10-16T09:57:40Z", "status": "new", "confidence": 87 }
  ],
  "recent_releases": [
    { "id": 7, "starts_at": "2026-10-15T06:00:00Z", "ends_at": "2026-10-15T14:00:00Z", "carrier": "TransLas", "log_count": 40 }
  ]
}
```
 
### `PUT /api/v1/sensors/{id}/mount`
 
Leśniczy montuje czujnik na miejscu: wybiera czujnik z listy, telefon podaje GPS. Po tym czujnik staje się aktywny.
 
```json
// zapytanie
{ "name": "Skład przy drodze 5", "lat": 50.0647, "lon": 19.9450 }
```
 
Odpowiedź `200`: czujnik z `active: true`. Leśnictwo bierzemy z konta leśniczego. Ponowny montaż (przeniesienie czujnika w inne miejsce) nadpisuje lokalizację.
 
### `PATCH /api/v1/sensors/{id}`
 
Zmiana nazwy albo włączenie/wyłączenie czujnika:
 
```json
// zmiana nazwy
{ "name": "Skład przy drodze 5 (nowy)" }
```
 
```json
// wyłączenie, np. skład pusty, czujnik do zdjęcia
{ "active": false }
```
 
Odpowiedź `200`: zaktualizowany czujnik. Wyłączony czujnik dalej wysyła heartbeaty (widzimy baterię), ale nie generuje alarmów ani pushy.

---

## 3. Wydania drewna (wyciszanie czujnika)
 
Najważniejsza akcja leśniczego. Bez niej każdy legalny wywóz kończy się alarmem.
 
### `POST /api/v1/sensors/{id}/releases`
 
Leśniczy wydaje drewno przewoźnikowi i potwierdza to w apce. **W apce wybiera czas wyciszenia z przycisków 1 h / 2 h / 4 h**, a apka wylicza z tego `ends_at`.
 
```json
// zapytanie
{ "ends_at": "2026-10-16T14:05:00Z" }
```
 
- `starts_at` nie trzeba podawać, backend wpisze „teraz”,
- bez `ends_at` backend przyjmie domyślne 4 h,
- opcjonalnie do ewidencji: `carrier` (przewoźnik), `log_count` (liczba kłód), `comment`.
```json
// 201
{
  "id": 8,
  "sensor_id": "70B3D57ED0055678",
  "starts_at": "2026-10-16T10:05:00Z",
  "ends_at": "2026-10-16T14:05:00Z",
  "carrier": null,
  "log_count": null,
  "comment": null,
  "created_by": "blazej"
}
```
 
Jeśli wydanie dla tego czujnika już trwa, zwracamy `409`.
 
### `POST /api/v1/releases/{id}/end`
 
Przewoźnik odjechał wcześniej, więc leśniczy kończy wyciszenie od razu i czujnik wraca do czuwania. Odpowiedź `200`: wydanie z `ends_at` ustawionym na „teraz”.
 
### `GET /api/v1/releases`
 
Historia wydań: `?sensor_id=...&from=...&to=...`. Kształt jak wyżej, lista. Przydaje się w raportach i przy wyjaśnianiu sporów z przewoźnikiem.
 
---
 
## 4. Alarmy
 
### `GET /api/v1/alarms`
 
Parametry: `?status=new&sensor_id=70B3D57ED0051234&from=2026-10-01T00:00:00Z&to=2026-10-31T23:59:59Z`
 
Sortowane od najnowszego.
 
```json
[
  {
    "id": 41,
    "detected_at": "2026-10-16T09:57:40Z",
    "sensor": { "id": "70B3D57ED0051234", "name": "Skład przy drodze 5", "lat": 50.0647, "lon": 19.9450 },
    "event_type": "theft",
    "sources": ["microphone", "vibration"],
    "confidence": 87,
    "duration_s": 40,
    "possible_tampering": false,
    "status": "new",
    "response": null
  },
  {
    "id": 39,
    "detected_at": "2026-10-15T14:12:03Z",
    "sensor": { "id": "70B3D57ED0051234", "name": "Skład przy drodze 5", "lat": 50.0647, "lon": 19.9450 },
    "event_type": "theft",
    "sources": ["vibration"],
    "confidence": 55,
    "duration_s": 12,
    "possible_tampering": true,
    "status": "false_alarm",
    "response": {
      "by": "blazej",
      "at": "2026-10-15T14:40:00Z",
      "comment": "zwierzę przy stosie",
      "lat": 50.0646,
      "lon": 19.9452
    }
  }
]
```
 
- `sources` pochodzi z ramki: które czujniki zareagowały
- `possible_tampering: true`, gdy były same wibracje bez dźwięku maszyny. Apka może wtedy pokazać „możliwa manipulacja przy czujniku”
- alarmy w czasie wydania nie powstają wcale (backend je pomija), więc tej listy nie trzeba filtrować
### `GET /api/v1/alarms/{id}`
 
Jeden alarm, ten sam kształt.
 
### `POST /api/v1/alarms/{id}/response`
 
Leśniczy po sprawdzeniu na miejscu.
 
```json
// zapytanie
{ "result": "theft", "comment": "przewoźnik ładował 5 dodatkowych kłód", "lat": 50.0646, "lon": 19.9452 }
```
 
- `result`: `theft` albo `false_alarm`
- `comment`, `lat`, `lon` opcjonalne. **Lokalizacji nie sprawdzamy, ufamy leśniczemu.** Apka może jednak dosłać pozycję z telefonu, a serwer tylko ją zapisze jako dowód, że ktoś był na miejscu
Odpowiedź `200`: alarm ze zmienionym `status` i uzupełnionym `response`. Ponowna odpowiedź na ten sam alarm zwraca `409`.
 
> Odpowiedź **nie idzie do czujnika** (komunikacja jednostronna), tylko zostaje w bazie: zamyka alarm i jest etykietą dla algorytmu.
 
---
 
## 5. Raporty (nadleśniczy)
 
### `GET /api/v1/reports/summary?from=2026-07-01&to=2026-09-30`
 
```json
{
  "period": { "from": "2026-07-01", "to": "2026-09-30" },
  "alarms": { "total": 23, "theft": 4, "false_alarm": 15, "unanswered": 4 },
  "releases": 31,
  "sensors": { "total": 6, "silent": 1, "low_battery": 2 },
  "per_sensor": [
    { "sensor_id": "70B3D57ED0051234", "name": "Skład przy drodze 5", "alarms": 6, "theft": 2, "false_alarm": 3, "releases": 12 },
    { "sensor_id": "70B3D57ED0055678", "name": "Skład przy szlabanie", "alarms": 2, "theft": 0, "false_alarm": 2, "releases": 9 }
  ],
  "per_week": [
    { "week": "2026-W27", "alarms": 2, "theft": 0 },
    { "week": "2026-W28", "alarms": 3, "theft": 1 }
  ]
}
```
 
`per_week` służy do wykresu.
 
### `GET /api/v1/reports/export.csv?from=2026-07-01&to=2026-09-30`
 
Plik CSV z alarmami i wydaniami (do Excela). `Content-Type: text/csv`, a frontend robi z tego zwykły link do pobrania.
 
---
 
## 6. Powiadomienia push (FCM)
 
Pushe dostaje tylko leśniczy (`forester`). Nadleśniczy korzysta z raportów.
 
### `POST /api/v1/push/subscriptions`
 
Apka po zgodzie użytkownika na powiadomienia wysyła token FCM.
 
```json
// zapytanie
{ "fcm_token": "fGx1...:APA91b...", "device_label": "Android – Chrome" }
```
 
Odpowiedź `201`. Ten sam token wysłany ponownie niczego nie psuje.
 
### `DELETE /api/v1/push/subscriptions/{fcm_token}`
 
Przy wylogowaniu. Odpowiedź `204`.
 
**Co przychodzi w pushu** (pole `data` w wiadomości FCM):
 
```json
{
  "type": "alarm",
  "alarm_id": "41",
  "sensor_id": "70B3D57ED0051234",
  "title": "Alarm: Skład przy drodze 5",
  "body": "Możliwe podbieranie drewna, pewność 87%"
}
```
 
Inne typy: `silent`, `low_battery`, `release_ended` (przypomnienie, że wyciszenie się skończyło). Kliknięcie otwiera ekran alarmu albo czujnika.
 
---
 
## 7. Użytkownicy (admin)
 
### `GET /api/v1/users`
 
```json
[
  { "id": 3, "login": "blazej", "full_name": "Błażej Kowalski", "role": "forester", "range_id": 1, "active": true, "must_change_password": false },
  { "id": 4, "login": "bogdan", "full_name": "Bogdan Nowak", "role": "district_manager", "range_id": null, "active": true, "must_change_password": false }
]
```
 
### `POST /api/v1/users`
 
```json
// zapytanie
{ "login": "nowy.lesniczy", "full_name": "Jan Nowy", "role": "forester", "range_id": 2, "password": "Tymczasowe123!" }
```
 
Odpowiedź `201`: utworzony użytkownik (bez hasła), z `must_change_password: true`, więc przy pierwszym logowaniu musi ustawić własne hasło.
 
### `PATCH /api/v1/users/{id}`
 
Zmiana roli, leśnictwa albo dezaktywacja: `{ "active": false }`.
 
### `POST /api/v1/users/{id}/reset-password`
 
Admin resetuje hasło, np. gdy leśniczy je zapomniał.
 
```json
// 200
{ "temporary_password": "Xk7-pQ2-mR9" }
```
 
Admin przekazuje hasło tymczasowe leśniczemu, a konto dostaje `must_change_password: true`.
 
### `GET /api/v1/ranges`
 
Lista leśnictw do formularza.
 
```json
[ { "id": 1, "name": "Leśnictwo Dąbrowa" }, { "id": 2, "name": "Leśnictwo Olszyny" } ]
```
 
---
 
## Ustalenia z Agatą (review PR #20)
 
- [x] nazwy ścieżek i pól po angielsku, tak jak w kodzie, opisy po polsku
- [x] długość wyciszenia: w apce przyciski 1 h / 2 h / 4 h, a gdy apka nie poda czasu, backend przyjmuje 4 h
- [x] odświeżanie list co kilkadziesiąt sekund + push, bez WebSocketów
- [x] token ważny 24 h
- [x] pushe tylko dla leśniczego, nadleśniczy ma raporty
- [x] zmiana hasła, reset przez admina, wymuszona zmiana przy pierwszym logowaniu
- [x] lokalizacja przy odpowiedzi na alarm: opcjonalna, tylko zapisywana jako dowód, bez sprawdzania
