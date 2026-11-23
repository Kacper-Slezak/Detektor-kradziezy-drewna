# Timber Guard v4.6: instrukcja instalacji, treningu i uruchamiania na Pycom LoPy

The optional burst diagnostic includes a trained compact model for the original LoPy.
Its measured comparison, reproduction commands and deployment procedure are in the
[English technical report](BURST_TECHNICAL_REPORT.md). This README describes the v4.6 baseline.
The [recall follow-up](RECALL_TECHNICAL_REPORT.md) compares real-only retraining and
documents the new recording manifest and experimental model.
The [acoustic diagnosis](ENGINE_RECALL_DIAGNOSIS.md) examines wet-clip provenance,
capture and spectral features, and the effect of vote-rule duration.
The [spectral feature follow-up](SPECTRAL_FEATURE_EVALUATION.md) reports the optional
FFT probes and transfer to source-screened engine recordings.
The [original LoPy bench and field recording runbook](LOPY_HARDWARE_VALIDATION.md)
covers deployment, hardware acceptance tests, raw capture and session splits.

Timber Guard v4.6 to eksperymentalny system wykrywania dźwięków silników w środowisku leśnym. Projekt obejmuje przygotowanie danych i trenowanie modelu na komputerze, analizę nagrań WAV, porównywanie wyników oraz diagnostyczną wersję oprogramowania MicroPython dla **oryginalnego modułu Pycom LoPy (ESP32)**.

W tej wersji stosowany jest kompaktowy klasyfikator CNN. Model **YAMNet służy wyłącznie jako model nauczycielski podczas treningu na komputerze** i nie jest uruchamiany na LoPy. W udostępnionym projekcie obsługiwana jest eksperymentalna wersja **v4.6**; starsze warianty pozostawiono wyłącznie tam, gdzie są niezbędne do przygotowania danych.

> **Status projektu:** rozwiązanie ma charakter eksperymentalny. Pakiet źródłowy nie zawiera zbiorów audio, przygotowanych danych FSC22, wyników wcześniejszych treningów ani wag modelu wytrenowanego na rzeczywistych danych. Dane należy dostarczyć osobno lub odtworzyć zgodnie z instrukcją. Model używany w testach jednostkowych nie jest modelem produkcyjnym. Alarmy fizyczne pozostają wyłączone, a dokładność detekcji, próbkowanie analogowe 4 kHz i wydajność na rzeczywistym LoPy nie zostały jeszcze zweryfikowane.

## 1. Struktura projektu

```text
micropython/
  algorithm/
    app/
      v4_2_prepare.py              # Prepare the original FSC22 feature cache, if needed
      v4_2_teacher.py              # Run YAMNet on the PC
      v4_2_teacher_diagnose.py     # Compare YAMNet and student-model CSV output
      v4_6_prepare.py              # Extract 8x24 log-mel and 9 energy features
      v4_6_train.py                # Train v4.6 with YAMNet supervision
      v4_6_infer.py                # Run WAV inference and export CSV
      v4_6_compare.py              # Compare forest and truck recordings
      v4_6_stage_lopy.py           # Prepare files for /flash/
      _dataset_utils.py
      _v46_training.py
      simulate.py                  # Legacy cache preparation only
    core/                          # v4.6 DSP/CNN and required helper modules
    legacy_firmware/               # Legacy DSP for v4_2_prepare.py; do not deploy
    data/                          # Dataset archives and manifests (not included)
    results/                       # Features, YAMNet scores and models (not included)
    sample_audio/                  # WAV recordings for testing (not included)
  firmware/
    main.py
    config.py
    lib/                            # v4.6 device modules only
    lopy_v46_memory_probe.py
  tests/
    test_v46.py
    test_cleanup.py
  prepare_fsc22_for_timber_guard.py
  requirements-student.txt
  requirements-teacher.txt
```

