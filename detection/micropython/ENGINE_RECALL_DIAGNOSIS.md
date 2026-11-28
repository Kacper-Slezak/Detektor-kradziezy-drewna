# Engine recall diagnosis on existing recordings

The [spectral feature follow-up](SPECTRAL_FEATURE_EVALUATION.md) compares the proposed small descriptors, audits source transfer and measures their portable cost.

**The rain-and-wind example is a wind-dominated composite.** Its engine component matches the existing Caterpillar recording. It was approximately **18 dB below the wind** over the analyzed interval. Subtracting the exact wind recording offline restored some v4.6 and previous burst detections. Both real-only fits still missed the residual at their frozen thresholds. The evidence points first to masking and differences in what the models learned from noisy examples. It also shows why the wet clip cannot validate performance on an independently recorded forest pass-by.

No neural network was trained, no audio was acquired, and no weights, deployed thresholds, vote rules or firmware were edited. The new tools expose waveform reuse, acoustic feature distributions and vote-rule eligibility. The historical held-out test and its stress features were excluded from this analysis.

## Evidence and prior exposure

| Material | Use in this diagnosis |
|---|---|
| Original validation split, 169 positive and 1,032 negative windows | Previously exposed during model and threshold selection. Four frozen score distributions, feature distributions and clip-event comparison. |
| Existing 169 validation 0 dB stress windows | Previously exposed simulated mixtures from validation recordings. Read the fixed feature cache for threshold-free ranking and scalar sensitivity only. |
| 47 ICE validation recordings and 36 negative recordings | Re-extracted 4 and 8 kHz features from original archive bytes. Six deterministic examples each of rain, wind, thunderstorm, insects, helicopter and train. Statistics use one median per file. |
| Supplied forest and truck recordings | Previously exposed development replays. Forest ambience shares the dry truck's background and influenced fitting. The dry truck's 19–40 s label is an approximate development annotation. |
| Three acquired training excerpts and two acquired scene replays | Existing files only. Compare gain and acoustic coverage. The two scene replays have weak labels from the publisher and no engine onset times. |

The analysis reads the pinned original v4.6, previous burst, local real-only and expanded real-only exports. The JSON records their SHA-256 hashes. No reported AUC is an independent performance estimate or a basis for a new operating threshold.

## Wet clip provenance and masking

The middle 20 s of `rain-wind-truck.wav` correlate **0.9915** with `wind-lake.wav` at zero lag after mono 4 kHz conversion. A gain estimate using the first five seconds alone was 1.0007. After subtracting that aligned wind, the residual from 19–35 s correlated **0.9788** with `catterpillar.wav` when the Caterpillar audio was shifted approximately **3.231 s later** in the wet clip. The residual also matched `rain-in-forest.wav` at zero lag. A fit to the three aligned components gave gains of approximately **1.000 wind, 0.990 engine and 0.997 rain**. Reconstruction error was **−35.5 dB** relative to the scene inside the fit and **−37.9 dB** outside it. This is strong evidence of shared audio, with most of the waveform explained even outside the fitting interval. Keep these four files in one provenance group for evaluation. This supersedes the earlier inconclusive duplicate check.

| Wet replay, frozen thresholds | v4.6 | Previous burst | Local real-only | Expanded real-only |
|---|---:|---:|---:|---:|
| Threshold | 0.68 | 0.84 | 0.83 | 0.73 |
| Highest original score | 0.589 | 0.272 | 0.0017 | 0.0010 |
| Highest over five capture phases | — | 0.281 | 0.0032 | 0.0019 |
| Highest after aligned wind subtraction | 0.876 | 0.940 | 0.762 | 0.614 |
| Positive windows after aligned wind subtraction | 5 | 2 | 0 | 0 |

The wind-only removal uses the exact reference recording and is an offline counterfactual. The script scores the residual in memory. It never exports an audio file or supplies the residual to training. None of the original wet windows reached threshold even when the full capture slot was covered across alternate phase replays. Adjusting only the mean log-RMS input by −12 dB, +12 dB or replacing it with its training mean also recovered zero windows. That leaves substantial spectral masking and learned score differences after controlling for the most obvious timing and level effects.

