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

- **`id`** to identyfikator czujnika: DevEUI, 16 znaków szesnastkowych (np. `70B3D57ED0051234`). Wpisuje go admin przy rejestracji i nie zmienia się. Backend usuwa spacje, `:` i `-` oraz zamienia litery na wielkie, więc można go przepisać z naklejki.
- **`name`** nadaje leśniczy, np. „Skład przy drodze 5”, i może ją zmieniać.

### Stan czujnika (`state`)

Wylicza go backend przy każdym odczycie (nie jest zapisany w bazie), a frontend tylko koloruje pinezkę. Sprawdzamy w tej kolejności, pierwszy pasujący wygrywa:

| wartość | kiedy |
|---|---|
| `inactive` | czujnik wyłączony w apce albo jeszcze niezamontowany (brak lokalizacji) |
| `alarm` | jest otwarty alarm (bez odpowiedzi leśniczego), także gdy potem zaczęło się wydanie |
| `muted` | trwa wydanie drewna, alarmy wyłączone do `muted_until` |
| `silent` | brak ramki dłużej niż 12 h albo czujnik jeszcze nic nie wysłał (zerwany, rozładowany, poza zasięgiem) |
| `ok` | czuwa, działa, nic się nie dzieje |

`open_alarm_id` i `muted_until` są wypełnione zawsze, gdy jest otwarty alarm albo trwa wydanie, niezależnie od `state`.



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

Złe hasło, nieistniejący login i konto nieaktywne dają ten sam `401` (`"Błędny login lub hasło"`), żeby nie zdradzać, które loginy istnieją.

Po 5 nieudanych próbach dla jednego loginu w ciągu 15 min kolejne próby (także z dobrym hasłem) dostają `429` z nagłówkiem `Retry-After` (sekundy) do końca tego okna. Udane logowanie zeruje licznik. Apka może pokazać `detail` z odpowiedzi ("Za dużo nieudanych prób, spróbuj za … min").

Token jest ważny 24 h i wysyłamy go w nagłówku `Authorization: Bearer <token>`. W Swaggerze (`/docs`) wklej go po kliknięciu **Authorize**. Token przestaje działać, gdy admin dezaktywuje konto.

**Wymuszona zmiana hasła.** Gdy `must_change_password` = `true`, token działa tylko na `/auth/me` i `/auth/change-password`. Pozostałe endpointy zwracają `403` z `"Najpierw zmień hasło"`. Po zmianie hasła ten sam token działa już wszędzie.

### `GET /api/v1/auth/me`

Zwraca zalogowanego użytkownika (ten sam obiekt `user`). Przydaje się po odświeżeniu apki.

### `POST /api/v1/auth/change-password`
 
Zmiana własnego hasła (także wymuszona przy pierwszym logowaniu).
 
```json
// zapytanie
{ "old_password": "Tymczasowe123!", "new_password": "MojeNoweHaslo2026" }
```
 
Odpowiedź `204`. Złe stare hasło → `400`. Nowe hasło takie samo jak stare → `400`. Nowe hasło krótsze niż 8 znaków → `422`. Po zmianie `must_change_password` = `false`.
 


---

## 2. Czujniki (mapa)

Kto co może:

| | leśniczy | nadleśniczy | admin |
|---|---|---|---|
| lista i szczegóły | swoje leśnictwo (cudzy czujnik → `403`) | wszystkie | wszystkie |
| rejestracja (`POST`) | – | – | tak |
| nazwa, włączenie (`PATCH`) | swoje leśnictwo | – | tak |
| leśnictwo (`PATCH range_id`) | – | – | tak |
| montaż (`PUT .../mount`) | swoje leśnictwo | – | tak (poprawki) |
| wydania: tworzenie i zakończenie | swoje leśnictwo | – | tak (poprawki) |
| wydania: historia (`GET /releases`) | swoje leśnictwo | wszystkie | wszystkie |

### `GET /api/v1/sensors`

Jedna lista dla mapy i dla tabeli w panelu admina. Parametry (opcjonalne): `?state=alarm&range_id=1&unmounted=true`

Leśniczy dostaje tylko swoje leśnictwo (leśniczy bez leśnictwa dostaje pustą listę), a nadleśniczy i admin wszystko. `unmounted=true` zwraca czujniki bez lokalizacji (do listy przy montażu). Nieznany `state` → `422`.
 
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
    "range_id": 1,
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
 
