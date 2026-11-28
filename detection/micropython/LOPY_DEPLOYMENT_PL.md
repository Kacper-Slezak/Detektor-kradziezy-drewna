# Wdrożenie i diagnostyka jednopilkowego firmware `main.py` na Pycom LoPy 1.0

Instrukcja wdrożeniowa i diagnostyczna dla **Pycom LoPy 1.0 (ESP32 @ 160 MHz)** z firmware **Pycom 1.20.2.r6 (MicroPython v1.11, commit `c5a0a97`, 2021-10-28)**.

Na urządzenie wgrywany jest **wyłącznie jeden samodzielny plik `main.py`** — bez osobnych modułów detekcji, zewnętrznych plików wag ani katalogu `/flash/lib/`. Oryginalny katalog `firmware/` w repozytorium pozostaje nienaruszony (tylko do odczytu).

---

## 1. Dwa gotowe, samodzielne pliki `main.py`

| Wariant | Ścieżka pliku | Rozmiar | Wagi w bajtkodzie | Status RAM (sterta 57 872 B Safe Boot) |
|---|---|---:|---|---|
| **Burst MLP (kompaktowy produkcyjny)** | `detection/micropython/deploy/burst/main.py` | `17 768 B` (~17,4 KiB) | surowe `bytes` (`528 B` INT8) | **Rekomendowany** (o 4,5 KB mniejszy niż poprzednio uruchomiona wersja `22 244 B`) |
| **CNN v4.6** *(bez zmian na tym etapie)* | `detection/micropython/deploy/cnn_v46/main.py` | `83 818 B` (~81,9 KiB) | surowe `bytes` (`13 072 B` INT8) | **Wysokie ryzyko `MemoryError` jako `.py`** |

### Regeneracja kompaktowego Burst MLP
```powershell
python detection/micropython/deploy/build_standalone_firmware.py --burst-only
```

---

## 2. Najważniejsze poprawki względem `firmware/main4.py` (Pycom 1.20.2.r6)

1. **Deep Sleep API (`AttributeError: pin_deepsleep_wakeup`):** zastąpiono nieistniejące `machine.pin_deepsleep_wakeup` zweryfikowanym w Pycom 1.20.2.r6 wywołaniem `machine.pin_sleep_wakeup(['P19', 'P20'], mode=machine.WAKEUP_ANY_HIGH, enable_pull=czy_pull)` oraz dodano ochronę przed nieskończoną pętlą wybudzeń przy stale wysokim stanie pinu (przejście w sen czasowy).
2. **Usunięto podwójne nagrywanie:** wyeliminowano pustą pętlę `for blok_audio in nagraj_audio(): pass` z `main()`. W `STAN 2` urządzenie nagrywa i analizuje audio **dokładnie raz** (10 bloków × 1 s, 8000 B współdzielony `bytearray`).
3. **Zgodność z MicroPython v1.11 (`array`):** usunięto nieobsługiwane `array(...) * int` oraz generatory w `array(...)` — wszystkie bufory alokowane są jednym blokiem przez `array(tc, range(n))` z zerowaniem w miejscu.
4. **Pierwszy start NVS:** brakujące klucze `boot_id` / `pkt_cnt` (`ValueError` / `OSError: No matching object for the provided key`) są obsługiwane bez błędu jako normalne pierwsze uruchomienie.
5. **Odporność sieciowa i HTTP:** błędy Wi-Fi (`Connection to AP Timeout!`), zerwane gniazda oraz kody HTTP spoza zakresu `200..299` są bezpiecznie obsługiwane i nie przerywają działania maszyny stanów. Przed wywołaniem Wi-Fi wykonywane jest `gc.collect()` po zwolnieniu buforów detekcji.
6. **Fail-closed:** błąd ADC lub brak poprawnych bloków audio nigdy nie jest raportowany jako poprawne tło i nie wysyła fałszywego alarmu.
7. **Tryb diagnostyczny (`tryb_diagnostyczny()`):** pozwala przetestować pełny tor detekcji na syntetycznych blokach ADC (8000 B, 12-bit LE) bez mikrofonu, Wi-Fi, backendu i Deep Sleep.

---

## 3. Wymagania sprzętowe — mikrofon analogowy vs cyfrowy I2S

