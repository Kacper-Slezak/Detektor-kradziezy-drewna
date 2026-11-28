# Integracja algorytmu detekcji audio z firmware Pycom LoPy 1.0 (`firmware/main4.py`)

Dokumentacja integracyjna dla programisty firmware. Opisuje sposób podłączenia strumieniowego adaptera detekcji (`tg_stream_detector.py`) do generatora `nagraj_audio()` oraz mapowania wyniku na ramkę alarmową protokołu **V2** (`przygotuj_ramke_alarm()`).

> **Uwaga:** Pliki w katalogu `firmware/` projektu nie zostały zmodyfikowane. Poniższa instrukcja oraz minimalny przykład [stream_example.py](firmware/stream_example.py) znajdują się w całości w `detection/micropython/`.

---

## 1. Wymagane pliki i zależności

Moduł `tg_stream_detector.py` wykorzystuje wyłącznie standardowe biblioteki MicroPythona (`array`, `math`, `ubinascii`/`binascii`, `gc`) i nie wymaga `numpy`, `scipy` ani `tensorflow`.

### Wariant A — kompaktowy model Burst MLP (`deploy/burst/`, **zalecany jako pierwszy test na LoPy 1.0**)
Do katalogu `/flash/lib/` na LoPy należy skopiować (3 pliki, brak zależności od `tg_temporal_v46.py`):
- `detection/micropython/deploy/burst/tg_stream_detector.py`
- `detection/micropython/deploy/burst/tg_burst.py`
- `detection/micropython/deploy/burst/tg_model_burst.py` (`3 988 B`)

### Wariant B — model wideband CNN v4.6 ze strumieniowanymi wagami binarnymi (`deploy/cnn_v46/`, **model preferowany**)
Do katalogu `/flash/lib/` na LoPy należy skopiować (3 pliki, brak zależności od `tg_burst.py` i `tg_temporal_v46.py`):
- `detection/micropython/deploy/cnn_v46/tg_stream_detector.py`
- `detection/micropython/deploy/cnn_v46/tg_model_v46_bin.py` (`2 274 B`, metadane)
- `detection/micropython/deploy/cnn_v46/tg_v46_weights.bin` (`13 072 B`, oryginalne niezmodyfikowane wagi INT8)

> **Ważne:** Nie należy ładować obu modeli jednocześnie. Szczegółową procedurę wygenerowania pakietów, polecenia PowerShell i samodzielny test dymny opisuje [LOPY_DEPLOYMENT_PL.md](LOPY_DEPLOYMENT_PL.md). Oba warianty korzystają z **identycznego API** klasy `Detector`.

---

## 2. Inicjalizacja detektora

Detektor należy utworzyć **raz** (przed pętlą `nagraj_audio()`), aby jednorazowo zaalokować bufory FFT i tablice pomocnicze:

```python
import gc
import tg_model_burst as model  # lub: import tg_model_v46 as model
from tg_stream_detector import Detector

gc.collect()
detector = Detector(model=model)
```

Najważniejsze parametry opcjonalne `Detector(...)`:
- `model`: obiekt modułu modelu (`tg_model_v46` lub `tg_model_burst`). Jeśli pominięty (`None`), próbuje zaimportować `tg_model_v46`, a następnie `tg_model_burst`.
- `threshold`: próg klasyfikacji okna (domyślnie `model.THRESHOLD`: `0.68` dla v4.6 CNN, `0.84` dla Burst MLP).
- `min_confirm_windows`: liczba kolejnych pozytywnych okien 2-sekundowych wymagana do potwierdzenia obecności silnika (domyślnie `2`, dopasowane do 10-blokowej sesji dającej 9 okien).
- `max_gap_s`: maksymalna dopuszczalna przerwa między blokami w sekundach przed wyczyszczeniem bufora okna (domyślnie `1.5`).
- `require_impact`: jeśli `True`, alarm wymaga jednocześnie potwierdzonego silnika oraz wykrycia impulsu akustycznego (domyślnie `False` — alarm po potwierdzeniu silnika).
- `event_type_alarm`, `source_bit_mic`, `source_bit_vib`: konfigurowalne stałe protokołu V2 (domyślnie `1`, `0x01`, `0x02`).