Jeden czujnik, ten sam kształt + 5 ostatnich alarmów i 5 ostatnich wydań (od najnowszych). Brak czujnika → `404`, czujnik z innego leśnictwa → `403`.
 
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
 
### `POST /api/v1/sensors`

Admin rejestruje nowy czujnik (np. po odebraniu partii od hardware). Leśnictwo jest wymagane, nazwa opcjonalna (zwykle nadaje ją leśniczy przy montażu).

```json
// zapytanie
{ "id": "70B3D57ED0051234", "range_id": 1, "name": null }
```

Odpowiedź `201`: czujnik z `active: false`, bez lokalizacji, `state: "inactive"`. Pojawia się na liście `?unmounted=true` leśniczych tego leśnictwa.

- czujnik o tym ID już jest → `409`
- nie ma takiego leśnictwa → `400`
- ID nie ma 16 znaków szesnastkowych → `422`

### `PUT /api/v1/sensors/{id}/mount`
 
Leśniczy montuje czujnik na miejscu: wybiera czujnik z listy, telefon podaje GPS. Po tym czujnik staje się aktywny.
 
```json
// zapytanie
{ "name": "Skład przy drodze 5", "lat": 50.0647, "lon": 19.9450 }
```
 
Odpowiedź `200`: czujnik jak w `GET /api/v1/sensors/{id}` (bez ostatnich alarmów i wydań), z `active: true`. Leśnictwo się nie zmienia: przypisuje je admin przy rejestracji.

- `name` wymagane, 1–100 znaków (spacje na początku i końcu są obcinane); `lat` −90…90, `lon` −180…180
- ponowny montaż (przeniesienie czujnika w inne miejsce) nadpisuje nazwę i lokalizację
- montaż włącza też czujnik wyłączony wcześniej przez `PATCH`
- świeżo zamontowany czujnik, który jeszcze nic nie wysłał, ma stan `silent`; po pierwszej ramce `ok`
- czujnik z innego leśnictwa albo zapytanie od nadleśniczego → `403`, brak czujnika → `404`, złe dane → `422`
 
### `PATCH /api/v1/sensors/{id}`
 
Zmiana nazwy, leśnictwa albo włączenie/wyłączenie. Pola, których nie podasz, zostają bez zmian. `"name": null` usuwa nazwę.
 
```json
// zmiana nazwy
{ "name": "Skład przy drodze 5 (nowy)" }
```
 
```json
// wyłączenie, np. skład pusty, czujnik do zdjęcia
{ "active": false }
```
 
```json
// przeniesienie do innego leśnictwa (tylko admin)
{ "range_id": 2 }
```

Odpowiedź `200`: zaktualizowany czujnik. Wyłączony czujnik dalej wysyła heartbeaty (widzimy baterię), ale nie generuje alarmów ani pushy.

- leśniczy zmienia `range_id`, cudzy czujnik albo zapytanie od nadleśniczego → `403`
- nie ma takiego leśnictwa → `400`
- `"range_id": null`, `"active": null` albo pusta nazwa → `422` (leśnictwa nie da się odpiąć)

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
- bez `ends_at` backend przyjmie domyślne 4 h (`RELEASE_DEFAULT_HOURS`),
- `ends_at` musi być w przyszłości i najwyżej 24 h od teraz (`RELEASE_MAX_HOURS`), inaczej `422`; czas bez strefy = UTC,
- opcjonalnie do ewidencji: `carrier` (przewoźnik, do 100 znaków), `log_count` (liczba kłód, ≥ 0), `comment` (do 500 znaków),
- `created_by` to login z tokena.
```json
// 201
{
  "id": 8,
  "sensor_id": "70B3D57ED0055678",
  "sensor_name": "Skład przy drodze 5",
  "starts_at": "2026-10-16T10:05:00Z",
  "ends_at": "2026-10-16T14:05:00Z",
  "active": true,
  "carrier": null,
  "log_count": null,
  "comment": null,
  "created_by": "blazej"
}
```
 
- `active`: czy wydanie trwa w chwili odpowiedzi
- wydanie dla tego czujnika już trwa → `409` (w `detail` jest jego `id`, żeby apka mogła je zakończyć)
- czujnik niezamontowany (bez lokalizacji) → `409`; dwa równoczesne wydania dla jednego czujnika nie powstaną (blokada wiersza czujnika)
- czujnik z innego leśnictwa albo zapytanie od nadleśniczego → `403`, brak czujnika → `404`