The reconstructed Caterpillar component was **−18.2 dB relative to wind overall** in the 19–35 s fit interval. Band estimates against combined wind and rain show why reweighting the spectral view is worth investigating. These are source-component estimates from the known composite, not a live microphone SNR measurement.

| Band | Engine vs wind and rain |
|---|---:|
| 35–130 Hz | −25.3 dB |
| 130–350 Hz | −26.6 dB |
| 350–800 Hz | −13.5 dB |
| 800–1,300 Hz | +1.1 dB |
| 1,300–1,900 Hz | +6.9 dB |
| 1,900–2,700 Hz | +7.1 dB |
| 2,700–3,800 Hz | +4.9 dB |

Some surviving engine energy is in the existing 4 kHz passband. The wet clip has only about 0.21% of its total 35–3,800 Hz energy above 1,900 Hz, versus 0.03% for wind-lake and 7.56% for Caterpillar. A high-band proportion alone will confuse some environmental sounds. The existing forest rain clip places about 41.8% of its energy there.

Inside the current passband, the 1,300–1,900 Hz share of 35–1,900 Hz energy at 4 kHz was 0.29% for the wet clip, 0.06% for wind-lake, 9.23% for fully contained dry-truck windows and 48.02% for forest rain. On the 83-file probe this descriptor had AUC 0.697 against all selected negatives. It is a useful measurement to combine with spectral structure or temporal evidence rather than a stand-alone engine criterion.

## Missed windows and training coverage

The same 4 kHz burst descriptors below are measured on the validation windows for all four scorers. “Hit” means the frozen classifier crossed its own threshold on a positively labeled window. “Low-band color” is the mean log spectral power of the first three burst bands relative to bands 5–11. Both features have substantial distribution overlap between hits and misses.

| Model | Median log RMS, hit / miss (dBFS) | Median low-band color, hit / miss (dB) | Whole positive clips with zero hits / 47 |
|---|---:|---:|---:|
| v4.6 | −25.0 / −31.4 | 13.9 / 11.4 | 5 |
| Previous burst | −24.9 / −31.8 | 13.8 / 11.8 | 1 |
| Local real-only | −24.9 / −33.1 | 14.1 / 11.2 | 2 |
| Expanded real-only | −24.9 / −33.1 | 13.9 / 11.8 | 2 |

Across the four scorers the hit-window RMS 10th percentiles were around −34 to −33 dBFS; miss-window 90th percentiles ranged from −23 to −21 dBFS. The two real-only fits missed entire validation engine clips with median levels around −35 and −34 dBFS, respectively, compared with −25 dBFS for detected clips. The number of whole-clip misses is small. Separately, wet and wind-lake windows were both near −14 dBFS and had nearly identical low-to-mid energy ratios (−5.74 and −5.98 dB). Absolute level helps within the isolated corpus and does not identify an engine in wind. Even without changing spectral inputs, a −12 dB scalar intervention reduced 0 dB validation hits from **106 to 65** in the previous burst and **90 to 53** in the expanded fit. This is sensitivity to one input, not a physical gain experiment.

| Exposed validation, positive scores against FSC22 negatives | v4.6 | Previous burst | Local real-only | Expanded real-only |
|---|---:|---:|---:|---:|
| AUC, clean engines | 0.974 | 0.984 | 0.989 | 0.987 |
| AUC, fixed 0 dB mixtures | 0.944 | 0.963 | 0.918 | 0.922 |
| Frozen-threshold 0 dB hits / 169 | 108 | 106 | 78 | 90 |
| 10th-percentile 0 dB positive score | 0.414 | 0.512 | 0.040 | 0.041 |

