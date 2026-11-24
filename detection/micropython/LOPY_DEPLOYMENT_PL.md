# Wdrożenie i test dymny na fizycznym Pycom LoPy 1.0 (`COM4`)

Instrukcja dla programisty firmware opisująca minimalne pakiety wdrożeniowe, wgrywanie plików przez port szeregowy (`COM4`, `115200`) oraz uruchomienie samodzielnego testu dymnego (`lopy_demo.py`) bez modyfikacji `main.py` i `boot.py`.

> **Bezpieczeństwo urządzenia:** narzędzie [lopy_tool.py](deploy/lopy_tool.py) blokuje nadpisywanie `/flash/main.py` oraz `/flash/boot.py` i wgrywa pliki wyłącznie do osobnego katalogu `/flash/tg_demo/`. Nie wymaga kasowania pamięci flash ani zmiany firmware.

---

## 1. Dwie niezależne konfiguracje wdrożeniowe

Pakiety są generowane skryptem [build_packages.py](deploy/build_packages.py) z katalogu `detection/micropython/`:

```powershell
python deploy/build_packages.py
```

Nie należy ładować obu modeli jednocześnie w pamięci RAM.

### Konfiguracja 1: Burst MLP — `deploy/burst/` *(kandydat niskopamięciowy)*
Zawiera wyłącznie 4 pliki (~47 KB w flash):
- `tg_stream_detector.py` — strumieniowy adapter ADC (`Detector`), leniwy import backendu.
- `tg_burst.py` — FFT 512 pkt i klasyfikator MLP.
- `tg_model_burst.py` — wytrenowane wagi Burst MLP (`3 988 B`, 528 wag INT8).
- `lopy_demo.py` — samodzielny skrypt demonstracyjny (generuje syntetyczne bloki 8000 B w RAM).

### Konfiguracja 2: CNN v4.6 (strumieniowane wagi binarne) — `deploy/cnn_v46/` *(model preferowany)*
Zawiera wyłącznie 4 pliki (~52 KB w flash):
- `tg_stream_detector.py` — adapter z fuzją Conv2D+ReLU+Pooling (bez tensora `conv` 12 KB), połówkową tablicą Hanna (oszczędność 2 KB) oraz strumieniowym odczytem warstwy gęstej z flash (wierszami po 201 B zamiast 12 864 B + 17,5 KB base64 w RAM).
- `tg_model_v46_bin.py` — metadane i progi v4.6 (`2 274 B`, bez zmian wag).
- `tg_v46_weights.bin` — dokładnie te same wytrenowane wagi INT8 (`13 072 B`: `wc` + transponowane `wd` + `wo`).
- `lopy_demo.py` — samodzielny skrypt demonstracyjny.

Weryfikacja zgodności numerycznej (PC): `tg_model_v46_bin.py` + `tg_v46_weights.bin` daje identyczne wyniki (`model_scores`) jak oryginalny `tg_model_v46.py`.

---

## 2. Polecenia PowerShell (wgrywanie i uruchomienie na `COM4`)

Wszystkie polecenia wykonuj z katalogu `detection/micropython/` (wymagany Python z `pyserial`; przed uruchomieniem zamknij inne terminale korzystające z `COM4`, np. PuTTY, Pymakr, Thonny).

### Krok 1 — sprawdzenie płytki, wolnego RAM i plików na `/flash`
```powershell
python deploy/lopy_tool.py --port COM4 info
```

### Krok 2 — wgranie i uruchomienie testu **Burst MLP**
```powershell
python deploy/lopy_tool.py --port COM4 upload-dir deploy/burst /flash/tg_demo
python deploy/lopy_tool.py --port COM4 run --reset --timeout 120 "import sys; sys.path.insert(0, '/flash/tg_demo'); import lopy_demo; lopy_demo.run('burst', 10)"
```

### Krok 3 — wgranie i uruchomienie testu **CNN v4.6** (po resecie sterty)
```powershell
python deploy/lopy_tool.py --port COM4 upload-dir deploy/cnn_v46 /flash/tg_demo
python deploy/lopy_tool.py --port COM4 run --reset --timeout 180 "import sys; sys.path.insert(0, '/flash/tg_demo'); import lopy_demo; lopy_demo.run('cnn_v46', 10)"
```

---

## 3. Co mierzy `lopy_demo.py`

Skrypt nie wymaga mikrofonu, czujnika drgań, Wi-Fi ani backendu. Dla 10 bloków po 8000 B (4000 próbek `uint16` LE 12-bit, jeden współdzielony `bytearray`) wypisuje na konsolę szeregową:
- `HEAP_BEFORE_IMPORT` — wolny heap przed importem detektora,
- `HEAP_AFTER_IMPORT` — po imporcie `tg_stream_detector`,
- `HEAP_AFTER_MODEL` — po załadowaniu modelu,
- `HEAP_AFTER_DETECTOR_INIT` — po utworzeniu `Detector(model=...)`,
- `HEAP_AFTER_BUFFERS` — po alokacji współdzielonego bufora `bytearray(8000)`,
- `BLOCK 00..09` — czas przetwarzania bloku (`time_ms`), wynik modelu (`score`), `rms` oraz bieżący `heap_free`,
- `MIN_HEAP_DURING_INFERENCE`, `TOTAL_INFERENCE_MS`, `FINALIZE_MS`, `HEAP_AFTER_FINALIZE`,
- `RESULT` — pełny słownik wynikowy zgodny z polami ramki V2,
- `HEAP_AFTER_RESET` i `HEAP_AFTER_REUSE_2BLK` — weryfikacja braku narastającego wycieku pamięci po `detector.reset()`.

