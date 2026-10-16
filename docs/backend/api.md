# API backendu – kontrakt dla frontendu

> Szkic v1, do ustalenia z Agatą. Nazwy pól i odpowiedzi mogą się jeszcze zmienić.
> Na żywo, gdy backend chodzi: dokumentacja Swagger pod `http://localhost:8000/docs`.

## Model w skrócie

- **Jeden czujnik = jedno miejsce składowania drewna** (kilka mygieł przy drodze). Czujnik działa obszarowo, więc nie przypisujemy go do konkretnej mygły.
- **Na mapie są tylko czujniki.** Pozycję zapisujemy przy montażu z GPS telefonu leśniczego.
- **Wydanie drewna = wyciszenie czujnika** na czas wywozu. Leśniczy potwierdza wydanie w apce, czujnik w tym oknie nie generuje alarmów, a po jego końcu wraca do pracy.

## Ogólne zasady

- **Adres lokalnie:** `http://localhost:8000`, wszystkie ścieżki z prefiksem `/api/v1`
- **Format:** JSON, czas w UTC (`2026-10-16T10:25:00Z`), współrzędne jako `lat` / `lon` 
- **Logowanie:** po `POST /auth/login` każde zapytanie wysyła nagłówek `Authorization: Bearer <token>`
- **Role:**
  - `lesniczy`: widzi i obsługuje czujniki swojego leśnictwa
  - `nadlesniczy`: widzi całe nadleśnictwo i raporty
  - `admin`: zarządza kontami

### Czujnik: ID vs nazwa

- **`id`** to identyfikator czujnika. Nadajemy go my i nie zmienia się.
- **`nazwa`** nadaje leśniczy, np. „Skład przy drodze 5”, i może ją zmieniać.

### Stan czujnika (`stan`)

Wylicza go backend, a frontend tylko koloruje pinezkę:

| wartość | kiedy |
|---|---|
| `ok` | czuwa, działa, nic się nie dzieje |
| `wyciszony` | trwa wydanie drewna, alarmy wyłączone do `wyciszony_do` |
| `alarm` | jest otwarty alarm (bez odpowiedzi leśniczego) |
| `milczy` | brak heartbeatu dłużej niż ~12 h (zerwany, rozładowany, poza zasięgiem) |
| `nieaktywny` | czujnik wyłączony w apce albo jeszcze niezamontowany (brak lokalizacji) |


### Status alarmu (`status`)

| wartość | znaczenie |
|---|---|
| `nowy` | czeka na reakcję leśniczego |
| `kradziez` | leśniczy potwierdził kradzież |
| `falszywy` | fałszywy alarm |

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

## 1. Logowanie

### `POST /api/v1/auth/login`

```json
// zapytanie
{ "login": "blazej", "haslo": "tajne123" }
```

```json
// 200
{
  "token": "eyJhbGciOi...",
  "wygasa": "2026-10-17T10:25:00Z",
  "user": {
    "id": 3,
    "login": "blazej",
    "imie": "Błażej Kowalski",
    "rola": "lesniczy",
    "lesnictwo": { "id": 1, "nazwa": "Leśnictwo Dąbrowa" }
  }
}
```

Złe hasło → `401`.

### `GET /api/v1/auth/me`

Zwraca zalogowanego użytkownika (ten sam obiekt `user`). Przydaje się po odświeżeniu apki.

---

## 2. Czujniki (mapa)

### `GET /api/v1/czujniki`

Parametry (opcjonalne): `?stan=alarm&lesnictwo_id=1&niezamontowane=true`

Leśniczy dostaje tylko swoje leśnictwo, a nadleśniczy wszystko. `niezamontowane=true` zwraca czujniki bez lokalizacji (do listy przy montażu).