Przed kolejną niezależną sesją nagrywania wystarczy wywołać `detector.reset()` bez ponownego tworzenia obiektu.

---

## 3. Oczekiwany format bloków audio i analiza `firmware/main4.py`

Kontrakt wejściowy `detector.process(audio_chunk)` odpowiada dokładnie generatorowi `nagraj_audio()` w `firmware/main4.py`:

| Parametr | Wartość w `firmware/main4.py` | Wymaganie `Detector.process()` |
|---|---|---|
| Częstotliwość próbkowania | `4000 Hz` (`CZESTOTLIWOSC_HZ = 4000`) | `4000 Hz` |
| Kanały | mono (`PIN_MIKROFON_ADC_ID = "P16"`) | mono |
| Próbek w bloku | `4000` (`ROZMIAR_BLOKU_PROBEK = 4000`) | `4000` |
| Czas bloku | `1 s` | `1 s` |
| Rozmiar bloku | `8000 B` (`bytearray(blok_probek * 2)`) | dokładnie `8000 B` |
| Format próbki | `uint16` little-endian, 12-bit ADC (`0..4095`) | `uint16` LE, `0..4095` (wartości spoza zakresu są obcinane) |
| Liczba bloków w sesji | `10` (`CZAS_NAGRANIA_S = 10`) | dowolna (0..N), standardowo `10` |
| Bufor | jeden współdzielony `bytearray(8000)` | brak zachowywania referencji po wyjściu z `process()` |

### Wykryte cechy i rozbieżności w `firmware/main4.py`:
1. **Przerwy między blokami:** `nagraj_audio()` resetuje `t_nastepna = time.ticks_us()` na początku każdego bloku. Czas wykonania `detector.process(blok_audio)` tworzy zatem naturalną przerwę akwizycji pomiędzy końcem bloku `k` a początkiem bloku `k+1`. Adapter **nie zakłada ciągłości próbek na granicy bloków** — wszystkie ramki FFT mieszczą się wewnątrz pojedynczego 1-sekundowego bloku.
2. **Brak metadanych czasu z `nagraj_audio()`:** generator zwraca wyłącznie `bytearray`. Jeżeli firmware zmierzy długą przerwę między blokami, może przekazać ją opcjonalnie jako `detector.process(blok_audio, gap_s=przerwa_s)`.
3. **10-blokowa sesja vs oryginalne 15 s w v4.6:** oryginalny `tg_presence_v46.py` wymagał 15 kolejnych okien, co jest niemożliwe w 10-sekundowym nagraniu (9 okien 2-sekundowych). Adapter stosuje regułę `min_confirm_windows=2` (2 kolejne pozytywne okna 2-sekundowe).
4. **Niedookreślone bity `source_bits`:** `firmware/main4.py` wywołuje `przygotuj_ramke_alarm(event_type=..., confidence=..., battery_pct=100)` bez przekazywania `source_bits`, `duration_s` i `energy`, a dokumentacja backendu (`docs/backend/api.md`) nie definiuje jawnie mapowania bitowego `source_bits`. Adapter używa domyślnej, konfigurowalnej konwencji `0x01` (mikrofon) i `0x02` (drgania) — **do potwierdzenia z zespołem backendu**.

---

## 4. Przetwarzanie bloków

```python
for blok_audio in nagraj_audio():
    detector.process(blok_audio)
```

- Każde wywołanie `process(audio_chunk)` dekoduje próbki fragmentami (po 1000 próbek dla v4.6 lub 512 dla burst) do wewnętrznego, wielokrotnie używanego bufora `array('h')`.
- Całe 10-sekundowe nagranie **nie jest** przechowywane w pamięci RAM.
- Po powrocie z `process()` bufor `blok_audio` może zostać natychmiast nadpisany przez `nagraj_audio()`.
- Pierwszy blok wypełnia pierwszą połowę 2-sekundowego okna (`score = None`); od drugiego bloku każde wywołanie `process()` oblicza wynik modelu dla 2-sekundowego okna.