---

## 4. Szacowane wymagania pamięciowe (RAM) i pamięć flash

Poniżej zestawiono **wartości zmierzone** (z kontraktu sprzętowego LoPy 1.0) oraz **szacunkowy bilans buforów numerycznych** (przed narzutem bajtkodu i obiektów MicroPythona):

| Składnik | Burst MLP (`deploy/burst/`) | CNN v4.6 bin (`deploy/cnn_v46/`) |
|---|---:|---:|
| Wolna sterta przed aplikacją *(zmierzone)* | `52 096 B` | `52 096 B` |
| Bufor audio firmware `nagraj_audio()` *(znane)* | `8 000 B` | `8 000 B` |
| Bufor dekodowanych próbek (1 podramka) | `1 024 B` (`512 × int16`) | `2 000 B` (`1000 × int16`) |
| Tablice FFT + ekstrakcja cech + bufor okien | `~9 984 B` | `~20 136 B` *(połówkowa tablica Hanna)* |
| Wagi modelu w RAM | `~860 B` (`528 B` INT8 + stałe) | `~1 017 B` (`wc` 144 B + `wo` 64 B + wiersz `201 B` + stałe) |
| Tensory pośrednie inferencji | `128 B` | `1 864 B` *(bez tensora `conv` 12 288 B)* |
| Stan detektora i wyniki sesji | `~1 000 B` | `~1 000 B` |
| **Suma buforów numerycznych (szacunek)** | **`~20 996 B`** *(zapas ~31 KB)* | **`~34 017 B`** *(zapas ~18 KB)* |
| Rozmiar pakietu w pamięci flash *(zmierzone)* | `47 200 B` (~46 KiB z ~460 KiB) | `51 923 B` (~51 KiB z ~460 KiB) |

> **Uwaga:** Rzeczywiste zużycie RAM obejmuje dodatkowo bajtkod zaimportowanych modułów, obiekty Pythona, fragmentację sterty oraz bufory Wi-Fi/HTTP. Z tego względu **Burst MLP** jest najbezpieczniejszym pierwszym kandydatem do uruchomienia na płytce, natomiast **CNN v4.6** (ze strumieniowaniem wag z flash) jest modelem preferowanym, jeżeli zmieści się w pomiarze `gc.mem_free()` na urządzeniu.

---

## 5. Pliki wymagane do integracji z `firmware/main4.py`

Do katalogu `/flash/lib/` na LoPy (po zakończeniu testu dymnego w `/flash/tg_demo/`) programista firmware kopiuje **wyłącznie** jeden z poniższych zestawów (nie należy ładować obu modeli naraz):

- **Zestaw Burst MLP** (z `detection/micropython/deploy/burst/`):
  - `tg_stream_detector.py`
  - `tg_burst.py`
  - `tg_model_burst.py`
- **Zestaw CNN v4.6** (z `detection/micropython/deploy/cnn_v46/`):
  - `tg_stream_detector.py`
  - `tg_model_v46_bin.py`
  - `tg_v46_weights.bin`

Minimalny przykład wywołania kompatybilny z `firmware/main4.py` znajduje się w [stream_example.py](firmware/stream_example.py) oraz opisany został w [FIRMWARE_INTEGRATION_PL.md](FIRMWARE_INTEGRATION_PL.md).

---

## 6. Status walidacji na fizycznym sprzęcie

- **Status: OCZEKUJĄCA (pending)** — wdrożenie fizyczne i testy na płytce Pycom LoPy 1.0 zostały przekazane programiście firmware (na tym etapie nie wykonywano zapisu na urządzenie przez `COM4`).
- **Kroki do wykonania przez programistę firmware na fizycznym LoPy 1.0:**
  1. Uruchomić test dymny dla `deploy/burst/` (sekcja 2, krok 2) i zanotować `HEAP_*`, `MIN_HEAP_DURING_INFERENCE` oraz `BLOCK xx: time_ms`.
  2. Uruchomić test dymny dla `deploy/cnn_v46/` (sekcja 2, krok 3) i sprawdzić, czy `gc.mem_free()` pozostawia wystarczający zapas pamięci dla `polacz_wifi()` i `wyslij_payload()` (ew. rozważyć prekompilację `mpy-cross`).
  3. Zweryfikować brak `MemoryError`, `ImportError` i brak narastania zużycia pamięci po `detector.reset()`.
  4. Podłączyć wybraną konfigurację w `STAN 2` w `firmware/main4.py` zgodnie z [FIRMWARE_INTEGRATION_PL.md](FIRMWARE_INTEGRATION_PL.md) i uzgodnić z backendem mapowanie bitów `source_bits`.