```json
// 200
[
  {
    "id": "70B3D57ED0051234",
    "nazwa": "Skład przy drodze 5",
    "lat": 50.0647,
    "lon": 19.9450,
    "lesnictwo_id": 1,
    "aktywny": true,
    "stan": "alarm",
    "bateria_pct": 64,
    "ostatni_kontakt": "2026-10-16T09:58:12Z",
    "wyciszony_do": null,
    "otwarty_alarm_id": 41
  },
  {
    "id": "70B3D57ED0055678",
    "nazwa": "Skład przy szlabanie",
    "lat": 50.0712,
    "lon": 19.9533,
    "lesnictwo_id": 1,
    "aktywny": true,
    "stan": "wyciszony",
    "bateria_pct": 91,
    "ostatni_kontakt": "2026-10-16T10:01:00Z",
    "wyciszony_do": "2026-10-16T18:00:00Z",
    "otwarty_alarm_id": null
  },
  {
    "id": "70B3D57ED0059ABC",
    "nazwa": null,
    "lat": null,
    "lon": null,
    "lesnictwo_id": null,
    "aktywny": false,
    "stan": "nieaktywny",
    "bateria_pct": 100,
    "ostatni_kontakt": "2026-10-16T08:30:00Z",
    "wyciszony_do": null,
    "otwarty_alarm_id": null
  }
]
```

### `GET /api/v1/czujniki/{id}`

Jeden czujnik, ten sam kształt + ostatnie alarmy i wydania:

```json
{
  "id": "70B3D57ED0051234",
  "nazwa": "Skład przy drodze 5",
  "stan": "alarm",
  "...": "pozostałe pola jak wyżej",
  "ostatnie_alarmy": [
    { "id": 41, "czas": "2026-10-16T09:57:40Z", "status": "nowy", "pewnosc": 87 }
  ],
  "ostatnie_wydania": [
    { "id": 7, "od": "2026-10-15T06:00:00Z", "do": "2026-10-15T14:00:00Z", "przewoznik": "TransLas", "liczba_klod": 40 }
  ]
}
```

### `PUT /api/v1/czujniki/{id}/montaz`

Leśniczy montuje czujnik na miejscu: wybiera czujnik z listy, telefon podaje GPS. Po tym czujnik staje się aktywny.

```json
// zapytanie
{ "nazwa": "Skład przy drodze 5", "lat": 50.0647, "lon": 19.9450 }
```

Odpowiedź `200`: czujnik z `aktywny: true`. Leśnictwo bierzemy z konta leśniczego. Ponowny montaż (przeniesienie czujnika w inne miejsce) nadpisuje lokalizację.

### `PATCH /api/v1/czujniki/{id}`

Zmiana nazwy albo włączenie/wyłączenie czujnika:

```json
// zmiana nazwy
{ "nazwa": "Skład przy drodze 5 (nowy)" }
```

```json
// wyłączenie, np. skład pusty, czujnik do zdjęcia
{ "aktywny": false }
```

Odpowiedź `200`: zaktualizowany czujnik. Wyłączony czujnik dalej wysyła heartbeaty (widzimy baterię), ale nie generuje alarmów ani pushy.

---

## 3. Wydania drewna (wyciszanie czujnika)

Najważniejsza akcja leśniczego. Bez niej każdy legalny wywóz kończy się alarmem.

### `POST /api/v1/czujniki/{id}/wydania`

Leśniczy wydaje drewno przewoźnikowi i potwierdza to w apce.

```json
// zapytanie
{
  "do": "2026-10-16T18:00:00Z",
}
```

- `od` nie trzeba podawać, backend wpisze „teraz”,
- bez `do` backend przyjmie domyślne okno (np. +4 h),
- `przewoznik`, `liczba_klod` i `komentarz` - opcjonalnie do ewidencji
  
```json
// 201
{
  "id": 8,
  "czujnik_id": "70B3D57ED0055678",
  "od": "2026-10-16T10:05:00Z",
  "do": "2026-10-16T18:00:00Z",
  "przewoznik": "TransLas", #opcjonalnie
  "liczba_klod": 40, #opcjonalnie
  "komentarz": "mygła M-13", #opcjonalnie
  "kto": "blazej"
}
```

