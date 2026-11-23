# Engine recall follow-up on the original Pycom LoPy

The [later acoustic diagnosis](ENGINE_RECALL_DIAGNOSIS.md) identifies the waveform sources of the rain-and-wind clip and adds duration-aware event comparisons. The original measurements below remain the record of that run.

The real-only retrain raised clean-engine recall from 75.0% to 78.0% relative to the previous burst MLP. Its recall on the fixed 0 dB benchmark fell from 43.3% to 32.3%. Adding three new vehicle recordings recovered part of that loss to 41.5%. Neither retrain reached the original v4.6 CNN's 81.7% clean and 55.5% mixed recall. The validation-selected export is available for diagnostics alongside the previous model. The default firmware model is still the previous burst MLP.

## Data review and acquisition

The original manifest contains 320 isolated engine clips (183 diesel and 137 petrol), 1,275 FSC22 environmental clips and 360 ESC-50 hard negatives. The positive clips are mono 44.1 kHz recordings. Vehicle, microphone distance, forest setting and weather are generally unavailable. FSC22 includes separate forest, animal, wind and rain examples. The fixed 0 dB benchmark contains earlier mixtures of isolated engines and FSC22 background, so it measures one controlled stress condition. It provides no labeled examples of the same vehicle measured at known distances in real forest rain. See the [earlier data audit](BURST_TECHNICAL_REPORT.md#recordings-and-split) for sample rates, clipping and labeling checks.

The local `engine_demo.wav`, vibration demos and earlier v4.7 passing cache come from simulation. In the original training cache, 1,666 rows are marked as augmented. All were excluded from the follow-up optimizer, as were any rows with synthetic augmentation identifiers, validation rows and test rows. Both fits used 5,321 genuine original training windows and 287 windows from the previously used forest development recording. The forest contributes 15% of negative weight. Neither fit used waveform mixing, simulated pass-bys, gain jitter or generated recordings.

The supplied four `-4k.wav` files duplicate their respective full-rate files after resampling. The dry truck and development forest WAV share substantially identical audio in the first eight seconds. They cannot provide independent evidence, and only the forest WAV entered fitting. The rain-and-wind WAV reports FL Studio 2025 as its encoder and has no engine timestamps or recording history in the project. A scan of its one-second slices every four seconds found maximum normalized correlations of 0.17 with the dry truck, 0.12 with forest ambience, 0.29 with forest rain and 0.24 with Caterpillar, allowing any offset in each comparison recording. This screen did not find a near-identical excerpt and cannot rule out reuse under processing or noise. Existing regression tests treat it as mixed-weather audio and expect zero fusion alarms. A zero theft alarm is compatible with an engine being present. The provenance and engine intervals remain unresolved, so the file was used for diagnosis and excluded from fitting. Exact manifest hashes and PCM-prefix checks found no original cross-split duplicates in the previous audit. Unknown ICE vehicle and session identities still leave the possibility of closely related recordings spanning splits.

Five archive recordings address specific coverage gaps. They occupy 61.4 MB under Git-ignored `algorithm/data/real_recall`. The [acquisition manifest](algorithm/real_recordings.csv) pins the media checksums, recording and session identifiers, URLs, license, attribution and training intervals. The files were preserved byte for byte as provided by the publisher, including the published Ogg for the six-minute forest scene. FFprobe confirmed stereo at 44.1–96 kHz. After mono 4 kHz conversion, none of the five reached the PCM near-clipping threshold. The training intervals trim quiet starts and ends based on the archive descriptions and a waveform-level check. They have no independent frame-level annotations. [Sounds of Changes license and attribution terms](https://www.soundsofchanges.eu/use-the-sounds/)

| Recording and credited recordist | Role | Coverage |
|---|---|---|
| John Deere 5820, Sami Laaksonen / Werstas | Train, 1–27 s | Turbo diesel idle and driving in Tampere. [Source](https://www.soundsofchanges.eu/sound/john-deere-tractor/) |
| Ursus C 342, Monika Widzicka / Museum of Municipal Engineering | Train, 5–86 s | Agricultural tractor driving in Szreniawa. [Source](https://www.soundsofchanges.eu/sound/tractor-ursus-c-342-driving/) |
| Peugeot Boxer, Boštjan Troha and Katarina Batagelj / Technical Museum of Slovenia | Train, 2–18 s | Sustained diesel after start in Bistra. [Source](https://www.soundsofchanges.eu/sound/van-peugeot-boxer-turbo-diesel-engine-running/) |
| Gdynia port lorries, Monika Widzicka / Museum of Municipal Engineering | Separate replay | Lorries arriving and leaving; session separate from Ursus. [Source](https://www.soundsofchanges.eu/sound/gdynia-port-container-terminal-1/) |
| Valla forest, Fredrik Johansson | Separate replay | Birds, insects, traffic and an airplane at a forest edge. [Source](https://www.soundsofchanges.eu/sound/valla-forest-nature-reserve-close-to-a-big-road/) |

The two separate archive scenes have clip-level descriptions and no engine onset or offset labels. They were replayed after model selection. They support comparisons of score and confirmation activity, with no way to verify whether individual confirmations align with engines. Gdynia and Valla broaden real validation conditions. The remaining gap is timestamped, naturally wet and windy heavy-vehicle pass-bys from independent forest locations, with distance and microphone metadata. Wikimedia Commons returned HTTP 429 on two attempted media files. The downloads above came directly from the original Sounds of Changes archive.

## Controlled retraining

The first two fits use the existing 32 → 16 → 1 MLP and 512-point DSP. Only the second adds archive training data. The three new sessions contribute 120 windows and 15% of positive weight, balanced by session. After those comparisons the same trainer evaluated two lightweight changes, omitting mean log RMS or shortening bursts to 256 samples. The 256-sample configuration has less time-domain coverage but more processing time per slot. All fits use the same deterministic Adam training and int8 export as the original burst pipeline. See [model and DSP details](BURST_TECHNICAL_REPORT.md#experiments-and-selection).

Model selection used the unchanged 1,201 original validation windows and three existing rain/wind background replays. It favored validation clean recall of at least 82%, FSC22 false-positive rate at most 6% and zero confirmations on the three replay negatives. Within those constraints it favored clip detection and penalized false confirmations and forest false-positive windows. Two-of-two, two-of-three and one-of-two votes were compared at each threshold. One-of-two still requires a full two-window history. The earlier held-out benchmark, including its fixed 0 dB stress features, was read for scoring only after the models and settings were frozen.

| Fit | Threshold | Votes required / span | Validation clean recall | FSC22 FP / 744 | Clips confirmed (engine / negative) |
|---|---:|---:|---:|---:|---:|
| Local real, 512, full features | 0.83 | 1 / 2 | 84.0% | 13 | 40 / 7 |
| Expanded real, 512, full features | 0.73 | 1 / 2 | 83.4% | 16 | 40 / 9 |
| Expanded real, 512, relative features | 0.92 | 1 / 2 | 59.2% | 19 | 35 / 8 |
| Expanded real, 256, full features | 0.74 | 2 / 2 | 85.2% | 17 | 39 / 4 |

All four settings in the table had zero confirmations on the rain/wind validation negatives. The local 512 fit ranked first, with 40 of 47 positive clips confirmed and 7 of 258 negative clips confirmed. The expanded 256 configuration confirmed fewer validation engine clips and remained an ablation. Its held-out split was kept unopened for this experiment.

## Frozen comparison

| Unchanged recording-level test | v4.6 CNN | Previous burst | Real-only local 512 | Real-only expanded 512 |
|---|---:|---:|---:|---:|
| Precision | 81.2% | 87.9% | 92.1% | 88.0% |
| Clean-engine recall | 81.7% | 75.0% | 78.0% | 76.2% |
| F1 | 81.5% | 80.9% | 84.5% | 81.7% |
| Confusion matrix (TP / FP / FN / TN) | 134 / 31 / 30 / 989 | 123 / 17 / 41 / 1,003 | 128 / 11 / 36 / 1,009 | 125 / 17 / 39 / 1,003 |
| FSC22 FP / 732 | 15 | 6 | 9 | 13 |
| Historical 0 dB hits / 164 | 91 (55.5%) | 71 (43.3%) | 53 (32.3%) | 68 (41.5%) |
| Diesel hits / 85 | 74 | 79 | 74 | 77 |
| Petrol hits / 79 | 60 | 44 | 54 | 48 |
| Engine clips with zero hits / 44 | 5 | 3 | 6 | 6 |
| Confirmed engines / 44 | 0 | 32 | 38 | 38 |
| False clip confirmations / 255 | 0 | 5 | 8 | 10 |

The v4.6 15-window rule cannot confirm on these clips, which are at most eight seconds long. The 1-of-2 rule restores six confirmations relative to 2-of-2 on a different fitted scorer, while increasing false clip confirmations. The observed difference combines classifier and rule changes. The two retrains share the same rule. Their difference shows that additional real training recordings improved recall under the earlier 0 dB benchmark by 15 windows relative to the local real-only fit. Clean recall, petrol recall, false-positive windows and false clip confirmations worsened. The data do not establish an overall generalization gain.

All four models had zero confirmed episodes in the 739 seconds of supplied background replay, which includes the 288-second development training recording. On the linked dry truck the previous burst confirmed at 21 s, the local retrain at 22 s and the expanded retrain at 20 s (nominal delays of 2, 3 and 1 s after the existing 19 s onset). v4.6 did not confirm that scene. None confirmed the rain-and-wind truck or Caterpillar replay. Gdynia produced 1, 2, 3 and 1 episodes respectively in the table's model order. Valla produced 4, 22, 11 and 16. Earlier and later transitions in these two untimed scenes have no event-level ground truth and cannot support latency or false-alarm claims.

## Why the wet example was missed

The rain-and-wind waveform is much louder than the dry truck (median −14.1 vs −34.9 dBFS), with no samples near clipping after mono conversion. The median 35–130 Hz to 130–800 Hz energy ratio is −5.8 dB in the wet clip versus +1.0 dB in the dry clip. Lower low-band concentration is consistent with engine cues being masked or with the scene containing a different dominant sound. These measurements cannot confirm an actual engine or assign the discrepancy to masking alone. The previous engine recall loss was concentrated in petrol in the fixed test. Mean log RMS helps clean validation precision/recall, but there is limited evidence that the gain seen in the corpus matches different microphones, distances and weather. Removing it severely degraded validation recall at the selected false-positive tradeoff.

The 512-sample DSP captures 128 ms per 250 ms slot and leaves a 122 ms gap. A counterfactual sweep used the same PCM at five equally spaced starting offsets from 0 to 122 ms, covering each part of the slot in at least one replay. Across those offsets, **none of the 47 wet windows qualified at any phase**. The previous model's maximum was 0.281 for a 0.84 threshold. The local and expanded models peaked at 0.0032 and 0.0019 for thresholds of 0.83 and 0.73. The fully captured v4.6 baseline also stayed below its 0.68 threshold, with a maximum of 0.589. These observations locate the immediate failure upstream of voting. They do not isolate classifier bias from missing positive examples or verify a wet truck annotation.

On the dry truck replay, the previous burst model confirmed somewhere in the recording at just two of five phases. The 1-of-2 retrains confirmed somewhere in the recording at all five, showing sensitivity to timing and the operating rule for borderline or brief events. On Caterpillar, the previous burst produced one positive window at every phase and 2-of-2 voting blocked a confirmation. Both retrains scored every phase below threshold. No measured result justified changing the embedded capture loop for this follow-up.

## Reproduction and deployment

Run from `detection/micropython` using the same Python, NumPy and FFmpeg setup as the [original burst report](BURST_TECHNICAL_REPORT.md#reproduce-from-the-project-directory). Use the existing `algorithm/results/burst/features.npz` and v4.6 results for the unchanged test. The old cache contains historical mixtures. The new fitter excludes them, and the evaluator uses the fixed test mixture features strictly for the requested benchmark. Use fresh output paths for each run.

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
python -m algorithm.app.recall_audio
python -m algorithm.app.recall_train --output algorithm/results/recall/verified_fit
python -m algorithm.app.recall_evaluate --selection algorithm/results/recall/verified_fit `
  --output algorithm/results/recall/verified_report.json
python -m unittest -v tests.test_recall tests.test_burst tests.test_v46 tests.test_cleanup
python -m algorithm.app.burst_stage_lopy --model algorithm/models/tg_model_recall.py `
  --output algorithm/results/recall/verified_flash
```

The checked-in export has 528 int8 weights and is 4,059 bytes. Its SHA-256 is `28c36dc6a9a0f4d9a88a4743d2dbc4735a652b04023e13af2ad4143dc48ad0d1`. Staging copies it into the existing MicroPython loader's expected file and produces about 20 KB of Python files. It uses the same 11 KB of fixed buffers and 122 ms slot budget as the previous model. No on-board runtime, heap or ADC measurements were performed. Portable replay across nine recordings matched every threshold decision from the NumPy feature path, with maximum score deviation under 0.000001. The existing analog microphone path, optional ADXL345 and LoPy heap probe are used as before. Follow the [original board validation procedure](BURST_TECHNICAL_REPORT.md#stage-and-validate-on-lopy-10) for bench measurements.