The expanded fit did improve noisy-window ranking and hits over the local real-only control. Its AUC still fell below the previous burst, so a change in threshold alone cannot explain the difference. The three added training sessions cover vehicle types and operating states, primarily at ordinary source levels. Their median RMS levels were −23.8 dBFS (John Deere), −30.4 (Ursus) and −17.0 (Peugeot). They did not add labeled engines under strong wind or rain. The lorry and forest-traffic scenes were replay-only. The earlier burst training included background mixtures and gain jitter. Comparing it with either real-only fit changes several things at once, so the AUC difference cannot be assigned to one removed technique. The clean-to-noisy ranking loss and the near-zero scores in the lower tail point to a coverage and generalization issue worth addressing ahead of network complexity.

## Sampling, spectral detail and temporal aggregation

| Descriptor, AUC on 47 engines vs 36 selected negatives | 4 kHz, 128 ms | 4 kHz, 250 ms | 8 kHz, 128 ms |
|---|---:|---:|---:|
| 35–130 Hz / 130–800 Hz energy ratio | 0.828 | 0.814 | 0.828 |
| Strongest ~24 Hz share of 45–350 Hz energy | 0.812 | 0.840 | 0.813 |
| Mean harmonic contrast across eight frames | 0.686 | 0.731 | 0.687 |
| 75th-percentile harmonic contrast | 0.702 | 0.680 | 0.702 |
| Best adjacent pair's lower harmonic contrast | 0.712 | 0.651 | 0.710 |
| 1,900–3,800 Hz energy share | — | — | 0.772 |

All probes use 250 ms slot spacing and fixed two-second windows. The 8 kHz comparison holds the capture duration and frequency resolution constant. Its matched low-band results differ little from 4 kHz, while the added upper band contains distinct information. The 250 ms probe both fills the gap and resolves narrower spectral peaks. Its modest peak-share improvement and mixed temporal results cannot separate those two effects. In the narrower comparison with 18 weather negatives, peak share scored 0.778, 0.806 and 0.779 in the same geometry order. RMS alone scored 0.517 against all selected negatives at current geometry. The probes use file-level labels and independent per-file medians within this exposed subset, with no threshold fitting.

The current 512-sample block has 7.8125 Hz FFT bins. Pooling them into 15 log-power means preserves broad spectral color and discards individual narrow lines. The MLP's time mean and standard deviation preserve variability and are unchanged by reordering frames. A narrow spectral peak computed on existing FFT powers, or the best adjacent pair of a gain-relative descriptor, would retain information currently discarded. An adjacent pair helps harmonic contrast at the existing geometry in this subset, including against weather negatives (AUC **0.747**, versus **0.703** for the mean), and fares worse at 250 ms. None of these descriptors alone distinguishes the wet composite reliably. Its adjacent harmonic score was nearly the same as wind-lake (8.85 vs 8.88 dB). A bank of narrow peaks or harmonic contrasts costs extra operations per captured frame. A single peak-share feature and an adjacent short-window statistic can reuse the existing FFT powers and small frame history.