W trakcie wydania `/ingest` zapisuje ramki, ale nie tworzy alarmów, a czujnik ma stan `muted` z `muted_until` = `ends_at`.
 
### `POST /api/v1/releases/{id}/end`
 
Przewoźnik odjechał wcześniej, więc leśniczy kończy wyciszenie od razu i czujnik wraca do czuwania. Odpowiedź `200`: wydanie z `ends_at` ustawionym na „teraz” i `active: false`. Wydanie już zakończone → `409`, brak → `404`, cudze leśnictwo / nadleśniczy → `403`.
 
### `GET /api/v1/releases`
 
Historia wydań: `?sensor_id=...&active=true&from=...&to=...&limit=100&offset=0`. Kształt jak wyżej, lista od najnowszych. Przydaje się w raportach i przy wyjaśnianiu sporów z przewoźnikiem.

- `active=true` tylko trwające, `active=false` tylko zakończone
- `from` / `to`: wydania, które choć częściowo trwały w tym przedziale; czas bez strefy = UTC
- `limit` 1–500 (domyślnie 100)
- leśniczy dostaje wydania swojego leśnictwa, nadleśniczy i admin wszystkie
 
---
 
## 4. Alarmy
 
### `GET /api/v1/alarms`
 
Parametry (wszystkie opcjonalne): `?status=new&sensor_id=70B3D57ED0051234&from=2026-10-01T00:00:00Z&to=2026-10-31T23:59:59Z&limit=100&offset=0`

- `from` / `to` dotyczą chwili wykrycia (`detected_at`); czas bez strefy = UTC
- `limit` 1–500 (domyślnie 100), `offset` do stronicowania
- leśniczy dostaje alarmy swojego leśnictwa, nadleśniczy i admin wszystkie

Sortowane od najnowszego.
 
