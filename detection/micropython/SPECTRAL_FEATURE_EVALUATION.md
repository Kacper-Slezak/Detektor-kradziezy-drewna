# Lightweight engine features and source transfer

**The added peak and temporal features did not improve the matched classifier.** They discriminated some negative categories in isolation, but both augmented logistic probes gave the same transfer recall and precision as the bands-and-RMS control. They also increased false confirmations on the exposed development recordings. The current LoPy firmware and weights remain the working default. This experiment leaves reusable optional feature code and a separate source-screened evaluation procedure.

## Fixed experiment and data exposure

The existing 4 kHz, 512-point FFT, 128 ms acquisition and 250 ms slot schedule were used throughout. Both spectral ranges use the same FFT output as the previous burst. The low region covers approximately 45–350 Hz and the upper region covers 1,300–1,900 Hz. A 3-bin peak spans approximately 23 Hz.

| Logistic probe | Inputs |
|---|---|
| Bands and RMS | Existing 15 log-band means, 15 standard deviations, mean log RMS and its standard deviation |
| Spectral | The same 32 plus mean narrow-peak share and mean local spectral contrast in each region |
| Spectral and ordered | The same 36 plus the proportion of adjacent peaks within two bins and the strongest stable pair's weaker contrast in each region |

Peak share is the winning three-bin power divided by regional power. Contrast compares the winning peak with its nearby shoulders. The ordered features use the chronological acquisition ring and do not join the oldest and newest frames. An adjacent pair is two capture slots separated by 250 ms, with the existing 122 ms gap. All variants use the same source-balanced logistic optimizer and int8 weights. There are no hidden units or extra FFTs.

The three inexpensive fits used **1,303 genuine windows from 336 original training sources** (128 engine and 208 negative). The sample was selected deterministically by source hash, capped at 64 positive sources per engine category and eight negatives per dataset/category. All windows of a sampled source stayed together. Original augmentation rows and all simulation audio were excluded. These are matched representation probes with a bounded training sample, so their absolute performance should not be interpreted as a capacity limit for the full-data model.

On the **previously exposed** 1,201 validation windows, each threshold was selected with two consecutive positives as the confirmation rule. A threshold that met both 80% clean recall and at most 5% negative clip confirmations would take precedence. No setting met both conditions. The fallback ranked eligible clip recall minus twice the negative confirmation fraction, followed by window F1 and negative confirmation fraction. The model exports and thresholds were frozen before scoring the transfer archive. The historical test and its mixed features were excluded. No new audio was acquired.

| Exposed validation | Threshold | Window recall | Window precision | Window AUC | Engines confirmed / 42 eligible | Negatives confirmed / 258 |
|---|---:|---:|---:|---:|---:|---:|
| Bands and RMS | 0.68 | 89.3% | 61.1% | 0.958 | 39 | 25 |
| Spectral | 0.65 | 87.0% | 59.0% | 0.954 | 39 | 29 |
| Spectral and ordered | 0.66 | 86.4% | 59.3% | 0.955 | 39 | 29 |

## Where the descriptors help

The per-file medians below use the same 83 exposed acoustic-probe files as the earlier diagnosis. Each column compares the 47 engine sources against six negative sources of that category. AUC above 0.5 means engines tend to have higher feature values. Small category samples limit precision.

| Feature | Rain | Wind | Thunderstorm | Insects | Helicopter | Train |
|---|---:|---:|---:|---:|---:|---:|
| Low peak concentration | 0.88 | 0.47 | 0.97 | 0.83 | 0.80 | 0.89 |
| Low local contrast | 0.68 | 0.51 | 0.65 | 0.67 | 0.75 | 0.48 |
| Upper peak concentration | 0.68 | 0.71 | 0.30 | 0.43 | 0.15 | 0.38 |
| Upper local contrast | 0.21 | 0.39 | 0.35 | 0.28 | 0.39 | 0.27 |
| Low peak stability | 0.94 | 0.46 | 0.97 | 0.93 | 0.89 | 0.93 |
| Low ordered contrast | 0.80 | 0.62 | 0.89 | 0.77 | 0.65 | 0.70 |
| Upper peak stability | 0.74 | 0.66 | 0.60 | 0.72 | 0.38 | 0.76 |
| Upper ordered contrast | 0.71 | 0.65 | 0.54 | 0.76 | 0.45 | 0.49 |

