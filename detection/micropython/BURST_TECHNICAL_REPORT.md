# Wood theft detector on the original Pycom LoPy

## Outcome

The selected diagnostic build uses a **32 → 16 → 1 ReLU MLP** with 528 signed int8 weights and a score threshold of **0.84**. It confirms after two consecutive positive windows and clears its evidence on invalid audio. On the original recording split, it reduced FSC22 false-positive windows from 15 to 6 of 732. Clean-engine window recall dropped from 81.7% to 75.0%, and 0 dB mixed-engine recall dropped from 55.5% to 43.3%. It missed the supplied rain-and-wind truck example. The build is ready to stage for bench measurements. Reliable field engine detection and LoPy timing remain unverified.

## Original implementation

The root project separates communications, hardware designs, desktop detection and MicroPython. The active MicroPython path is v4.6. It reads the analog SparkFun BOB-12758 microphone at 4 kHz using software-timed ADC polling. Two one-second PCM16 buffers feed eight Hann-windowed 1,024-point FFT frames with 24 log-mel bands from 35–1,900 Hz. The CNN uses the 8×24 patch and nine RMS envelope features, a 16-channel 3×3 convolution, frequency-group mean and max pooling, 64 hidden units and a sigmoid. The model uses int8 weights with floating-point activations. Optional YAMNet supervision runs only on the PC. The existing export uses a 0.68 threshold and nine positive windows in a fully populated 15-window history.

The original desktop path supports WAV replay, a training cache and an off-hours alarm simulation. The v4.6 LoPy entry point supports audio diagnostics only. The legacy drivers include ADXL345 and vibration handling, and the desktop simulator exercises loading/fusion scenarios. The burst build reuses the microphone interface and exposes optional ADXL345 readings on I2C. The accelerometer supplies diagnostics only, at four reads per second, with the latest sample reported alongside the audio result. The communications area contains LoRa design material. Neither diagnostic entry point uses a radio.

Between ADC acquisitions the v4.6 firmware computes FFTs, runs the CNN, collects garbage and prints telemetry. Its default 20 ms processing-gap limit can invalidate the next window if processing overruns. The new capture schedule intentionally reserves time for these operations. The workspace also contains legacy experimental modules, old result directories and stale tests. They remain available for their original use.

## Recordings and split

| Local source | Archive WAVs | Used by FSC22 manifest | Raw duration used by manifest |
|---|---:|---:|---:|
| Zenodo ICE, diesel and petrol | 183 + 137 | 320 engine | 25.28 min |
| ESC-50 | 2,000 | 360 hard negatives | 30.00 min |
| FSC22 full and selected archives | 2,025 and 1,275 | 1,275 forest/environment negatives | 106.25 min |
| Total | | 1,955 clips | 161.53 min |

The older 1,080-clip manifest uses the same 320 engines, 360 ESC-50 hard negatives and 400 other ESC-50 backgrounds. The FSC22 manifest replaces the latter 400 with 17 classes of 75 examples, including wind, rain, animals and silence. Archive counts can include copies between full and selected archives. The additional accelerometer CSVs and sibling desktop loading scenario contain demo material and supply no independent acoustic labels for training.

The selected source clips cover 8–192 kHz and one to eight channels. All 680 ICE and ESC-50 clips are mono 44.1 kHz PCM16. Most FSC22 clips are 44.1 or 48 kHz mono or stereo, and three have 32-bit samples. Five ICE clips are shorter than the two-second window. A first-second PCM16 scan found 46 clips with more than 0.1% of samples near full scale, 37 very quiet clips (standard deviation below 32 PCM counts) and 18 with absolute DC above 1% of full scale. This screen identifies possible clipping, low gain or bias and covers only clip prefixes. Whole-clip labels can include quiet intervals and other sounds. Vehicle and recorder/session identities for ICE recordings and some FSC22 scenes are unavailable.

The original split uses 229/47/44 engine sources and 1,122/258/255 negatives in train/validation/test. All overlapping windows and original augmentations stay in their source split. Manifest SHA-256 checks, source ID checks and a scan of first-second PCM hashes found no exact duplicates across selected splits. The first-second scan covers PCM16 data and leaves near-duplicate ICE takes and shared hardware or sites unresolved. There are 6,987 train windows (1,666 augmented positives), 1,201 validation windows and 1,184 test windows. The 0 dB stress test mixes each held-out engine with a same-split FSC22 background; these mixtures provide 169 validation and 164 test windows and are never used for fitting weights. Windows within a recording are correlated.