At 4 kHz, the current slot leaves 122 ms for FFT, inference, sensors and diagnostics. Filling an entire 250 ms slot leaves no intentional processing gap on the existing single acquisition loop. Switching to 8 kHz for the same capture duration would require a 1,024-point transform, approximately 2.22 times as many radix-2 butterflies and roughly twice the typed PCM and FFT payload. The available application heap and timing on the original board are unmeasured. The evidence supports examining gain-relative structure inside 4 kHz first. [Original Pycom LoPy documentation](https://pycom.github.io/pydocs/datasheets/development/lopy.html)

## Event comparison and duration bias

Native v4.6 confirmation requires **9 hits within a full 15-window buffer**. With a two-second window and one-second hop, filling that buffer requires at least 16 seconds of contiguous audio. The exposed validation clips are too short, so v4.6 has **zero eligible clips** under its native rule. For a full two-window rule, five of 47 positive clips are too short or lack contiguous votes. Every negative clip is eligible for a two-window rule. The new event audit splits runs on missing or invalid hops, reports eligibility by class, and replays common rules at the frozen thresholds.

| Same fixed validation rule | v4.6 | Previous burst | Local real-only | Expanded real-only |
|---|---:|---:|---:|---:|
| At least one hit, detected engines / 47 | 42 | 46 | 45 | 45 |
| At least one hit, negative clips with a hit / 258 | 24 | 12 | 7 | 9 |
| Two consecutive, confirmed engines / 42 eligible | 34 | 35 | 36 | 36 |
| Two consecutive, negative confirmations / 258 | 13 | 8 | 4 | 3 |
| One of two, confirmed engines / 42 eligible | 37 | 41 | 40 | 40 |
| One of two, negative confirmations / 258 | 24 | 12 | 7 | 9 |

On the supplied long background replays all native rules produced zero episodes. A common two-consecutive rule produced **two v4.6 episodes on the development forest**, with zero for the bursts. The current thresholds differ among models, so the common-rule comparison controls voting and eligibility while retaining the models' original operating points.

The dry-truck latency comparison also depends on whether the rule can count a window overlapping the annotated onset. Whole-stream replay gave the previous burst its first native confirmation at 21 s and the expanded fit at 20 s. When votes start empty on the first fully contained window, the previous burst has no 2-of-2 confirmation, the expanded fit confirms after 3 s under either 1-of-2 or 2-of-2, the local fit confirms after 3 s under 1-of-2 and 4 s under 2-of-2, and v4.6 confirms after 7 s under 2-of-2. The wet composite has no original threshold hit to pass on to any temporal rule. Report both whole-stream behavior and event-only latency on timed data. Report production alarm policy separately from classifier confirmations.

## Prioritized recommendations

1. **Fix provenance and comparison first.** Treat the wet clip as a controlled composite and group it with wind-lake, rain and Caterpillar. Keep the linked dry truck and forest within one development group. Report native persistence, common-rule confirmation and classifier window scores separately. Keep clips ineligible for a rule out of that rule's recall denominator.
2. **Characterize wind suppression and input gain before further fitting.** The exact-reference subtraction test shows that wind removal can restore v4.6 and previous burst evidence and that it may still leave the real-only scores below threshold. The component spectra identify 800–1,900 Hz as a useful range to check with existing PCM or on the bench. Measure analog headroom and wind protection separately, and compare relative band shape against absolute RMS. Low-band attenuation can also hurt less-masked engines, so the wet result alone does not justify a production filter.
3. **Keep the existing acquisition rate and compare small spectral and temporal probes on distinct development sources.** Reuse FFT powers for narrow peak concentration or gain-relative higher-band energy. Retain short ordered evidence or an adjacent-pair statistic. Their measured advantages depend on the descriptor and capture geometry. Preserve both context-based voting and event-only reporting. Delay longer capture or 8 kHz changes until there are timed examples showing an advantage and the original LoPy can meet the sampling deadline.
4. **Resolve remaining evidence gaps before training or expanding the dataset.** Review timestamps, label confidence and session identity for existing candidates. The unresolved generalization question is whether timed engines under naturally co-recorded weather are detected at operational distances. Keep any eventual confirmation data separate from the corpus used for these probes.

## Reproduce the diagnosis

Use the same Python, NumPy and FFmpeg environment and the existing frozen exports and feature cache from the [recall follow-up](RECALL_TECHNICAL_REPORT.md). The expanded export and its selection record are read from the existing ignored selection directory. This command performs no training or acquisition.

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
python -m algorithm.app.engine_diagnose --output algorithm/results/diagnostics/diagnosis_replay.json
python -m unittest -v tests.test_engine_diagnose tests.test_recall tests.test_burst tests.test_v46 tests.test_cleanup
```

The JSON includes per-file feature quantiles and source/model hashes for the main comparisons. The regression tests cover window alignment, offset matching, valid-hop eligibility, tied ranking and onset timing. All runtime measurements in this diagnosis are desktop observations or arithmetic estimates. No physical hardware was exercised.