Z projektu usunięto nieużywane wersje eksperymentalne v4.1–v4.5 i v4.7, ich skrypty treningowe i testowe, stare modele, demonstracje oraz nieaktualną dokumentację. Zachowano moduły niezbędne do działania v4.6 oraz odtworzenia wcześniejszego zbioru cech. Katalog `algorithm/legacy_firmware` służy wyłącznie do przygotowania danych i **nie jest częścią oprogramowania wdrażanego na LoPy**.

## 2. Wymagania

Instrukcja zakłada system **Windows 11** i wykonywanie poleceń w **PowerShell** z katalogu `detection/micropython`.

Do przygotowania danych i uruchamiania kompaktowej sieci potrzebne są:

- Python 3.13 wraz z pakietami określonymi w `requirements-student.txt`;
- FFmpeg dostępny z poziomu terminala;
- dane audio oraz odpowiedni manifest, jeżeli model ma być trenowany od początku.

Do generowania ocen YAMNet potrzebne jest osobne środowisko **Python 3.11** z zależnościami z `requirements-teacher.txt`. TensorFlow i YAMNet nie są wymagane na urządzeniu LoPy.

### Tworzenie środowiska dla modelu kompaktowego

```powershell
py -3.13 -m venv .venv-v4
.\.venv-v4\Scripts\python.exe -m pip install -r requirements-student.txt
ffmpeg -version
```

### Tworzenie środowiska dla YAMNet

```powershell
py -3.11 -m venv .venv-yamnet
.\.venv-yamnet\Scripts\python.exe -m pip install -r requirements-teacher.txt
```

Oba środowiska i FFmpeg są instalowane na komputerze, nie na mikrokontrolerze.

## 3. Instalacja oraz migracja z wcześniejszej wersji

Przy nowej instalacji należy rozpakować projekt tak, aby katalog roboczy miał postać `detection/micropython`.

W przypadku migracji z wcześniejszego projektu **nie należy rozpakowywać nowych plików bezpośrednio na stary katalog**. Mogłoby to pozostawić nieużywane moduły starszych wersji.

Zalecana procedura migracji:

1. Zmienić nazwę poprzedniego katalogu `micropython` na `micropython-old`.
2. Rozpakować nową wersję w katalogu `detection`, tworząc nowy `micropython`.
3. Skopiować dane użytkowe i wyniki z dotychczasowego projektu:

   ```text
   micropython-old/algorithm/data/         -> micropython/algorithm/data/
   micropython-old/algorithm/results/      -> micropython/algorithm/results/
   micropython-old/algorithm/sample_audio/ -> micropython/algorithm/sample_audio/
   ```

4. Sprawdzić poprawność działania, zanim stary katalog zostanie usunięty.

Środowiska wirtualne na Windows mogą przestać działać po przeniesieniu. Najbezpieczniej utworzyć je ponownie. Na potrzeby krótkiej weryfikacji można też skorzystać z interpretera pozostawionego w starej lokalizacji:

```powershell
..\micropython-old\.venv-v4\Scripts\python.exe -m unittest -v tests.test_v46
```

## 4. Weryfikacja danych i wyników treningu

Po migracji można sprawdzić obecność najważniejszych plików:

```powershell
Test-Path 'algorithm/data/dataset_manifest_fsc22.csv'
Test-Path 'algorithm/results/v4_2_fsc22/features.npz'
Test-Path 'algorithm/results/v4_2_fsc22/windows.csv'
Test-Path 'algorithm/results/v4_2_fsc22/wide_v46.npz'
Test-Path 'algorithm/results/v4_2_fsc22/teacher_scores.npy'
Test-Path 'algorithm/results/v4_6_wideband/tg_model_v46.py'
```

Wynik `True` oznacza, że wskazany plik istnieje. Wynik `False` oznacza konieczność odzyskania go z poprzedniej instalacji lub ponownego wygenerowania.

