# Ochrona przed powtórkami (`boot_id`, ramka wersji 3)

**Stan obecny:** płytki wysyłają **ramki wersji 3** (`boot_id` w nagłówku każdej ramki). Backend przyjmuje też wersje 1 i 2, ale tylko **przejściowo** (`LEGACY_FRAMES`, patrz [Konfiguracja i wdrażanie](#konfiguracja-i-wdrażanie)). Wersja 2 jest opisana niżej, bo to ona wprowadziła `boot_id`, ale ma lukę, którą zamyka dopiero wersja 3.

## Problem

Każda ramka ma 16-bitowy licznik, który płytka zwiększa o 1. Backend odrzuca ramki z licznikiem nie większym niż ostatni (duplikaty i powtórki). Po restarcie płytki licznik zaczyna od nowa, dlatego płytka wysyła **BOOT**, a backend po BOOT zapomina ostatni licznik i przyjmuje nowy.

Ta furtka pozwalała obejść ochronę przed powtórkami: ktoś, kto podsłuchał dowolny BOOT, mógł go wysłać ponownie, żeby zresetować licznik czujnika, a potem powtórzyć dawniej podsłuchane ALARM-y (backend uznawał je znowu za nowe). Szyfrowanie samo tego nie naprawia, bo identyczny BOOT daje identyczny szyfr.

## Rozwiązanie: ramka wersji 2

BOOT dostaje pole `boot_id` (2 B): numer uruchomienia, który płytka zwiększa **przy każdym starcie** i zapisuje w pamięci nieulotnej. Backend pamięta największy przyjęty `boot_id` czujnika (`sensors.last_boot_id`) i odrzuca BOOT, którego numer nie jest większy.

| | wersja 1 | wersja 2 |
|---|---|---|
| nagłówek (3 B) | `0x1T`, licznik | `0x2T`, licznik (`T` = typ: 1 ALARM, 2 HEARTBEAT, 3 BOOT) |
| ALARM, HEARTBEAT | bez zmian | **taki sam układ**, tylko wersja w nagłówku |
| BOOT: bajty po nagłówku | firmware, przyczyna, bateria (3 B, razem 6 B) | firmware, przyczyna, bateria, **`boot_id`** (5 B, razem 8 B) |

Przykład: `23 0001 01 01 58 002A` to BOOT wersji 2, licznik 1, firmware 1, włączenie zasilania, bateria 88%, `boot_id` 42. Backend przyjmuje obie wersje.

## Zasady backendu (wersja 2, przejściowo)

| Sytuacja | Wynik |
|---|---|
| pierwszy BOOT z `boot_id` | przyjęty, numer zapamiętany |
| `boot_id` większy niż zapamiętany | przyjęty, licznik zaczyna od nowa, numer zapamiętany |
| `boot_id` równy lub mniejszy | **powtórka**: `200 duplicate`, licznik się **nie** resetuje, nic nie zapisano |
| przekręcenie 65535 → 0 | w porządku (arytmetyka modulo 2^16, jak przy liczniku) |
| skok o więcej niż 32768 do przodu | traktowany jak stary numer (powtórka) |
| BOOT wersji 1 od czujnika, który już wysłał `boot_id` | `422`: inaczej stary BOOT wersji 1 wystarczyłby, żeby zresetować licznik |
| BOOT wersji 1 od czujnika, który nie wysłał jeszcze `boot_id` | przyjęty jak dotąd (okres przejściowy) |
| BOOT wersji 1 przy `BOOT_ID_REQUIRED=true` | `422` |

Po wymianie płytki lub skasowaniu jej pamięci numer zaczyna od 1, co wygląda jak powtórka (patrz „Reset”).

## Luka wersji 2

`boot_id` w BOOT chroni przed powtórką **samego BOOT-a**, ale nie przed powtórką ramek z poprzedniej sesji po **prawdziwym** restarcie płytki:

| Krok | Co się dzieje | Licznik w backendzie |
|---|---|---|
| 1 | BOOT, `boot_id` 1 | 1 |
| 2 | prawdziwy ALARM, licznik 50 (ktoś go nagrywa) | 50 |
| 3 | prawdziwy restart: BOOT, `boot_id` 2 | **1** (po BOOT od nowa) |
| 4 | ktoś odtwarza nagrany ALARM z licznikiem 50 | 50 > 1, **przyjęty** |

ALARM i HEARTBEAT wersji 2 nie mówią, z której sesji pochodzą, więc backend nie odróżni starej ramki od nowej. Szyfrowanie nie pomaga: nagrany pakiet zaszyfrowała prawdziwa płytka.

## Ramka wersji 3

`boot_id` (2 B) jest w **nagłówku każdej ramki**, przed licznikiem. Para (`boot_id`, licznik) mówi, z której sesji i z którego miejsca w niej jest ramka, a backend przyjmuje tylko pary nowsze niż ostatnio przyjęta.

| | wersje 1 i 2 | wersja 3 |
|---|---|---|
| nagłówek | `wersja\|typ` (1 B), licznik (2 B) = 3 B | `wersja\|typ` (1 B), **`boot_id` (2 B)**, licznik (2 B) = **5 B** |
| BOOT: treść | firmware, przyczyna, bateria (v2: + `boot_id`) | firmware, przyczyna, bateria (`boot_id` jest w nagłówku) |
| HEARTBEAT, ALARM: treść | bateria, odrzucone, flagi / rodzaj, źródło, pewność, czas, energia, bateria | bez zmian |
| długość | BOOT 6 (v2: 8), HEARTBEAT 6, ALARM 10 | **BOOT 8, HEARTBEAT 8, ALARM 12** |

Przykłady (`boot_id` 42):

```
BOOT       33 002A 0001 01 01 58               licznik 1, firmware 1, włączenie, bateria 88%
HEARTBEAT  32 002A 0002 58 00 00               licznik 2, bateria 88%
ALARM      31 002A 0003 01 03 5A 003C C8 58    licznik 3, mikrofon + wibracje, pewność 90, 60 s, energia 200, bateria 88%
```

Wszystkie ramki mieszczą się w jednym bloku AES (16 B), więc [szyfrowanie](szyfrowanie.md) działa bez zmian.

### Zasady backendu (wersja 3)

Jedna zasada dla wszystkich typów (`is_replay` w `app/services/ingest.py`). BOOT nie ma wyjątku: to zwykła pierwsza ramka nowej sesji.

| Ostatnio przyjęte (`boot_id`, licznik) | Nowa ramka | Wynik |
|---|---|---|
| brak (pierwszy kontakt albo po resecie) | dowolna | przyjęta |
| (5, 10) | (5, 11) | przyjęta: ta sama sesja, licznik rośnie |
| (5, 10) | (5, 10) lub (5, 9) | `200 duplicate` |
| (5, 10) | (6, 1) | przyjęta: nowa sesja (restart), licznik od nowa |
| (5, 10) | (6, 500) | przyjęta: nowa sesja, nawet gdy BOOT zginął w radiu |
| (5, 10) | (4, 50) | **`200 duplicate`: ramka z poprzedniej sesji (luka wersji 2 zamknięta)** |

Porównania są modulo 2^16 (przekręcenie 65535 → 0 jest w porządku), a skok do przodu o więcej niż 32768 traktujemy jak starą wartość. Po przyjęciu ramki backend zapisuje `sensors.last_boot_id` i `sensors.last_counter`. Kolumny są już z wersji 2, więc wersja 3 nie wymaga migracji.

Przejście czujnika z wersji 2 na 3 działa samo: płytka po aktualizacji wystartuje z większym `boot_id` niż ostatni BOOT wersji 2.

## Co musi robić firmware

1. Trzymać `boot_id` w pamięci nieulotnej (NVS), startować od 1.
2. Przy każdym starcie: odczytać, zwiększyć o 1, **zapisać**, dopiero potem wysłać cokolwiek.
3. Wysyłać **wszystkie** ramki w wersji 3, z tym `boot_id` w nagłówku.
4. Licznik zaczyna od 1 w każdej sesji (po każdym starcie) i rośnie o 1 przy każdej ramce.
5. Nigdy nie wracać do mniejszego numeru ani nie losować numeru: backend porównuje „czy nowszy”, a nie „czy już był”.

Zapis w pamięci nieulotnej następuje raz na start płytki, więc zużycie pamięci nie ma znaczenia.

## Konfiguracja i wdrażanie

- `LEGACY_FRAMES` (domyślnie `true`): przyjmuj ramki wersji 1 i 2. `false` odrzuca je z `422`, przyjmowana jest tylko wersja 3 ([konfiguracja.md](konfiguracja.md)).
- `BOOT_ID_REQUIRED` (domyślnie `false`, dotyczy tylko wersji 1 i 2): `true` odrzuca każdy BOOT bez `boot_id`.
- Kolejność: 1) wdrożyć backend (obsługuje wersje 1, 2 i 3, `LEGACY_FRAMES=true`), 2) wgrać firmware wersji 3 na wszystkie płytki, 3) gdy w bazie nie ma już nowych ramek wersji 1 ani 2 (`SELECT DISTINCT decoded->'header'->>'version' FROM messages WHERE received_at > now() - interval '1 day';`), ustawić `LEGACY_FRAMES=false` i zrestartować backend.
- **W okresie przejściowym** (`LEGACY_FRAMES=true`) czujnik, który już wysyła wersję 3, nie jest w pełni chroniony: nagraną dawniej ramkę ALARM lub HEARTBEAT wersji 1 albo 2 z licznikiem większym niż ostatni backend przyjmie. Dlatego `LEGACY_FRAMES=true` nie powinno zostawać dłużej niż trzeba.
- Symulator czujników domyślnie wysyła wersję 3 i trzyma `boot_id` w pliku stanu (`--state`). `--frame-version 2` wysyła jak dawniej.
- Dane demo (`seed --demo`) to ramki wersji 3 z `boot_id` 0, więc symulator (od `boot_id` 1) zaczyna nowszą sesję.
- Migracja `7d41b8c52e90` dodaje kolumnę `sensors.last_boot_id` (pusta dla czujników bez `boot_id`). Wersja 3 nie dodaje migracji.