The four `-4k.wav` recordings are resampled copies of their full-rate counterparts. An eight-second prefix check found correlation above 0.999999 between the truck example's pre-engine background and the supplied forest ambience at zero lag. Both recordings are therefore development data. The forest recording was used as a negative, in augmentation and in threshold screening. The truck recording was used to select a model using the existing 19–40 s annotation. Rain, wind, the rain-and-wind truck and Caterpillar replays provide limited additional observations. Their provenance and engine time boundaries are incomplete. The synthetic engine and loading demos are regression material.

## Experiments and selection

Nine configurations were evaluated including the original v4.6 export. The burst classifiers use eight 4 kHz capture blocks per nominal two-second window at one-second hops, subtract the PCM mean in each block, apply Hann tapering and compute average FFT power in 15 bands spanning nominally 30–1,900 Hz. Each block's log powers are centered and clipped. Features are the temporal mean and standard deviation per band plus the standard deviation of log RMS. Candidates with absolute RMS also use the mean log RMS. The model standardizes each feature using its training mean and a standard deviation floor of 0.05, then clips to ±6. Weight quantization is symmetric per layer and is applied before threshold selection. Biases and activations remain floating point. The optimizer uses Adam, 30 epochs, batches of 128, learning rate 0.003, L2 coefficient 0.001 and seed 2026.

The first five burst configurations were screened on the original validation split and 0 dB mixtures. The initial winner was the 512-point MLP with mean log RMS (threshold 0.88 on that pass). It produced 147 positive windows and 28 confirmed episodes on the 288-second forest example. The second pass added three calibration configurations. They give the forest recording 15% of negative training weight, include new mixtures of the same forest recording with **training engines only** at −8, −2 and +4 dB, and jitter the absolute RMS feature by ±9 dB where present. Original training augmentations have SNRs of −10, −5, 0, +5 and +10 dB.

Thresholds from 0.05 to 0.99 were searched on validation. The target was at least 80% clean-engine recall, at least 60% recall on 0 dB mixtures and at most 2% positive windows on the development forest. Within those targets, selection favors fewer FSC22 false positives. The fallback balances the lower of clean and mixed recall against the FSC22 and development-forest false-positive fractions. Candidates meeting the targets and producing a truck confirmation during the annotated interval with no earlier confirmation rank first. The original test split was kept fixed and used to score the selected model after each phase. Its initial results were already visible during the development iteration, which limits claims of a blind assessment.

| Configuration | Threshold | Validation clean recall | FSC22 FP / 744 | 0 dB hits / 169 | Development forest hits / 287 |
|---|---:|---:|---:|---:|---:|
| Original v4.6 CNN | 0.68 | 81.1% | 42 | 108 | 25 |
| 256 FFT, linear, relative features | 0.89 | 37.3% | 27 | 20 | 4 |
| 256 FFT, MLP, relative features | 0.99 | 12.4% | 1 | 8 | 3 |
| 512 FFT, linear, relative features | 0.91 | 32.5% | 16 | 13 | 2 |
| 512 FFT, MLP, relative features | 0.88 | 69.8% | 36 | 75 | 80 |
| 512 FFT, MLP, absolute RMS | 0.94 | 67.5% | 5 | 69 | 77 |
| 256 FFT, calibrated MLP, absolute RMS | 0.85 | 81.1% | 6 | 103 | 1 |
| 512 FFT, calibrated MLP, relative features | 0.72 | 80.5% | 66 | 102 | 15 |
| **512 FFT, calibrated MLP, absolute RMS** | **0.84** | **81.1%** | **20** | **106** | **0** |

The selected 512-point model was the only configuration meeting the validation targets and the linked truck check. The smaller calibrated 256-point variant had fewer FSC22 validation false positives and missed that truck. For temporal smoothing, 2-of-2 confirmed 35 of 47 validation engines with 8 negative clips confirmed, 2-of-3 confirmed 34 with 8 negatives, and 3-of-4 confirmed 31 with 5 negatives. Selection weights clip recall five times as heavily as specificity. Each option requires a full vote buffer.

## Measured comparison

| Original recording-level test results | v4.6 CNN | Burst MLP |
|---|---:|---:|
| Precision | 81.2% | 87.9% |
| Recall | 81.7% | 75.0% |
| F1 | 81.5% | 80.9% |
| Confusion matrix (TP / FP / FN / TN) | 134 / 31 / 30 / 989 | 123 / 17 / 41 / 1,003 |
| FSC22 false-positive windows | 15 / 732 | 6 / 732 |
| Engine clips without a single positive window | 5 / 44 | 3 / 44 |
| 0 dB mixed-engine windows detected | 91 / 164 | 71 / 164 |
| Positive clips with a confirmation | 0 / 44 | 32 / 44 |
| Negative clips with a confirmation | 0 / 255 | 5 / 255 |