- Firmware `nagraj_audio()` obsługuje **wyłącznie mikrofon analogowy** (wyjście analogowe `AO` na pinie ADC1 `P16`, opcjonalne wyjście cyfrowe `DO` na `P19`).
- Zainstalowane firmware **Pycom 1.20.2.r6 nie udostępnia `machine.I2S`**. Cyfrowy mikrofon I2S podłączony obecnie do płytki **nie może** być odczytywany przez `ADC`.
- Do testów bez mikrofonu analogowego należy użyć wbudowanego trybu `tryb_diagnostyczny()`.

---

## 4. Ręczne wgranie i weryfikacja (PowerShell + REPL)

> **Uwaga pamięciowa:** po normalnym starcie `main.py` nie wywołuj ponownie `import main` w tej samej sesji REPL (może to wywołać `MemoryError` przez podwójne załadowanie modułu). Do testu z REPL wykonaj najpierw miękki reset (`Ctrl+D` lub Safe Boot).

### Krok 1 — wgranie pliku `main.py` przez `ampy` (PowerShell)
```powershell
# Wariant Burst MLP (zalecany pierwszy test):
ampy --port COM4 --baud 115200 put detection\micropython\deploy\burst\main.py /flash/main.py

# Opcjonalnie wgranie lekkiej sondy zgodnosci REPL:
ampy --port COM4 --baud 115200 put detection\micropython\deploy\lopy_compat_probe.py /flash/lopy_compat_probe.py
```

### Krok 2 — szybka weryfikacja zgodności API w REPL (opcjonalnie)
```python
import lopy_compat_probe
lopy_compat_probe.run()
```

### Krok 3 — uruchomienie trybu diagnostycznego (bez Wi-Fi, bez Deep Sleep, syntetyczne ADC)
W REPL (po przerwaniu normalnego startu przez `Ctrl+C` lub po ustawieniu `TRYB_DIAGNOSTYCZNY = True` na czas testu):
```python
import gc
gc.collect()
print("HEAP_BEFORE:", gc.mem_free())
import main
main.tryb_diagnostyczny(liczba_blokow=10)
```
Oczekiwany wynik: wypisane `DIAG_TIME_MS`, `DIAG_HEAP_END`, `DIAG_RESULT: (czy_alarm, event_type, confidence)` oraz `DIAG_META`, bez próby połączenia z Wi-Fi i bez wejścia w Deep Sleep.

### Krok 4 — normalny start (po ustawieniu `WIFI_SSID`, `WIFI_HASLO`, `INGEST_KEY`)
Po twardym resecie (przycisk Reset) urządzenie przejdzie przez `STAN 3` (wysyłka ramki `MSG_BOOT` lub bezpieczna obsługa braku Wi-Fi), a następnie wejdzie w `idz_spac_na_czujniki()` przez `machine.pin_sleep_wakeup(...)` i `machine.deepsleep()`.

---

## 5. Szacowane wymagania pamięciowe (RAM)

| Składnik | Burst MLP (`deploy/burst/main.py`) | CNN v4.6 (`deploy/cnn_v46/main.py`) |
|---|---:|---:|
| Wolna sterta po Safe Boot *(zmierzone)* | `57 872 B` | `57 872 B` |
| Rozmiar `main.py` w flash *(zmierzone)* | `29 228 B` (~28,5 KiB) | `83 818 B` (~81,9 KiB) |
| Szacowana wolna sterta po załadowaniu `main.py` | `~36–40 KB` *(poprzednio zmierzono `41 024 B` przy 22 KB)* | `~10–20 KB` *(wysokie ryzyko `MemoryError` przy kompilacji)* |
| Bufory w trakcie `analizuj_sygnaly()` + `8 000 B` audio | `~19 900 B` | `~32 000 B` |
| **Ocena zmieszczenia się w RAM** | **Realistyczny zapas (~16–20 KB w trakcie inferencji)** | **Prawdopodobne `MemoryError` jako `.py` bez `.mpy`/frozen** |

---

## 6. Status walidacji fizycznej

- **Status: OCZEKUJĄCA (pending)** — weryfikacja fizyczna na płytce Pycom LoPy 1.0 zostanie wykonana ręcznie (nie łączono się z `COM4`).
- **Testy automatyczne na PC (CPython 3.11.9):** `39/39` testów zaliczonych (`tests.test_standalone_firmware`, `tests.test_stream_detector`, `tests.test_v46`, `tests.test_burst`, `tests.test_cleanup`).
