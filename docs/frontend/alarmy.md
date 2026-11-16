# Lista alarmów

Leśniczy i nadleśniczy przełączają się w górnym pasku między **Mapa** i **Alarmy**. Admin tego widoku nie ma.

## Co widać

- przy przycisku **Alarmy** czerwona liczba: ile czujników ma otwarty alarm (bez odpowiedzi leśniczego). Liczy się z tej samej listy czujników co mapa, więc odświeża się razem z nią
- alarmy od najnowszego, każdy na osobnym kafelku:
  - nazwa czujnika (albo ID, gdy nie ma nazwy) i status: **Nowy** (czerwony), **Kradzież**, **Fałszywy alarm**
  - czas wykrycia, pewność w % i co zareagowało: dźwięk, wibracje
  - **„Możliwa manipulacja przy czujniku”**, gdy zareagowały same wibracje, bez dźwięku (`possible_tampering`)
  - po odpowiedzi leśniczego: kto i kiedy sprawdził oraz jego komentarz
- filtr nad listą: **Nowe** (domyślnie, bo na nie trzeba zareagować), Kradzież, Fałszywe, Wszystkie
- na telefonie tytuł w pasku jest ukryty, bo przyciski Mapa / Alarmy już pokazują, gdzie jesteśmy
- przyciski i tekst są duże (przyciski ok. 44–48 px wysokości), żeby dało się trafić kciukiem w terenie

## Odpowiedź na alarm

Pod każdym **nowym** alarmem leśniczy ma dwa przyciski: **Kradzież** i **Fałszywy alarm**.

1. stuknięcie przycisku nic jeszcze nie wysyła: pojawia się pytanie „Potwierdzasz kradzież?” / „Oznaczyć jako fałszywy alarm?” i pole na komentarz (opcjonalnie, do 500 znaków). Dzięki temu przypadkowe stuknięcie, np. w kieszeni, nie zamknie alarmu
2. **Zapisz** wysyła `POST /alarms/{id}/response` ([api.md, sekcja 4](../backend/api.md#4-alarmy)), **Wróć** wraca do wyboru
3. po zapisaniu nad listą pojawia się „Zapisano: Kradzież – Skład przy drodze 5”. Alarm nie jest już nowy, więc znika z filtra **Nowe**, a pod innymi filtrami ma nowy status i podpis, kto i kiedy go sprawdził
4. mapa od razu pobiera czujniki na nowo, więc znika czerwona liczba przy **Alarmy** i czerwona pinezka

- odpowiada tylko **leśniczy**. Nadleśniczy widzi listę bez przycisków (backend i tak zwróciłby mu `403`)
- gdy ktoś odpowiedział wcześniej (`409`), nad listą pojawia się „Alarm ma już odpowiedź”, a lista i mapa ładują się na nowo (znika licznik i czerwona pinezka)
- pozycji z telefonu (`lat`, `lon`) na razie nie wysyłamy. API ją przyjmuje jako dowód, że leśniczy był na miejscu, więc można ją dodać później

## Adres

Widok jest zapisany w adresie strony, więc działa przycisk **Wstecz** (w przeglądarce i na telefonie):

| Adres | Co widać |
|---|---|
| `/` | mapa |
| `/alarms` | lista alarmów |
| `/alarms/41` | lista z wyróżnionym alarmem 41 (czerwona ramka), przewinięta do niego |

- `/alarms/41` otwiera powiadomienie push: backend wysyła w nim `url` alarmu ([api.md](../backend/api.md))
- gdy alarm ma już odpowiedź, nie ma go pod **Nowe**, więc lista sama przełącza się na **Wszystkie** i tam go wyróżnia
- gdy alarmu nie ma nawet pod **Wszystkie** (zły numer albo alarm innego leśnictwa), nad listą pojawia się „Nie znaleziono alarmu 999…” z przyciskiem **OK**
- lista przewija się do alarmu tylko raz, po wejściu. Odświeżanie co 20 s już nie przewija, więc leśniczy może spokojnie przeglądać resztę
- nieznany adres pokazuje mapę
- po wylogowaniu adres wraca na `/`, żeby następna osoba na tym telefonie zaczynała od mapy
- serwer zwraca aplikację pod każdym adresem (`try_files` w `frontend/Caddyfile`), więc odświeżenie `/alarms/41` nie daje 404
- kod: `src/lib/route.ts`

## Dane

`GET /alarms?status=...` ([api.md, sekcja 4](../backend/api.md#4-alarmy)). Leśniczy dostaje alarmy swojego leśnictwa, nadleśniczy wszystkie. Backend sortuje od najnowszego.

- lista odświeża się **co 20 s**, tak jak mapa (`src/lib/refresh.ts`). Nowe alarmy mają też przychodzić pushem
- gdy odświeżenie się nie uda, lista zostaje, a nad nią pojawia się komunikat
- na mocku (`VITE_USE_MOCK=true`) są 4 alarmy: 3 w Leśnictwie Dąbrowa (`blazej`) i 1 w Olszynach

## Dalej

- szczegóły alarmu z mapką
- z dymka pinezki w stanie alarmu przejście do tego alarmu
- pozycja z telefonu przy odpowiedzi
