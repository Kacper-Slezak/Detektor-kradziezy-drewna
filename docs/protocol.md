# Protokół: ramki urządzenie → serwer

Stan na 25.11.2026: ramka **wersji 3** (od PR #79), szyfrowanie AES-128 (PR #68), backend w `backend/app/protocol/` (`decoder.py`, `encoder.py`) i `backend/app/services/ingest.py`. Szczegóły w osobnych dokumentach: [backend/boot-id.md](backend/boot-id.md) (powtórki, `boot_id`), [backend/szyfrowanie.md](backend/szyfrowanie.md) (AES), [testowanie.md](testowanie.md) (ręczne wysyłanie ramek, odpowiedzi `/ingest`).

Ten dokument to przegląd całości: co jest w ramce, co robi z nią serwer i co jeszcze jest otwarte. Gdy zmieniasz protokół, zmieniasz dekoder, koder i ten plik w jednym PR.

## Ustalenia

- **Łączność.** Dziś płytka łączy się przez Wi-Fi i wysyła ramkę na `POST /api/v1/ingest` (testy, pokaz). Docelowo LoRaWAN przez TTN: bramka przekazuje ramkę webhookiem do backendu (adaptera `/ingest/ttn` jeszcze nie ma). **Ramka jest ta sama** w obu drogach, różni się tylko opakowanie.
- **Komunikacja jednostronna.** Tylko urządzenie → serwer, bez komend w dół (oszczędność prądu, bez nasłuchiwania). Odpowiedź leśniczego i wydania zostają na serwerze.
- **Czujniki:** mikrofon i czujnik drgań. Akcelerometru nie ma (spotkanie 15.10).
- **Detekcja na urządzeniu.** Wysyłamy wynik i kilka liczb, bez surowego dźwięku.
- **Lokalizacja** z telefonu leśniczego przy montażu (`PUT /sensors/{id}/mount`), nie w ramce.
- **Legalny wywóz** to wydanie w aplikacji. W tym czasie backend odrzuca alarmy czujnika. Płytka o wydaniu nie wie.

## Ogólnie

- **Bajty, nie JSON.** Kolejność bajtów big-endian.
- **Najwyżej 16 B**, czyli jeden blok AES. Ramki wersji 3 mają 8–12 B.
- **Czego nie ma w ramce**, bo daje to droga przesyłu: ID urządzenia (DevEUI, pole `device` w `/ingest`), czas odbioru (`received_at`, bez niego „teraz”) i RSSI.
- **Budżet radiowy LoRaWAN:** TTN daje ok. 30 s nadawania na dobę, przy SF12 jedna ramka to ok. 1 s, czyli **ok. 25 ramek na dobę** w najgorszym przypadku. Heartbeat co ~6 h (4/dobę) i alarmy (3 ramki na zdarzenie) się mieszczą.

## Szyfrowanie

Przy ustawionym `FRAME_AES_KEY` urządzenie dopełnia jawną ramkę **zerami** do 16 B, szyfruje ją AES-128-ECB i wysyła 32 znaki hex. Backend odszyfrowuje, sprawdza, że dopełnienie to same zera, i dekoduje. Jawna ramka albo zły klucz → `422`.

Własne szyfrowanie zostaje także przy LoRaWAN: LoRaWAN szyfruje kluczem, który zna serwer aplikacji TTN, a nasz klucz zna tylko płytka i nasz backend. Szczegóły i wektory testowe: [backend/szyfrowanie.md](backend/szyfrowanie.md).

**Ograniczenie:** nie ma podpisu (MIC). Zera w dopełnieniu odrzucają losowe pakiety, ale kto zna klucz, zbuduje dowolną ramkę.

## Nagłówek (wersja 3, 5 B)

| bajt | pole | uwagi |
|---|---|---|
| 0, górne 4 bity | wersja | wersja **formatu ramki**: 3. Wersje 1 i 2 backend przyjmuje tylko przejściowo (`LEGACY_FRAMES=true`) |
| 0, dolne 4 bity | typ | 1 ALARM, 2 HEARTBEAT, 3 BOOT |
| 1–2 | `boot_id` | numer uruchomienia płytki: +1 przy każdym starcie, trzymany w pamięci nieulotnej (NVS) |
| 3–4 | licznik | +1 przy każdej ramce, od 1 w każdej sesji (po każdym starcie) |

Np. `0x31` = wersja 3, typ 1 (ALARM). Para (`boot_id`, licznik) mówi, z której sesji i z którego miejsca w niej jest ramka. Backend przyjmuje tylko pary nowsze niż ostatnio przyjęta, więc duplikaty i powtórki nagranych ramek (także z poprzedniej sesji) odrzuca ([backend/boot-id.md](backend/boot-id.md)).

## Typy ramek

| typ | nazwa | kiedy | długość (v3) |
|---|---|---|---|
| 1 | ALARM | wykryto kradzież; wysyłany 3 razy, potem blokada | 12 B |
| 2 | HEARTBEAT | co ~6 h: „żyję” + bateria | 8 B |
| 3 | BOOT | po włączeniu albo restarcie | 8 B |

### ALARM (12 B)

| bajt | pole | uwagi |
|---|---|---|
| 0–4 | nagłówek | |
| 5 | rodzaj zdarzenia | backend zna dziś `1` = kradzież (`EVENT_TYPES` w `backend/app/schemas.py`), inne pokazuje jako `unknown`. Listę ustala Kiryl |
| 6 | źródło (bity) | bit0 = mikrofon, bit1 = drgania. **Same drgania** backend i aplikacja pokazują jako „możliwa manipulacja przy czujniku” (`Alarm.possible_tampering`) |
| 7 | pewność 0–100 | wartość > 100 → `422`. Skalę ustala Kiryl |
| 8–9 | czas trwania [s] | stuknięcie czy kilka minut załadunku |
| 10 | energia 0–255 | głośność / siła zdarzenia, dla leśniczego „blisko czy daleko” |
| 11 | bateria % | > 100 → `422` |

### HEARTBEAT (8 B)

| bajt | pole | uwagi |
|---|---|---|
| 0–4 | nagłówek | |
| 5 | bateria % | poniżej 20% (`BATTERY_LOW_PCT`) leśniczy dostaje push „Słaba bateria” |
| 6 | odrzucone zdarzenia | ile razy płytka się obudziła i uznała, że to nie kradzież (dane dla Kiryla, zapisywane, na razie nieużywane) |
| 7 | flagi | bit0 zablokowany (po alarmie), bit1 niska bateria (też daje push), bit2 błąd czujnika. Bit0 i bit2 backend na razie tylko zapisuje |

### BOOT (8 B)

| bajt | pole | uwagi |
|---|---|---|
| 0–4 | nagłówek | `boot_id` nowej sesji, licznik zwykle 1 |
| 5 | wersja firmware | |
| 6 | przyczyna restartu | 1 włączenie, 2 watchdog, 3 za niskie napięcie. Częste restarty przez watchdog to bug |
| 7 | bateria % | |

### Przykłady (`boot_id` 42)

```
BOOT       33 002A 0001 01 01 58               licznik 1, firmware 1, włączenie, bateria 88%
HEARTBEAT  32 002A 0002 58 00 00               licznik 2, bateria 88%
ALARM      31 002A 0003 01 03 5A 003C C8 58    licznik 3, kradzież, mikrofon + drgania, pewność 90, 60 s, energia 200, bateria 88%
```

Złożenie i odczytanie ramki koderem i dekoderem backendu: [testowanie.md](testowanie.md), sekcja 4.

## Co musi robić firmware

1. Przy każdym starcie: odczytać `boot_id` z NVS, zwiększyć o 1, **zapisać**, dopiero potem cokolwiek wysłać. Zacząć od 1, nigdy nie cofać ani nie losować.
2. Licznik od 1 w każdej sesji, +1 przy **każdej** ramce, także przy powtórzeniach ALARM (ramka z tym samym licznikiem to duplikat).
3. Wysyłać wszystkie ramki w wersji 3.
4. Z `FRAME_AES_KEY`: dopełnić zerami do 16 B, zaszyfrować AES-128-ECB.
5. Po wykryciu: ALARM 3 razy z odstępem, potem blokada (niżej).

## Alarm i blokada

Komunikacja jest jednostronna, więc urządzenie nie wie, czy alarm doszedł. Dlatego wysyła ALARM **3 razy** z odstępem, każdy z nowym licznikiem. Backend scala ramki ALARM czujnika z 10 minut (`ALARM_MERGE_WINDOW_S`) w jeden alarm (pole `repeats`) i wysyła jeden push.

Potem urządzenie **blokuje się** do upływu timeoutu (np. 1 h), bo kradzież trwa kilkanaście minut i nie ma sensu alarmować co chwilę z tego samego miejsca.

```
SEN --dźwięk/drgania--> ANALIZA --kradzież--> ALARM x3 --> ZABLOKOWANY
 ^                         |                                  |
 |-------nie kradzież------|                                  |
 |----------------------- timeout (np. 1 h) ------------------|
```

Odpowiedź leśniczego („kradzież” / „fałszywy alarm”) nie idzie do urządzenia. Zamyka alarm w aplikacji i jest etykietą dla Kiryla.

## Co robi serwer (`POST /api/v1/ingest`)

Zapytanie: `{"device": "<DevEUI>", "payload_hex": "<ramka>", "received_at": "…", "rssi": -112}` (dwa ostatnie pola opcjonalne), nagłówek `X-Ingest-Key`.

1. Sprawdza `X-Ingest-Key` (`INGEST_API_KEY`); zły albo brak → `401`.
2. Przy `FRAME_AES_KEY`: odszyfrowuje i sprawdza dopełnienie; jawna ramka albo zły klucz → `422`.
3. Dekoduje: wersja, typ, długość, wartości procentowe; błąd → `422`. Wersja 1 lub 2 przy `LEGACY_FRAMES=false` → `422`.
4. Szuka czujnika po `device`; nieznany → `404`.
5. Sprawdza parę (`boot_id`, licznik); nie nowsza niż ostatnia → `200 duplicate`, nic nie zapisuje. Przeskok licznika zapisuje w logu jako zgubione ramki.
6. Zapisuje ramkę w `messages` (także gdy alarm jest wyciszony) i stan czujnika: `last_seen`, bateria, `boot_id`, licznik.
7. ALARM: gdy czujnik jest wyłączony albo trwa wydanie, alarm nie powstaje (`muted: true`). W przeciwnym razie dokleja ramkę do otwartego alarmu z ostatnich 10 min albo tworzy nowy.
8. Po odpowiedzi płytce wysyła push do leśniczych leśnictwa czujnika: nowy alarm, słaba bateria.

Bez żadnej ramki backend wysyła też push „Brak kontaktu” po 12 h ciszy (`SENSOR_SILENT_AFTER_H`) i „Koniec wydania”, gdy wyciszenie się skończy ([backend/api.md](backend/api.md), sekcja 6).

Przykład: ALARM z przykładu wyżej po dekodowaniu (`to_dict`, tak trafia do `messages.decoded`):

```json
{
  "header": {"version": 3, "msg_type": "ALARM", "counter": 3, "boot_id": 42},
  "event_type": 1,
  "sources": ["microphone", "vibration"],
  "confidence": 90,
  "duration_s": 60,
  "energy": 200,
  "battery_pct": 88
}
```

Kody odpowiedzi `/ingest`: [testowanie.md](testowanie.md), sekcja 4.

## Filtrowanie na serwerze

**Działa:**
- wydanie drewna wycisza alarmy czujnika na czas wywozu,
- wyłączony czujnik nie daje alarmów,
- powtórzenia ALARM scalane w jeden alarm,
- same drgania oznaczone jako możliwa manipulacja.

**Pomysły, nie zrobione:**
- alarmy z wielu czujników naraz → raczej wichura albo burza,
- czujnik, który często daje fałszywe alarmy (wg odpowiedzi leśniczych) → niższa ocena,
- odpowiedzi leśniczych jako dane do strojenia algorytmu Kiryla (już zapisywane przy alarmie, eksport w raporcie CSV).

## Do ustalenia

- [x] ~~Damian: licznik czy FCnt LoRaWAN?~~ Licznik 2 B w ramce, bo droga Wi-Fi nie ma FCnt, plus `boot_id` w NVS (wersja 3).
- [x] ~~Wojtek / Damian: akcelerometr?~~ Czujnik drgań. Manipulacja = alarm z samych drgań.
- [x] ~~szyfrowanie~~ AES-128 z `FRAME_AES_KEY`, bo droga Wi-Fi nie ma szyfrowania LoRaWAN.
- [ ] **Kiryl:** lista rodzajów zdarzeń (bajt 5) i skala pewności (bajt 7).
- [ ] **wszyscy:** timeout blokady i co ile heartbeat, gdy zmierzymy zużycie baterii. Uwaga: płytka nie wie o wydaniu, więc w trakcie legalnego wywozu wyśle alarm (backend go odrzuci) i zablokuje się; jeśli po końcu wydania maszyna dalej pracuje, następny alarm przyjdzie dopiero po timeoucie.
- [ ] **Damian, Martyna:** firmware wysyła wersję 3 z szyfrowaniem; potem na serwerze `LEGACY_FRAMES=false`.
- [ ] **Kacper:** adapter TTN `POST /api/v1/ingest/ttn` (webhook: DevEUI, `frm_payload` w base64, czas, RSSI) na ten sam `ingest()`.
- [ ] **później:** uwierzytelnienie ramek (MIC, np. AES-CMAC albo AES-CCM) zamiast samego szyfrowania.