The original 15-window confirmation rule cannot fill its history on clips cut to eight seconds or less. Its clip-level figures reflect that constraint. The baseline and burst event figures count the first transition to confirmed, separate from the legacy off-hours alarm policy. The diagnostic build outputs confirmed state and does not actuate an alarm.

| Longer replay | Nominal audio | v4.6 positive windows / confirmed episodes | Burst positive windows / confirmed episodes |
|---|---:|---:|---:|
| Development forest ambience | 288.02 s | 25 / 0 | 0 / 0 |
| Forest rain | 360.28 s | 0 / 0 | 0 / 0 |
| Wind blowing | 42.74 s | 0 / 0 | 0 / 0 |
| Wind lake | 48.02 s | 0 / 0 | 0 / 0 |
| Linked development truck | 48.47 s | 4 / 0 | 3 / 1 |
| Rain-and-wind truck | 48.03 s | 0 / 0 | 0 / 0 |
| Caterpillar | 44.79 s | 2 / 0 | 1 / 0 |

The confirmed truck episode appeared at nominal window-end time 21 s, 2 s after the documented 19 s onset. It is a development latency observation. The four background replays had 0 observed confirmation episodes over 739.07 s for both models, including 288.02 s used for development. That length and source diversity are insufficient to estimate an unattended false alarm rate. Limited recording labels prevent meaningful latency or event recall estimates for the other examples.

## Resource use and parity

| Resource | v4.6 CNN | Burst MLP |
|---|---:|---:|
| Int8 weights | 13,072 bytes | 528 bytes |
| Model Python source | 19,815 bytes | 3,988 bytes |
| Staged diagnostic Python files | 40,370 bytes | About 20 KB |
| PCM buffer payload | 16,000 bytes | 1,024 bytes |
| FFT arrays and tables, excluding PCM and mel-filter objects | 18,336 bytes | 9,216 bytes |
| Numerical DSP/inference buffer payload | At least 46,624 bytes, including CNN activations | 11,010 bytes, including feature ring and votes |
| FFT butterflies per steady-state one-second hop | 20,480 | 9,216 |
| Nominal classifier weight products per hop | Up to 40,576 | 528 |
| CPython median extraction per steady-state hop | 17.31 ms | 7.49 ms |
| CPython median scoring including burst summarization | 11.76 ms | 0.14 ms |