---

## 5. Pobieranie wyniku końcowego

Po zakończeniu pętli `for`:

```python
gc.collect()
wynik = detector.finalize(vib_active=vib_aktywny, mic_active=mic_aktywny)
```

Słownik `wynik` zawiera:

**Pola zgodne z protokołem V2:**
- `alarm` (`bool`): czy potwierdzono zdarzenie alarmowe.
- `event_type` (`int`): `1` (kradzież / silnik) przy `alarm == True`, `0` w przeciwnym razie.
- `confidence` (`int`, `0..100`): skalibrowany szacunek pewności (nie mylić z surowym wyjściem modelu `model_scores`).
- `source_bits` (`int`, `0..255`): maska bitowa źródeł (`0x01` audio, `0x02` drgania).
- `duration_s` (`int`, `0..65535`): szacowany czas trwania zdarzenia w sekundach.
- `energy` (`int`, `0..255`): skwantowana energia sygnału audio (skala logarytmiczna RMS).

**Pola diagnostyczne (wewnętrzne):**
- `engine_detected` (`bool`): czy potwierdzono obecność silnika.
- `impact_detected` (`bool`), `impact_count` (`int`): czy wykryto impulsy akustyczne.
- `vib_active` (`bool`): przekazana binarna informacja z czujnika drgań (**sama w sobie nigdy nie wywołuje alarmu**).
- `model_type` (`str`): `'tiny_cnn_wide_v46'` lub `'burst_mlp'`.
- `model_threshold` (`float`): próg decyzyjny modelu.
- `model_scores` (`list[float]`): surowe prawdopodobieństwa (sigmoid) z poszczególnych okien 2 s.
- `max_model_score` (`float`), `mean_model_score` (`float`).
- `positive_windows` (`int`), `max_consecutive_hits` (`int`).
- `blocks_processed` (`int`), `observed_duration_s` (`float`).
- `gap_resets` (`int`), `clipped_samples` (`int`), `max_audio_rms` (`float`).

---

## 6. Przykładowa integracja z `nagraj_audio()` w `STAN 2` (`firmware/main4.py`)

Minimalny fragment pokazujący zastąpienie sekcji `TODO` w `firmware/main4.py` (pełny przykład: [stream_example.py](firmware/stream_example.py)):

```python
# Na początku modułu lub przed nagrywaniem (poza pętlą):
import tg_model_burst as model  # lub tg_model_v46
from tg_stream_detector import Detector

# Wewnątrz STAN 2 (powod == machine.PIN_WAKE):
gc.collect()
detector = Detector(model=model)

for blok_audio in nagraj_audio():
    try:
        detector.process(blok_audio)
    except ValueError as exc:
        print("Pominięto niepoprawny blok audio:", exc)

gc.collect()
wynik = detector.finalize(vib_active=vib_aktywny, mic_active=mic_aktywny)

if wynik["alarm"]:
    ramka = przygotuj_ramke_alarm(
        event_type=wynik["event_type"],
        confidence=wynik["confidence"],
        battery_pct=100,
        source_bits=wynik["source_bits"],
        duration_s=wynik["duration_s"],
        energy=wynik["energy"],
    )
    try:
        polacz_wifi()
        wyslij_payload(ramka)
    except Exception as e:
        print("Błąd wysyłania Alarmu:", e)
```

---

## 7. Mapowanie wyników detekcji na ramkę V2 (`przygotuj_ramke_alarm`)

Ramka V2 w `firmware/main4.py` ma format `>BBBHBB` (7 bajtów ciała + 3 bajty nagłówka):

