# Ochrona przed powtórką BOOT (`boot_id`)

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

## Zasady backendu

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

## Co musi robić firmware

1. Trzymać `boot_id` w pamięci nieulotnej (NVS), startować od 1.
2. Przy każdym starcie: odczytać, zwiększyć o 1, **zapisać**, dopiero potem wysłać BOOT z tym numerem.
3. Wysyłać ramki z wersją 2 w nagłówku (BOOT musi, pozostałe mogą).
4. Nigdy nie wracać do mniejszego numeru ani nie losować numeru: backend porównuje „czy większy”, a nie „czy już był”.

Zapis w pamięci nieulotnej następuje raz na start płytki, więc zużycie pamięci nie ma znaczenia.

## Konfiguracja i wdrażanie

- `BOOT_ID_REQUIRED` (domyślnie `false`): `true` odrzuca każdy BOOT bez `boot_id` ([konfiguracja.md](konfiguracja.md)).
- Kolejność: 1) wdrożyć backend (obsługuje obie wersje), 2) wgrać firmware z `boot_id` na wszystkie płytki, 3) ustawić `BOOT_ID_REQUIRED=true`. Czujnik zaczyna być chroniony po pierwszym BOOT-cie wersji 2, a przy `true` chronione są wszystkie.
- Symulator czujników wysyła BOOT wersji 2 i trzyma `boot_id` w pliku stanu (`--state`).
- Migracja `7d41b8c52e90` dodaje kolumnę `sensors.last_boot_id` (pusta dla czujników bez `boot_id`).

## Reset (admin)

`POST /api/v1/sensors/{id}/reset-boot` zapomina `last_boot_id` i licznik czujnika (odpowiedź `204`, tylko admin). Użyj po wymianie płytki, skasowaniu jej pamięci albo gdy pliku stanu symulatora nie ma, a baza pamięta wyższy numer. Następny BOOT czujnika zostanie przyjęty. To samo w SQL:

```sql
UPDATE sensors SET last_boot_id = NULL, last_counter = NULL WHERE id = '<DevEUI>';
```

## Warstwa szyfrowania (PR #68)

Moduł szyfrujący obcina dopełnienie zerami po odszyfrowaniu. Długość jawnej ramki trzeba brać z `frame_length(pierwszy_bajt)` z `app/protocol/decoder.py` (zależy od wersji i typu), a nie z `BODY[typ].size`, bo BOOT wersji 2 jest dłuższy.

## Czego to nie robi

`boot_id` zamyka powtórkę BOOT, ale **nie uwierzytelnia nadawcy**: ktoś, kto zna `X-Ingest-Key` i klucz AES, może wysłać BOOT z większym numerem. Uwierzytelnienie ramek (tag, CCM, klucze per czujnik) to osobny krok.