Jeśli wydanie dla tego czujnika już trwa, zwracamy `409`.

### `POST /api/v1/wydania/{id}/zakoncz`

Przewoźnik odjechał wcześniej, więc leśniczy kończy wyciszenie od razu i czujnik wraca do czuwania. Odpowiedź `200`: wydanie z `do` ustawionym na „teraz”.

### `GET /api/v1/wydania`

Historia wydań: `?czujnik_id=...&od=...&do=...`. Kształt jak wyżej, lista. Przydaje się w raportach i przy wyjaśnianiu sporów z przewoźnikiem.

---

## 4. Alarmy

### `GET /api/v1/alarmy`

Parametry: `?status=nowy&czujnik_id=70B3D57ED0051234&od=2026-10-01T00:00:00Z&do=2026-10-31T23:59:59Z`

Sortowane od najnowszego.

```json
[
  {
    "id": 41,
    "czas": "2026-10-16T09:57:40Z",
    "czujnik": { "id": "70B3D57ED0051234", "nazwa": "Skład przy drodze 5", "lat": 50.0647, "lon": 19.9450 },
    "rodzaj": "podbieranie",
    "zrodlo": ["mikrofon", "wibracje"],
    "pewnosc": 87,
    "czas_trwania_s": 40,
    "mozliwa_manipulacja": false,
    "status": "nowy",
    "odpowiedz": null
  },
  {
    "id": 39,
    "czas": "2026-10-15T14:12:03Z",
    "czujnik": { "id": "70B3D57ED0051234", "nazwa": "Skład przy drodze 5", "lat": 50.0647, "lon": 19.9450 },
    "rodzaj": "podbieranie",
    "zrodlo": ["wibracje"],
    "pewnosc": 55,
    "czas_trwania_s": 12,
    "mozliwa_manipulacja": true,
    "status": "falszywy",
    "odpowiedz": {
      "kto": "blazej",
      "kiedy": "2026-10-15T14:40:00Z",
      "komentarz": "zwierzę przy stosie"
    }
  }
]
```

- `zrodlo` pochodzi z ramki: które czujniki zareagowały
- `mozliwa_manipulacja: true`, gdy były same wibracje bez dźwięku maszyny. Apka może wtedy pokazać „możliwa manipulacja przy czujniku”
- alarmy w czasie wydania nie powstają wcale (backend je pomija), więc tej listy nie trzeba filtrować

### `GET /api/v1/alarmy/{id}`

Jeden alarm, ten sam kształt.

### `POST /api/v1/alarmy/{id}/odpowiedz`

Leśniczy po sprawdzeniu na miejscu.

```json
// zapytanie
{ "wynik": "kradziez", "komentarz": "przewoźnik ładował 5 dodatkowych kłód" }
```

`wynik`: `kradziez` albo `falszywy`. Odpowiedź `200`: alarm ze zmienionym `status` i uzupełnioną `odpowiedz`. Ponowna odpowiedź na ten sam alarm zwraca `409`.

> Odpowiedź **nie idzie do czujnika** (komunikacja jednostronna), tylko zostaje w bazie: zamyka alarm i jest etykietą dla algorytmu.

---

## 5. Raporty (nadleśniczy)

### `GET /api/v1/raporty/podsumowanie?od=2026-07-01&do=2026-09-30`

