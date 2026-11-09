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

## Dane

`GET /alarms?status=...` ([api.md, sekcja 4](../backend/api.md#4-alarmy)). Leśniczy dostaje alarmy swojego leśnictwa, nadleśniczy wszystkie. Backend sortuje od najnowszego.

- lista odświeża się **co 60 s**, tak jak mapa (`src/lib/refresh.ts`). Nowe alarmy mają też przychodzić pushem
- gdy odświeżenie się nie uda, lista zostaje, a nad nią pojawia się komunikat
- na mocku (`VITE_USE_MOCK=true`) są 4 alarmy: 3 w Leśnictwie Dąbrowa (`blazej`) i 1 w Olszynach

## Dalej

- odpowiedź leśniczego: **Kradzież** / **Fałszywy alarm** przy nowym alarmie
- adres `/alarms/41`, żeby powiadomienie push otwierało ten alarm
- szczegóły alarmu z mapką