Low peak concentration and stability were strong against rain and thunderstorm, with little separation against wind. The upper features helped against some weather negatives and behaved differently on mechanical sounds. A stable peak is also present in many non-target sounds. The upper-band SNR found in the wet composite was a property of that mixture and its recorded components. Regional aggregate statistics did not turn it into a transferable engine signature.

## Source-screened transfer

The local full FSC22 archive contains 5-second Freesound excerpts. Before reading any model scores, the transfer procedure restricted the evaluation to the unused VehicleEngine, Generator, Chainsaw, Helicopter and Handsaw categories. It rejected source IDs or exact bytes used in either historical split manifest, exact bytes from the five acquired recordings, IDs with multiple archive class assignments and explicitly simulation-like names. It used one deterministic excerpt per identifiable source ID and up to 24 sources per negative category. This yielded **61 engine, 24 generator, 24 helicopter, 13 handsaw and six chainsaw excerpts**. No files from this group were used to fit models or thresholds documented here. Source IDs and hashes screen known overlaps. Related recordings by the same uploader remain possible. One uploader accounts for 13 engine excerpts, so the 61 clips do not establish 61 independent recording sessions. [FSC22 data descriptor](https://doi.org/10.3390/s23042032) · [FSC22 metadata and archive documentation](https://github.com/IRMIOT/FSC22)

| Model | Frozen threshold | Native TP / FP | Shared 2-of-2 TP / FP | Shared recall | Shared precision |
|---|---:|---:|---:|---:|---:|
| v4.6 CNN | 0.68 | Ineligible | 9 / 6 | 14.8% | 60.0% |
| Previous burst MLP | 0.84 | 8 / 5 | 8 / 5 | 13.1% | 61.5% |
| Local real-only MLP | 0.83 | 15 / 3 | 9 / 2 | 14.8% | 81.8% |
| Expanded real-only MLP | 0.73 | 17 / 6 | 11 / 5 | 18.0% | 68.8% |
| Logistic bands and RMS | 0.68 | 18 / 12 | 18 / 12 | 29.5% | 60.0% |
| Logistic spectral | 0.65 | 18 / 12 | 18 / 12 | 29.5% | 60.0% |
| Logistic spectral and ordered | 0.66 | 18 / 12 | 18 / 12 | 29.5% | 60.0% |

The shared rule makes every excerpt eligible. Native v4.6 requires 15 windows and makes all 128 excerpts ineligible. Missing or extra events within an individual file cannot be labeled from the clip categories, so the table reports clip confirmations and precision. It does not assume that each two-second window in an engine clip contains an engine. Generator and helicopter confusions account for all 12 negative confirmations for each logistic probe. Each augmented probe picked up one engine the control missed and missed one the control picked up. Higher transfer recall for the logistic family came with many more false confirmations, and adding the new features did not improve the tradeoff.

The expanded real-only model's advantage transferred **modestly** beyond the original development recordings. At the same vote rule as the previous burst, it gained six engine confirmations, lost three and had the same total false confirmations. Relative to the local real-only model it gained four and lost two, while adding three false confirmations. The six engine files with wind or wet-road terms in their titles have weak condition labels. With the shared rule, the expanded model and v4.6 both confirmed the same slow wet-asphalt Jeep clip. The previous and local bursts confirmed zero of the six. The logistic probes each confirmed the same different wet-asphalt Jeep excerpt, from the same uploader and likely a related setup. These are small, acoustically related examples without evidence of a broad gain under real forest rain or wind.

## Timing and the controlled wet example

The seven known replays remain development data. All models stayed below threshold on every wet-composite window. The spectral probes peaked at 0.522 and 0.535 against thresholds 0.65 and 0.66. The wet clip remains grouped with its wind, rain and Caterpillar constituents. See the [waveform provenance diagnosis](ENGINE_RECALL_DIAGNOSIS.md#wet-clip-provenance-and-masking).

| Development replay, shared two-consecutive rule | v4.6 | Previous burst | Local real-only | Expanded real-only | Logistic control | Logistic spectral | Logistic ordered |
|---|---:|---:|---:|---:|---:|---:|---:|
| Confirmed episodes across 739 s of background | 2 | 0 | 0 | 0 | 21 | 25 | 25 |
| Dry truck delay after approximate onset, using only fully contained windows | 7 s | None | 4 s | 3 s | None | None | None |

Native rules produced zero confirmed background episodes for the four existing models. The prior burst's native dry-truck confirmation used a window crossing the onset boundary. The local and expanded models each reached a native event-only confirmation after 3 s. The logistic probes had dry-truck episodes elsewhere in the stream, including before its annotated onset. The background includes the linked development forest and is insufficient for a population false-alarm rate. The archived transfer set has no equivalent timestamps, so event-start latency is unavailable there.

## Compute, memory and parity

| Portable path, CPython median across seven benchmark repetitions | Previous burst monitor | 40-input logistic with peaks and order |
|---|---:|---:|
| Extraction-only slot | 1.094 ms | 1.102 ms |
| Slot with a decision | 1.190 ms | 1.128 ms |
| Per-slot p95 | 1.356 ms | 1.377 ms |
| Fixed typed working buffers, including two vote bytes | 11,010 bytes | 11,106 bytes |
| Approx. live numeric payload including int8 weights and 32-bit model constants | 11,870 bytes | 11,474 bytes |
| Weight products on a decision | 528 | 40 |

The optional path reuses the in-place FFT and adds a 192-byte peak history. Its smaller head uses less input scratch space, giving a net 96-byte increase in typed buffers. It scans 116 FFT bins plus a short shoulder around each peak. Median extraction-only time increased by about 1–4% across two desktop runs. The smaller linear head offset that cost on decision slots. Garbage collection, serial output, ADC acquisition and physical LoPy timing were outside the benchmark. The payload estimate does not include interpreter objects, temporary boxed values or sensor drivers. Actual peak MicroPython heap remains unmeasured.

The NumPy FFT and portable class agreed on **every threshold decision across all seven replays and all three fitted probes**. Maximum absolute score discrepancy was **5.64 × 10⁻⁷**. The tests cover feature and score parity, chronological ring order, reset after invalid input, native vote ineligibility, and source-ID/hash filtering. The optional probe is outside firmware startup and is deliberately absent from production staging.

## Decision and reproduction

Keep the present 4 kHz acquisition, model and vote settings. The most useful follow-up signal is low-band peak stability on rain and mechanical negatives, but the current fixed-bin stability and local contrast did not generalize to wind-dominated engine detection. An evidence-gated follow-up should check whether the surviving upper-band structure tracks an engine across time in **timestamped, naturally co-recorded noise**. The existing clip-level transfer results and composite cannot settle that question. The reserve has now been scored and should remain a reported comparison rather than an untouched dataset for later feature selection.

From `detection/micropython`, use the same NumPy and FFmpeg environment as the previous experiments. The four existing frozen exports, original cache and local archives are required. Output paths must be new.

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
python -m algorithm.app.spectral_development --output algorithm/results/spectral/reproduce_fit
python -m algorithm.app.spectral_transfer --frozen algorithm/results/spectral/reproduce_fit `
  --output algorithm/results/spectral/reproduce_transfer.json
python -m unittest -v tests.test_spectral_probe tests.test_engine_diagnose tests.test_recall tests.test_burst tests.test_v46 tests.test_cleanup
```

The frozen-fit JSON records the three configurations, operating points and export hashes. The transfer JSON retains original source identifiers and digests, model hashes, native and common rule counts, replay results and all seven benchmark repetitions. The generated experimental weights and archive audio are kept in ignored directories.