| Pole wyniku `finalize()` | Argument `przygotuj_ramke_alarm()` | Typ / zakres | Uwagi |
|---|---|---|---|
| `wynik["event_type"]` | `event_type` | `uint8` (`0` lub `1`) | `1` odpowiada `"event_type": "theft"` |
| `wynik["source_bits"]` | `source_bits` | `uint8` (`0..255`) | domyślnie `0x01`=mic, `0x02`=vib (do potwierdzenia z backendem) |
| `wynik["confidence"]` | `confidence` | `uint8` (`0..100`) | skalibrowana pewność, odrębna od surowych `model_scores` |
| `wynik["duration_s"]` | `duration_s` | `uint16` (`0..65535`) | całkowita liczba sekund aktywnego zdarzenia |
| `wynik["energy"]` | `energy` | `uint8` (`0..255`) | logarytmicznie przeskalowane maksymalne RMS (`-60..0 dBFS`) |
| *(z firmware)* | `battery_pct` | `uint8` (`0..100`) | dostarczane przez firmware |

---

## 8. Obsługa błędów

- **`ValueError` w `process()`**: niepoprawna długość bloku (`len(audio_chunk) != 8000`) lub niemonotoniczny `timestamp_s`.
- **`TypeError` w `process()`**: przekazano obiekt niebędący `bytes`, `bytearray` ani `memoryview`.
- **`ImportError` / `ValueError` w `Detector()`**: brak pliku modelu lub uszkodzone wymiary wag.
- **`MemoryError` na LoPy**: w przypadku braku RAM przy ładowaniu `tg_model_v46.py` należy wywołać `gc.collect()` przed inicjalizacją i przełączyć się na kompaktowy `tg_model_burst.py` (lub użyć prekompilowanych plików `.mpy`).
- **Pusta sesja (0 bloków)**: `finalize()` zwraca bezpieczny wynik bez alarmu (`alarm=False`, `event_type=0`, `confidence=0`, `duration_s=0`, `energy=0`).

---

## 9. Szacowane wymagania pamięciowe i wydajnościowe

### Wartości zmierzone vs szacowane (Pycom LoPy 1.0, MicroPython 1.20.2.r6)

| Zasób | Status | Wartość |
|---|---|---|
| Wolna sterta (heap) przed załadowaniem aplikacji | **zmierzone** (z kontraktu zadania) | `52 096 B` |
| Współdzielony bufor audio `nagraj_audio()` | **zmierzone / znane** (`main4.py`) | `8 000 B` |
| Wolna pamięć flash | **zmierzone** (z kontraktu zadania) | `~460 KiB` |

### Szacunkowy bilans buforów numerycznych (RAM)

| Składnik | Wariant B: `v4.6 CNN` (fused) | Wariant A: `Burst MLP` |
|---|---:|---:|
| Bufor audio firmware (`nagraj_audio`) | `8 000 B` | `8 000 B` |
| Bufor dekodowanych próbek (1 podramka) | `2 000 B` (`1000 × int16`) | `1 024 B` (`512 × int16`) |
| Tablice FFT + ekstrakcja cech + bufor okien | `~22 136 B` | `~9 984 B` |
| Wagi modelu (INT8) + stałe float | `~13 680 B` (+ ~17,5 KB base64 w `.py`) | `~860 B` (źródło `3 988 B`) |
| Tensory pośrednie inferencji | `1 864 B` *(usunięto tensor conv `12 288 B`)* | `128 B` |
| Stan detektora i wyniki sesji | `~1 000 B` | `~1 000 B` |
| **Suma buforów numerycznych (szacunek)** | **`~48 680 B`** *(+ narzut MicroPython / base64)* | **`~20 996 B`** *(+ narzut MicroPython)* |

**Uczciwa ocena zmieszczenia się w stercie `52 096 B`:**
- **Wariant B (`v4.6 CNN`)**: mimo redukcji RAM o ~40 KB względem oryginalnego `tg_v46_device.py` (usunięcie buforów `RawChunk` 16 KB, listy `powers` ~12 KB oraz tensora `conv` 12,3 KB), sama suma buforów numerycznych i wag wynosi ~48,7 KB przed uwzględnieniem bajtkodu, obiektów modułów, łańcuchów `WEIGHT_B64` oraz stosu Wi-Fi/HTTP. **Nie można twierdzić, że `v4.6 CNN` zmieści się w 52 096 B RAM bez pomiaru na urządzeniu** (prawdopodobnie przekroczy dostępny heap w wersji `.py`).
- **Wariant A (`Burst MLP`)**: bufory numeryczne + bufor audio zajmują ok. **21 KB**, pozostawiając ok. **31 KB** zapasu na bajtkod MicroPythona, fragmentację sterty i transmisję Wi-Fi/HTTP. Również wymaga fizycznej weryfikacji na płytce.