## Reset (admin)

`POST /api/v1/sensors/{id}/reset-boot` zapomina `last_boot_id` i licznik czujnika (odpowiedź `204`, tylko admin). Użyj po wymianie płytki, skasowaniu jej pamięci albo gdy pliku stanu symulatora nie ma, a baza pamięta wyższy numer. Następna ramka czujnika (w wersji 3 dowolna, w wersji 2 BOOT) zostanie przyjęta. To samo w SQL:

```sql
UPDATE sensors SET last_boot_id = NULL, last_counter = NULL WHERE id = '<DevEUI>';
```

## Warstwa szyfrowania (PR #68)

Po odszyfrowaniu backend obcina dopełnienie zerami według `frame_length(pierwszy_bajt)` z `app/protocol/decoder.py` (zależy od wersji i typu), więc zaszyfrowany BOOT wersji 2 (8 B) i ramki wersji 3 (8 i 12 B) zachowują `boot_id`. Opis szyfrowania: [szyfrowanie.md](szyfrowanie.md).

## Czego to nie robi

Wersja 3 zamyka powtórki starych ramek, ale **nie uwierzytelnia nadawcy**: ktoś, kto zna `X-Ingest-Key` i klucz AES, może wysłać ramkę z większym `boot_id`. Uwierzytelnienie ramek (tag, CCM, klucze per czujnik) to osobny krok.