Jeżeli dostępne są pliki `wide_v46.npz`, `wide_v46_report.json`, `features.npz`, `windows.csv`, `teacher_scores.npy` oraz `teacher_report.json`, nie ma potrzeby ponownego przygotowywania FSC22 ani uruchamiania YAMNet. Gdy dostępny jest również wytrenowany `tg_model_v46.py`, można przejść bezpośrednio do testowania nagrań lub przygotowania plików dla LoPy.

## 5. Przygotowanie danych i trenowanie modelu

Poniższe czynności są potrzebne tylko wtedy, gdy brak przygotowanych danych lub konieczne jest przeprowadzenie nowego treningu.

### 5.1. Przygotowanie cech v4.6

Wymagane są plik `dataset_manifest_fsc22.csv`, archiwa WAV, do których odwołuje się manifest, oraz podstawowy zestaw danych przygotowany dla v4.2.

```powershell
.\.venv-v4\Scripts\python.exe -m algorithm.app.v4_6_prepare `
  --results 'algorithm/results/v4_2_fsc22' `
  --manifest 'algorithm/data/dataset_manifest_fsc22.csv' `
  --data-dir 'algorithm/data'
```

Jeżeli brakuje `features.npz`, `windows.csv` lub katalogu `teacher_audio`, należy najpierw odtworzyć dane bazowe:

```powershell
.\.venv-v4\Scripts\python.exe -m algorithm.app.v4_2_prepare `
  --manifest 'algorithm/data/dataset_manifest_fsc22.csv' `
  --data-dir 'algorithm/data' `
  --output 'algorithm/results/v4_2_fsc22' `
  --aug-per-engine 2 `
  --snr -10 -5 0 5 10
```

Następnie można ponownie uruchomić polecenie `v4_6_prepare`.

### 5.2. Przygotowanie ocen nauczyciela YAMNet

Ten etap jest wymagany tylko wtedy, gdy nie istnieje plik `teacher_scores.npy`:

```powershell
.\.venv-yamnet\Scripts\python.exe -m algorithm.app.v4_2_teacher `
  --results 'algorithm/results/v4_2_fsc22'
```

YAMNet jest wykonywana na komputerze. Jej oceny są wykorzystywane do wspomagania treningu kompaktowej sieci, a nie do bezpośredniej klasyfikacji na LoPy.

### 5.3. Trenowanie CNN v4.6

```powershell
.\.venv-v4\Scripts\python.exe -m algorithm.app.v4_6_train `
  --results 'algorithm/results/v4_2_fsc22' `
  --output-dir 'algorithm/results/v4_6_wideband' `
  --conv-channels 16 --hidden 64 `
  --teacher-alpha 0.20 --teacher-cutoff 0.24 `
  --hard-negative-boost 1.5 --gain-aug-db 9 --epochs 40
```

Model jest zapisywany jako `algorithm/results/v4_6_wideband/tg_model_v46.py`.

**Uwaga:** jeżeli taki plik już istnieje, dla nowego eksperymentu należy ustawić inny katalog `--output-dir`, aby nie nadpisać wcześniej wytrenowanych wag.

## 6. Testowanie modelu na nagraniach WAV

Do testów można użyć dowolnych odpowiednich nagrań WAV. Poniższy przykład obejmuje nagranie samego środowiska leśnego oraz nagranie z dźwiękiem ciężarówki. Nazwy plików należy dostosować do zawartości katalogu `algorithm/sample_audio`.

```powershell
$names = @('forest-ambience', 'forest-with-truck')
foreach ($name in $names) {
    .\.venv-v4\Scripts\python.exe -m algorithm.app.v4_6_infer `
      --model 'algorithm/results/v4_6_wideband/tg_model_v46.py' `
      --audio-wav "algorithm/sample_audio/$name.wav" `
      --quiet --off-hours `
      --output "algorithm/results/v4_6_wideband/$name.csv"
}
```

Porównanie obu wyników:

```powershell
.\.venv-v4\Scripts\python.exe -m algorithm.app.v4_6_compare `
  --forest 'algorithm/results/v4_6_wideband/forest-ambience.csv' `
  --truck 'algorithm/results/v4_6_wideband/forest-with-truck.csv' `
  --start 19 --end 40
```

Parametry `--start 19 --end 40` odpowiadają przykładowemu przedziałowi obecności silnika w nagraniu testowym. Dla innych nagrań należy podać właściwe granice czasowe.

Przełącznik `--off-hours` jest używany wyłącznie do symulowania reguł alarmowych w wynikach CSV. **Nie aktywuje alarmu na urządzeniu fizycznym.** Nagrania używane wielokrotnie podczas projektowania modelu nie powinny być traktowane jako niezależny zbiór testowy.

## 7. Przygotowanie oprogramowania dla LoPy

Po zakończeniu treningu można wygenerować katalog z plikami wymaganymi przez diagnostyczną wersję MicroPython:

```powershell
.\.venv-v4\Scripts\python.exe -m algorithm.app.v4_6_stage_lopy `
  --model 'algorithm/results/v4_6_wideband/tg_model_v46.py' `
  --output 'algorithm/results/v4_6_wideband/flash_stage'
```

W katalogu `flash_stage/` znajdują się:

- `main.py` i `config.py`,
- `lopy_v46_memory_probe.py`,
- biblioteki w katalogu `lib/`, w tym wytrenowany model `tg_model_v46.py`.

**Na urządzenie przeznaczona jest zawartość katalogu `flash_stage`, a nie cały projekt `micropython`.** Powyższa komenda tylko przygotowuje pliki. Nie wykonuje flashowania i nie uruchamia alarmu.

Przed ponownym generowaniem plików należy usunąć lub zmienić nazwę **wyłącznie poprzedniego katalogu `flash_stage`**, jeżeli narzędzie wymaga pustego katalogu docelowego.

### Konfiguracja sprzętowa

Docelowa konfiguracja sprzętowa obejmuje:

- oryginalny moduł **Pycom LoPy (ESP32)**;
- analogowy moduł mikrofonowy **SparkFun BOB-12758 z OPA344**;
- zasilanie mikrofonu **3,3 V**;
- pobieranie próbek przez wejście **ADC**.

Wartość `AUDIO_PIN = 'P16'` w `firmware/config.py` jest **przykładem**, nie potwierdzonym przypisaniem pinu. Należy dostosować ją do rzeczywistego połączenia i możliwości ADC danego pinu.

Nie zweryfikowano jeszcze na fizycznym LoPy poprawności programowego próbkowania z częstotliwością 4 kHz ani pracy bez PSRAM. Wersja diagnostyczna nie obsługuje akcelerometru, detekcji drgań, LoRa, syreny fizycznej ani autonomicznego zgłaszania kradzieży.

### Diagnostyka pamięci

Po umieszczeniu diagnostycznych plików na urządzeniu można uruchomić w konsoli REPL:

```python
import lopy_v46_memory_probe
lopy_v46_memory_probe.main()
```

Pomiary wykonywane bezpośrednio na urządzeniu są niezbędne do oceny rzeczywistego zużycia pamięci i wydajności.

## 8. Testy automatyczne

Testy można uruchomić na komputerze poleceniem:

```powershell
.\.venv-v4\Scripts\python.exe -m unittest -v tests.test_v46 tests.test_cleanup
```

Testy weryfikują zgodność obliczeń FFT i cech widmowych między implementacją komputerową a MicroPythonem, zgodność inferencji CPU i eksportu INT8 oraz działanie logiki zdarzeń. **Pozytywny wynik nie potwierdza gotowości systemu do pracy w terenie.**

Jeżeli `MODEL_FLAVOR` jest inny niż `v4_6` lub brakuje pliku modelu, program na urządzeniu nie uruchomi automatycznie żadnej starszej, alternatywnej wersji klasyfikatora.