### Wydajność na PC (CPython 3.11.9 — **NIE jest to wydajność ESP32!**)
- `v4.6 CNN` (fused): pierwszy blok `8,50 ms`, mediana kolejnego bloku `14,18 ms`, 10 bloków `136,67 ms`, `finalize()` `0,024 ms`.
- `Burst MLP`: pierwszy blok `4,46 ms`, mediana kolejnego bloku `4,43 ms`, 10 bloków `45,20 ms`, `finalize()` `0,018 ms`.

Na ESP32 @ 160 MHz (MicroPython bez JIT) czas przetwarzania bloku będzie **wielokrotnie dłuższy** (rzędu kilkudziesięciu–kilkuset ms) i zwiększy przerwę akwizycji pomiędzy kolejnymi blokami `nagraj_audio()`.

---

## 10. Znane ograniczenia

1. **Brak walidacji sprzętowej:** kod został przetestowany na CPython z symulacją buforów i rzeczywistymi nagraniami WAV; działanie na fizycznym Pycom LoPy 1.0 (heap, czas FFT, Wi-Fi po detekcji) nie zostało jeszcze zmierzone.
2. **Niezamrożone bity `source_bits`:** bitmaska (`0x01` / `0x02`) musi zostać uzgodniona z dekoderem ramek V2 po stronie backendu.
3. **Kalibracja `confidence` i impulsów:** `confidence` (0–100) oraz progi detekcji impulsów (`impact_min_rms`, `impact_crest_threshold`) są heurystykami wymagającymi kalibracji na rzeczywistym torze mikrofon + ADC płytki LoPy.
4. **Przerwy między blokami:** dłuższy czas `process()` na ESP32 wydłuża przerwę pomiędzy blokami w `nagraj_audio()`, co może powodować pominięcie krótkich impulsów przypadających w trakcie obliczeń.

---

## 11. Instrukcja walidacji na fizycznym sprzęcie LoPy 1.0

1. Wgrać pliki z sekcji 1 (najpierw **Wariant A — `Burst MLP`**) do `/flash/lib/` na LoPy 1.0.
2. W konsoli REPL zmierzyć wolny heap na każdym etapie:
   ```python
   import gc, time
   gc.collect(); print("START:", gc.mem_free())
   import tg_model_burst as model
   from tg_stream_detector import Detector
   gc.collect(); print("PO IMPORCIE:", gc.mem_free())
   det = Detector(model=model)
   gc.collect(); print("PO INICJALIZACJI:", gc.mem_free())
   buf = bytearray(8000)
   for i in range(10):
       t0 = time.ticks_ms()
       step = det.process(buf)
       dt = time.ticks_diff(time.ticks_ms(), t0)
       gc.collect()
       print("Blok", i, "ms:", dt, "heap:", gc.mem_free(), "score:", step["score"])
   print("WYNIK:", det.finalize())
   ```
3. Zweryfikować:
   - brak `MemoryError`,
   - zapas `gc.mem_free()` wystarczający do późniejszego wywołania `polacz_wifi()` i `wyslij_payload()`,
   - czas `dt` pojedynczego bloku (aby ocenić długość przerwy między blokami `nagraj_audio()`),
   - poprawność poziomu DC z mikrofonu (oczekiwana średnia surowych próbek ADC blisko środka zakresu przy ciszy oraz `clipped_samples == 0` w tle).
4. Po pozytywnym teście Wariantu A opcjonalnie powtórzyć procedurę dla Wariantu B (`tg_model_v46.py`, najlepiej po prekompilacji `mpy-cross`).