```json
[
  {
    "id": 41,
    "detected_at": "2026-10-16T09:57:40Z",
    "last_frame_at": "2026-10-16T09:58:40Z",
    "sensor": { "id": "70B3D57ED0051234", "name": "Skład przy drodze 5", "lat": 50.0647, "lon": 19.9450 },
    "event_type": "theft",
    "sources": ["microphone", "vibration"],
    "confidence": 87,
    "duration_s": 40,
    "energy": 180,
    "repeats": 3,
    "possible_tampering": false,
    "status": "new",
    "response": null
  },
  {
    "id": 39,
    "detected_at": "2026-10-15T14:12:03Z",
    "last_frame_at": "2026-10-15T14:13:03Z",
    "sensor": { "id": "70B3D57ED0051234", "name": "Skład przy drodze 5", "lat": 50.0647, "lon": 19.9450 },
    "event_type": "theft",
    "sources": ["vibration"],
    "confidence": 55,
    "duration_s": 12,
    "energy": 60,
    "repeats": 3,
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
 
- `sources` pochodzi z ramki: które czujniki zareagowały (`microphone`, `vibration`)
- `possible_tampering: true`, gdy `sources` to same wibracje (bez dźwięku). Apka może wtedy pokazać „możliwa manipulacja przy czujniku”
- `event_type`: kod rodzaju zdarzenia z ramki zamieniony na nazwę. Na razie `1` → `theft`, a każdy inny kod → `unknown`. Listę ustala Kiryl
- `repeats`: z ilu ramek złożył się alarm (urządzenie wysyła ALARM 3 razy, a backend scala ramki z 10 minut w jeden alarm); `last_frame_at` to czas ostatniej z nich
- `confidence`, `duration_s`, `energy`: największe wartości ze scalonych ramek
- alarmy w czasie wydania nie powstają wcale (backend je pomija), więc tej listy nie trzeba filtrować
### `GET /api/v1/alarms/{id}`
 
Jeden alarm, ten sam kształt. Brak alarmu → `404`, alarm z innego leśnictwa → `403`.
 
### `POST /api/v1/alarms/{id}/response`
 
Leśniczy po sprawdzeniu na miejscu. Odpowiedzieć może leśniczy leśnictwa, w którym jest czujnik, oraz admin (np. żeby coś poprawić). Nadleśniczy → `403`.
 
```json
// zapytanie
{ "result": "theft", "comment": "przewoźnik ładował 5 dodatkowych kłód", "lat": 50.0646, "lon": 19.9452 }
```
 
- `result`: `theft` albo `false_alarm`
- `comment` (do 500 znaków), `lat`, `lon` opcjonalne. **Lokalizacji nie sprawdzamy, ufamy leśniczemu.** Apka może jednak dosłać pozycję z telefonu, a serwer tylko ją zapisze jako dowód, że ktoś był na miejscu
- `lat` i `lon` podajemy razem albo wcale; jedna współrzędna albo wartość poza zakresem → `422`
- `response.by` to login z tokena, `response.at` to czas serwera
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
 
## 6. Powiadomienia push (Web Push, VAPID)
 
Standardowy Web Push przeglądarki z kluczami VAPID, bez Firebase. Pushe dostaje tylko leśniczy (`forester`). Nadleśniczy korzysta z raportów.
 
Działa tylko po HTTPS albo na `localhost`. Android (Chrome, Edge, Firefox): w przeglądarce i w zainstalowanej PWA. iPhone (iOS 16.4+): tylko w aplikacji dodanej do ekranu początkowego.
 
### `GET /api/v1/push/vapid-public-key`
 
Klucz publiczny do `pushManager.subscribe({ userVisibleOnly: true, applicationServerKey })`. Front nie wpisuje go na sztywno.
 
```json
// 200
{ "public_key": "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U" }
```
 
Klucz jest w base64url, a `applicationServerKey` przyjmuje go po zamianie na `Uint8Array`.
 
### `POST /api/v1/push/subscriptions`
 
Po zgodzie użytkownika (prośba po kliknięciu przycisku, nie przy wejściu) apka wysyła to, co zwraca `subscription.toJSON()`, plus opcjonalną etykietę urządzenia.
 
```json
// zapytanie
{
  "endpoint": "https://fcm.googleapis.com/fcm/send/dXk0...:APA91b...",
  "expirationTime": null,
  "keys": { "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM", "auth": "tBHItJI5svbpez7KI4CCXg" },
  "device_label": "Android – Chrome"
}
```
 
- odpowiedź `201`; ten sam `endpoint` wysłany ponownie nadpisuje klucze i właściciela (np. inne konto na tym samym telefonie), duplikatu nie ma,
- `expirationTime` backend ignoruje,
- konto inne niż leśniczy → `403`.
 
### `DELETE /api/v1/push/subscriptions?endpoint=…`
 
Przy wylogowaniu, razem z `subscription.unsubscribe()` w przeglądarce. `endpoint` w zapytaniu zakodowany przez `encodeURIComponent`. Odpowiedź `204`, także gdy subskrypcji już nie ma. Usunąć można tylko własną subskrypcję.
 
**Co przychodzi w pushu** (treść wiadomości, w service workerze `event.data.json()`):
 
```json
{
  "type": "alarm",
  "alarm_id": 41,
  "sensor_id": "70B3D57ED0051234",
  "title": "Alarm: Skład przy drodze 5",
  "body": "Możliwe podbieranie drewna, pewność 87%",
  "url": "/alarms/41"
}
```
 
Service worker pokazuje `title` i `body` (`showNotification`), a `notificationclick` otwiera `url`. Inne typy: `silent`, `low_battery`, `release_ended` (przypomnienie, że wyciszenie się skończyło); `url` prowadzi wtedy do czujnika.
 
Gdy usługa push odpowie `404` albo `410` (subskrypcja wygasła, użytkownik cofnął zgodę), backend usuwa subskrypcję.
 
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

- login zajęty → `409`
- `forester` bez `range_id` albo nieistniejące leśnictwo → `400`
- nieznana rola albo hasło krótsze niż 8 znaków → `422`
 
### `PATCH /api/v1/users/{id}`
 
Zmiana roli, leśnictwa albo dezaktywacja: `{ "active": false }`. Można też zmienić `full_name`. Pola, których nie podasz, zostają bez zmian, a `"range_id": null` odpina leśnictwo. Dezaktywowany użytkownik nie zaloguje się, a jego token od razu przestaje działać.

- `forester` bez leśnictwa albo nieistniejące leśnictwo → `400`
- admin nie może dezaktywować ani zdegradować samego siebie → `409`
- nie ma takiego użytkownika → `404`
 
### `POST /api/v1/users/{id}/reset-password`
 
Admin resetuje hasło, np. gdy leśniczy je zapomniał.
 
```json
// 200
{ "temporary_password": "Xk7-pQ2-mR9" }
```
 
Admin przekazuje hasło tymczasowe leśniczemu, a konto dostaje `must_change_password: true`.
 
### `GET /api/v1/ranges`
 
Lista leśnictw do formularza. Dostępna tylko dla admina.
 
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