```json
{
  "okres": { "od": "2026-07-01", "do": "2026-09-30" },
  "alarmy": { "wszystkie": 23, "kradziez": 4, "falszywy": 15, "bez_odpowiedzi": 4 },
  "wydania": 31,
  "czujniki": { "wszystkie": 6, "milczace": 1, "niska_bateria": 2 },
  "per_czujnik": [
    { "czujnik_id": "70B3D57ED0051234", "nazwa": "Skład przy drodze 5", "alarmy": 6, "kradziez": 2, "falszywy": 3, "wydania": 12 },
    { "czujnik_id": "70B3D57ED0055678", "nazwa": "Skład przy szlabanie", "alarmy": 2, "kradziez": 0, "falszywy": 2, "wydania": 9 }
  ],
  "per_tydzien": [
    { "tydzien": "2026-W27", "alarmy": 2, "kradziez": 0 },
    { "tydzien": "2026-W28", "alarmy": 3, "kradziez": 1 }
  ]
}
```

`per_tydzien` służy do wykresu.

### `GET /api/v1/raporty/eksport.csv?od=2026-07-01&do=2026-09-30`

Plik CSV z alarmami i wydaniami (do Excela). `Content-Type: text/csv`, a frontend robi z tego zwykły link do pobrania.

---

## 6. Powiadomienia push (FCM)

### `POST /api/v1/push/subskrypcje`

Apka po zgodzie użytkownika na powiadomienia wysyła token FCM.

```json
// zapytanie
{ "token_fcm": "fGx1...:APA91b...", "urzadzenie": "Android – Chrome" }
```

Odpowiedź `201`. Ten sam token wysłany ponownie niczego nie psuje.

### `DELETE /api/v1/push/subskrypcje/{token_fcm}`

Przy wylogowaniu. Odpowiedź `204`.

**Co przychodzi w pushu** (pole `data` w wiadomości FCM):

```json
{
  "typ": "alarm",
  "alarm_id": "41",
  "czujnik_id": "70B3D57ED0051234",
  "tytul": "Alarm: Skład przy drodze 5",
  "tresc": "Możliwe podbieranie drewna, pewność 87%"
}
```

Inne typy: `milczy`, `niska_bateria`, `koniec_wydania` (przypomnienie, że wyciszenie się skończyło). Kliknięcie otwiera ekran alarmu albo czujnika.

---

## 7. Użytkownicy (admin)

### `GET /api/v1/uzytkownicy`

```json
[
  { "id": 3, "login": "blazej", "imie": "Błażej Kowalski", "rola": "lesniczy", "lesnictwo_id": 1, "aktywny": true },
  { "id": 4, "login": "bogdan", "imie": "Bogdan Nowak", "rola": "nadlesniczy", "lesnictwo_id": null, "aktywny": true }
]
```

### `POST /api/v1/uzytkownicy`

```json
// zapytanie
{ "login": "nowy.lesniczy", "imie": "Jan Nowy", "rola": "lesniczy", "lesnictwo_id": 2, "haslo": "Tymczasowe123!" }
```

Odpowiedź `201`: utworzony użytkownik (bez hasła).

### `PATCH /api/v1/uzytkownicy/{id}`

Zmiana roli, leśnictwa albo dezaktywacja: `{ "aktywny": false }`.

### `GET /api/v1/lesnictwa`

Lista leśnictw do formularza.

```json
[ { "id": 1, "nazwa": "Leśnictwo Dąbrowa" }, { "id": 2, "nazwa": "Leśnictwo Olszyny" } ]
```

---

## Do ustalenia @AgataSlusarczyk

- [ ] nazwy pól po polsku czy po angielsku? (tu po polsku, łatwo zmienić teraz, później będzie trudniej) chyba po angielsku miało być w kodzie na spokojnie
- [ ] domyślna długość wydania (wyciszenia), jeśli leśniczy nie poda: 4 h?
- [ ] czy wystarczy odświeżanie listy alarmów co X sekund, czy chcemy coś na żywo (WebSocket)? Na prototyp proponuję odświeżanie + push
- [ ] jak długo ma żyć token (propozycja: 24 h)
- [ ] czy nadleśniczy też dostaje pushe, czy tylko raporty - wydaje mi sięże tylko raporty