The 11,010-byte estimate sums fixed typed buffers. Quantized weights add 528 bytes, and the 83 floating-point constants add at least 332 bytes of numeric payload with 32-bit floats. Real peak heap also includes array and module headers, boxed numbers, source import, temporary floats, sensor drivers and JSON/serial output. The v4.6 lower bound excludes mel filters, intermediate Python lists and model storage. Flash figures are source file bytes. Neither Flash capacity available to the application nor physical MicroPython heap was measured. The original LoPy 1.0 has 512 KB total SRAM, 4 MB external Flash and no external PSRAM. MCU and firmware reservations reduce available heap. [Pycom LoPy 1.0 datasheet](https://cdn-shop.adafruit.com/product-files/3339/3339_specs.pdf)

The new monitor retains one 512-sample PCM block and a ring of eight small feature rows. A burst occupies 128 ms of each 250 ms slot, leaving about 122 ms for FFT, scoring as needed, optional I2C, garbage collection and logging. This is a scheduling budget. Actual processing latency depends on the Pycom build and connected hardware. The 51.2% capture duty cycle can miss short transients or make results depend on where an event falls in the slot. FFT tables are preallocated, and each burst is transformed once. The time-critical ADC loop uses integer reads and fixed-size PCM storage. The ADC maps 12-bit codes to signed PCM16 with `(raw << 4) - 32768`. Acquisition deadlines use `ticks_diff`, so support for `ticks_add` is unnecessary. A slot overrun clears prior votes and drops partial audio evidence. [Pycom ADC API](https://docs.pycom.io/firmwareapi/pycom/machine/adc/) · [Pycom ticking clock API](https://docs.pycom.io/firmwareapi/micropython/utime/)

CPython 3.11.9 synthetic compute benchmarks excluded ADC, I2C, printing and radio activity. The replay ran the portable firmware implementation over identical PCM samples and compared it with NumPy FFT features. Maximum observed score deviation was 0.00000066 across seven recordings with no threshold disagreements. The test tolerance is 0.0005 for DSP features and scores. Physical-microphone noise, ADC nonlinearity and actual MicroPython arithmetic remain outside these measurements.

## Reproduce from the project directory

Run from `detection/micropython` with Python 3.11 and FFmpeg on PATH. The measured runs used the existing Python 3.11 environment with NumPy 1.26.4 and FFmpeg 9.0.2. The burst workflow needs NumPy and FFmpeg on the PC. For v4.6 baseline retraining and rebuilding missing original caches, use the procedures in [README.md](README.md) with the FSC22 manifest. The comparison used the existing `v4_6_wideband/tg_model_v46.py` with SHA-256 `3c93afb94965359c510ef28ed6ddc667d179c39d554fa67bad3e051744d75e25`. The checked-in burst export is sufficient to stage and run diagnostics, including when the datasets are unavailable.

```powershell
# When a suitable Python environment is already active, skip the next three lines.
python -m venv .venv-burst
.\.venv-burst\Scripts\Activate.ps1
python -m pip install numpy==1.26.4

$env:OPENBLAS_NUM_THREADS = '1'
python -m algorithm.app.burst_prepare
python -m algorithm.app.burst_calibrate --forest algorithm/sample_audio/forest-ambience.wav
python -m algorithm.app.burst_train `
  --calibration algorithm/results/burst/calibration.npz `
  --development-truck algorithm/sample_audio/forest-with-truck.wav --truck-interval 19 40 `
  --output algorithm/results/burst/fit_final
python -m algorithm.app.burst_evaluate `
  --model algorithm/results/burst/fit_final/tg_model_burst.py `
  --output algorithm/results/burst/replay_check.json
python -m unittest -v tests.test_burst tests.test_v46 tests.test_cleanup
```

Use new output paths for repeated experiments. Feature preparation reuses the validated v4.6 cache split and the corresponding `teacher_audio` WAV cache, so YAMNet scores are required only to retrain the original CNN with teacher supervision. The calibrated command reproduced the shipped burst export byte for byte on the measured environment. Its SHA-256 is `58fe48dd39888b87bbdd01c5e636a6734c1a483c33ead6aa9b66150aba1a1844`. The focused tests cover FFT and score parity, threshold edge, gap recovery, fixed buffer reuse, ADC conversion and tick wrap, acceleration units and staging. Full discovery also collects older tracked tests that import missing pre-v4.6 modules or expect removed file layout.

## Stage and validate on LoPy 1.0

```powershell
python -m algorithm.app.burst_stage_lopy --output algorithm/results/burst/flash_diagnostic
# Add --accel if an ADXL345 is wired and its I2C addresses and pins have been checked.
```

1. Use the original Pycom LoPy 1.0. Inspect the analog bias, gain and voltage on the intended ADC1 input before connecting the microphone. Staged defaults use P16 and 11 dB attenuation. Verify the board revision and wiring. Optional ADXL345 defaults to SDA P9, SCL P10 and address 0x53. [Pycom LoPy pinout](https://pycom.github.io/pydocs/datasheets/development/lopy.html) · [Pycom I2C API](https://docs.pycom.io/firmwareapi/pycom/machine/i2c/)
2. Copy the staged `main.py`, `config.py` and `lopy_burst_probe.py` to `/flash/` and the staged `lib` contents to `/flash/lib/`. Check that the diagnostic image starts and reports free heap. At the REPL interrupt monitoring with Ctrl+C, then run `import lopy_burst_probe; lopy_burst_probe.main()`. It reports heap around imports, allocation, FFT and scoring, minimum sampled free heap and worst synthetic compute time. It does not measure the true instantaneous heap low-water mark.
3. Restart and record serial output under the intended power, Wi-Fi and peripheral settings. Check `late_samples`, `missed_slots`, `clipped_samples`, `valid`, `compute_us` and `heap_free`. A sample more than 100 μs late counts as late. More than 8% late samples invalidates a block. A slot over 2.5 ms late clears history. Exercise multi-hour runs, the optional accelerometer and any separately integrated radio activity. Measure actual capture cadence and worst-case compute plus serial output against the 122 ms slack. A LoRa test requires the correct connected antenna. [Pycom LoPy setup](https://pycom.github.io/pydocs/gettingstarted/connection/lopy.html)
4. Log labeled negative hours and pass-bys from independent forest locations, vehicles and sessions with the deployment microphone. Include wind and rain and annotate event times. Report misses, false confirmations per hour, latency and data-invalid gaps before deciding whether it is suitable for unattended use.
