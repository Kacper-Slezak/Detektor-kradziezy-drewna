# Original LoPy hardware validation and field recording

**Physical status.** Windows exposed no connected serial devices. The bench software, staged bundle, capture reader, replay and split validation were exercised on CPython with a simulated clock, ADC and I2C sensor. Sustained 4 kHz acquisition, ADC behavior, heap headroom and SD latency on a physical LoPy 1.0 remain unmeasured. The default configuration and trained models are preserved. This procedure exercises the shipped burst path as the candidate for field collection.

## Compatibility review

| Surface | What to verify on the original LoPy |
|---|---|
| Board and firmware | Verify LoPy 1.0 on the board itself. Save `os.uname()`, `sys.implementation` and the bench start record. The LoPy4 is a different target. [Original LoPy pinout and setup](https://pycom.github.io/pydocs/datasheets/development/lopy.html) |
| Analog microphone | The burst path uses a callable `ADC(0).channel(pin='P16', attn=ADC.ATTN_11DB)` and assumes 12-bit reads. Confirm ADC1, pin and attenuation on the board. Power the BOB-12758 from 3.3 V with common ground and verify its biased AUD output is within the characterized ADC range. Supply voltage alone does not give that range. [Pycom ADC API](https://docs.pycom.io/firmwareapi/pycom/machine/adc/) · [SparkFun BOB-12758 guide](https://learn.sparkfun.com/tutorials/electret-mic-breakout-board-hookup-guide/all) |
| Timing | The bench and normal monitor share the software scheduler and sample loop. Pycom documents `ticks_us`, `ticks_diff` and `sleep_ms`. Short relative deadlines avoid depending on `ticks_add`. Check timer wrap and stability on the exact firmware version. [Pycom timing API](https://docs.pycom.io/firmwareapi/micropython/utime/) |
| Processing | The bench uses the same PCM conversion, bounded FFT buffers, int8 model and vote rule as the normal burst monitor. The device uses `array` and `math` and needs no desktop ML stack. The v4.6 CNN uses a different acquisition loop and is outside this profile. |
| ADXL345 | Optional I2C defaults to P9/P10, address 0x53 and DEVID 0xE5. The sensor's configured rate is 100 Hz. The application reads the latest XYZ sample once per burst, about 4 Hz, so these readings cannot reconstruct a vibration waveform. [Pycom I2C API](https://docs.pycom.io/firmwareapi/pycom/machine/i2c/) |
| Heap, hashing and SD | On the device verify `gc.mem_free()`, `gc.mem_alloc()`, `ustruct.pack_into()`, SHA-256 and binary writes from packed arrays. The recorder uses the ESP32 little-endian layout. SD requires a suitable expansion board or the documented fixed pins and a compatible FAT card. [Pycom GC](https://docs.pycom.io/firmwareapi/micropython/gc/) · [Binary packing](https://docs.pycom.io/firmwareapi/micropython/ustruct/) · [SHA-256](https://docs.pycom.io/firmwareapi/micropython/uhashlib/) · [SD setup](https://docs.pycom.io/firmwareapi/pycom/machine/sd/) |

The nominal schedule is 512 reads at 250 µs spacing every 250 ms. It samples at **4 kHz within a burst**, with about 128 ms of acquisition and 122 ms of processing time. Intentional gaps occupy about 49% of wall time. The code still attempts every sample index during a late burst, so reads may bunch together. The skipped-start counter counts abandoned scheduled burst starts. Multiplying it by block size estimates unread scheduled samples and excludes the intentional gaps. It does not count hardware conversions discarded by the ADC.

## Stage and operate the exact build

From `detection/micropython` on the PC, stage to new directories. Choose the accelerometer bundle only when a verified sensor is attached.

```powershell
python -m algorithm.app.burst_stage_lopy --bench --output algorithm/results/lopy_validation/flash_audio
python -m algorithm.app.burst_stage_lopy --bench --accel --output algorithm/results/lopy_validation/flash_audio_accel
```

1. Back up the existing application files. Record the physical board revision, on-board firmware version, board ID, microphone/enclosure, supply, SD card and peripheral setup. Upload one staged directory to `/flash/` with its layout intact. Transfer the model in binary mode and reset after upload so the model loaded in memory matches the file on flash. No firmware upgrade is planned.
2. Open a serial REPL and save a separate plain UTF-8 console log for each run. Match the settings for the expansion board. Normal startup still runs the burst monitor. Verify `READY_DIAGNOSTIC_ONLY` and valid `TG` windows after warm-up. Confirm no GPIO alarm is active. Stop the monitor with Ctrl+C before entering the optional bench. [Pycom serial troubleshooting](https://pycom.github.io/pydocs/gettingstarted/troubleshooting-guide.html)
3. Run the REPL commands below. The optional bench verifies the on-device model SHA-256 before measuring and emits `LBD` records with build metadata, counters, latest scores, confirmation state and optional XYZ. Run only one ADC loop at a time. Reset to go back to ordinary monitoring.

```python
import os, sys
print(os.uname(), sys.implementation)
import lopy_bench
lopy_bench.run(seconds=60, report_every=4, board_id='lopy01')
```

## Physical measurements and proposed acceptance gates

Use the field supply, gain, enclosure and peripheral settings. The limits below are proposed acceptance gates for this pipeline. They are not manufacturer specifications.

| Step | Procedure and acceptance |
|---|---|
| ADC range, bias and microphone | Scope AUD in quiet and with normal and loud input. Check that it stays within the characterized range with headroom. For an electrical calibration, disconnect the microphone output before applying three known safe DC levels. The decoded means should increase monotonically and deviate from the fitted line by no more than 5% of the checked span. Record noise floor and gain. Require ≤0.1% rail reads on representative input. Test deliberate clipping separately to confirm the counter, and inspect the scope for earlier compression. |
| Known audio and aliasing | Capture quiet and a steady in-band tone, excluding transitions. With 512 samples, expect the strongest Hann FFT bin within 7.8 Hz of the known tone. Compare a same-amplitude out-of-band tone and its in-band alias using a controlled source. Use at least 20 dB alias attenuation as a proposed target, or report the measured limitation. The analog anti-alias response is uncharacterized. Keep all bench stimuli out of the field dataset. |
| Live timing | Run 900 s without SD. Require individual and aggregate burst spans within 1% of nominal, no saturated timing slots, at most 0.1% of waits more than 100 µs late and maximum in-burst gap ≤500 µs. Require zero invalid blocks, abandoned starts and overruns, with ≥10 ms minimum sampled slack. Check absolute clock accuracy against a calibrated tone or an independent timing measurement. |
| DSP and inference | Require one decision per second after two seconds of valid warm-up, without missing decisions. Require ≤240 ms from final-slot start to score ready. This includes final-slot acquisition and computation. It differs from onset-to-confirmation latency. Compare scores and confirmation flags against the PC replay from the recorded blocks. Require scores within 0.0005 and identical threshold decisions. |
| ADXL345 | With the board stationary, verify the gravity axis and rotate through each axis. Require a gravity-vector magnitude between 0.85 and 1.15 g in stable positions and correct sign/orientation. If acceleration will be used in the field, repeat timing and soak with it enabled. Require one I2C read per captured slot and zero I2C errors. |
| Heap and continuity | Soak for 8 h without recording under representative configuration. Require clean finish, three or more periodic summaries, sampled free heap ≥8 KiB and successful 4 KiB contiguous allocation after GC at the beginning and end. Allow ≤1 KiB drop from the first periodic post-GC reading to the lowest later post-GC reading. Inspect resets, GC duration and any trend separately. |
| SD recording | Record 300 s with the real microphone and intended sensors. Require the same numerical gates, one complete file, matching raw and log slot counts and identical digests after copying. Retain worst SD and flush time. Compare with the timing-only run using the same configuration. |

Heap probes sample before cleanup and after FFT/inference or GC. They can miss shorter allocation peaks. The fixed 4 KiB allocation checks one contiguous request after GC with timing paused. A failure despite apparently sufficient aggregate free heap can indicate fragmentation or firmware heap constraints. It does not report the exact largest block. The diagnostic loop adds work. Compare with the ordinary monitor as a control if console or measurement overhead materially affects slack.

```python
lopy_bench.run(seconds=900, report_every=16, board_id='lopy01')
lopy_bench.run(seconds=28800, report_every=16, board_id='lopy01')
```

```powershell
python -m algorithm.app.lopy_bench_report algorithm/data/lopy/logs/lopy01_timing.txt --profile bench
python -m algorithm.app.lopy_bench_report algorithm/data/lopy/logs/lopy01_soak.txt --profile soak
python -m algorithm.app.lopy_bench_report algorithm/data/lopy/logs/lopy01_sd.txt --profile sd
```

The CLI exits nonzero for failed numerical gates or unexpected firmware identity. Pair any passing report with the verified board, wiring, raw logs and test setup. The device's clock and GPIO/ADC conversion timing cannot be certified by desktop simulation.

## Record the actual microphone path

Use a preformatted, compatible SD card. At 512 samples, allow about 8.3 kB/s or 30 MB per hour. Recording writes only a new `/sd/*.lopy` file, with a limit of one hour per file. Keep all files from the same session together. Wait for the run to finish naturally before removal. An interrupt or failed write leaves an incomplete file that the strict importer rejects. Preserve it separately for investigation.

```python
from machine import SD
sd = SD()
os.mount(sd, '/sd')  # Skip if already mounted.
lopy_bench.run(seconds=300, record_path='/sd/s001_test.lopy',
               session_id='s001', board_id='lopy01', capture_kind='bench')
```

Use `capture_kind='field'` for observing actual field activity, and enter a UTC anchor from the operator's synchronized clock. Emit or note a distinctive sync mark at the start and end on both the LoPy and independent reference recorder. Use them to estimate offset and drift. The manually entered UTC anchor alone does not support event latency.

```python
lopy_bench.run(seconds=300, record_path='/sd/s012_part1.lopy',
               session_id='s012', board_id='lopy01', capture_kind='field',
               start_utc='2026-11-22T13:20:00Z')
```

The versioned header holds the build/model, time anchor and acquisition setup. Each record contains slot timing, misses, clipping, validity, PCM16 and per-read lateness. The stored sample is exactly `(adc12 << 4) - 32768`, retaining all 12 ADC bits. The estimated request time is the relative burst start plus `i × 250 µs + lateness[i]`. The timestamp is taken before the read. Conversion delay and instrumentation overhead remain. The lateness field saturates at 65,535 µs and flags the slot. Neither intentional gaps nor missed blocks are filled.

Copy the original to `algorithm/data/lopy/raw/`. Keep logs, references and metadata in the same ignored dataset tree. The importer checks the footer, sequence, sample ranges and timing consistency. It outputs ADC min, max, mean, rail count and byte offsets for both raw arrays. The optional replay requires the same model hash.

```powershell
python -m algorithm.app.lopy_capture algorithm/data/lopy/raw/s012_part1.lopy --model firmware/lib/tg_model_burst.py --output algorithm/data/lopy/index/s012_part1
```

`capture.json` marks successful import. `slots.csv` preserves flags and offsets. Join `replay.csv` with live summaries using `last_slot = stats.slots - 1`. `last_block_end_us` is the capture end before inference. Keep the bursts separate. Concatenating them would compress time and create misleading event cadence. For the tone check, read valid bursts with `read_header` and `read_slots` from `algorithm.app.lopy_capture`, unpack the little-endian PCM, subtract its mean, apply a Hann window and compute `numpy.fft.rfft` at the nominal in-burst rate. Compare powers at matched gain and signal levels.

## Sessions, events and split isolation

Plan assignments before reviewing model scores. Use multiple vehicles, sites, days and sensor placements. Example distance bands are **5, 15, 30 and 60 m** when the site permits. Record the actual or estimated closest distance and uncertainty. Keep microphone, gain and enclosure fixed for the primary domain and record any changes for separate evaluation.

| Collect | Coverage |
|---|---|
| Diesel engines, trucks and tractors | Idle, cold start, acceleration, approach, pass-by, departure and stopped engine. Vary make, load, orientation and speed. Include independently observed passes near and below the audibility limit. |
| Natural background | Long quiet periods, wind and gusts, rain, wet ground, birds and insects. Retain long uninterrupted negatives, including weather transitions, to measure confirmations per hour. |
| Hard negatives | Chainsaws, generators, aircraft, tools, human activity and impacts. Record enough history around each sound for event rules. Apply a consistent project definition for other vehicle or engine sounds. |
| Natural mixtures | Capture actual concurrent engines and environmental noise. Retain all planned passes, including misses. Keep waveform mixtures, speaker playback and generated audio outside field training and final test. |

Log weather, distance and method, supply, build, source identity, mounting, wind protection, device IDs and annotation confidence. A separate continuous reference recorder can label events during the LoPy gaps. Keep the reference in its own domain and within the same group as the LoPy capture. Label onset and offset from observer notes or synchronized video/audio, independently of classifier scores. Mark ambiguous intervals `uncertain` and leave unlabeled gaps unlabeled. For event latency target synchronization uncertainty ≤0.25 s, otherwise report the timing limitation.

Assign whole groups to `train`, `validation` or `test`. Keep repeated captures from the same known vehicle or site/day together even across devices or files. All derivatives inherit that split. Hold final test sessions, sites and vehicles apart where feasible. The historical test, FSC22 transfer, forest/truck development replays, rain-and-wind composite and its constituents, and all bench/playback recordings are already exposed. The new final test should use fresh sessions and remain unopened until that test is frozen. Log its first evaluation and use development for later decisions.

Example `algorithm/data/lopy/catalog.json` under the ignored tree. Paths are relative to that catalog and `site_date` is the local observation date.

```json
{
  "sessions": [
    {
      "session_id": "s012", "group_id": "group12", "site_id": "site-a",
      "site_date": "2026-11-22", "split": "train", "exposure": "fresh",
      "vehicle_ids": ["truck07"], "weather": "light rain"
    }
  ],
  "recordings": [
    {
      "file": "raw/s012_part1.lopy", "session_id": "s012",
      "annotation_source": "observer-clock reference audio and video",
      "sync_method": "start and end marks", "sync_uncertainty_s": 0.10,
      "events": [
        {"start_s": 12.4, "end_s": 21.5, "label": "truck", "distance_m": 30,
         "motion": "pass_by", "confidence": "reviewed"}
      ]
    }
  ]
}
```

The builder checks field-capture metadata, group isolation, same-vehicle and site/day associations, exact duplicate PCM, UTC anchors and non-overlapping labels within the audio span. It records both file and PCM digests. Review provenance for processed duplicates and recording setup similarities that IDs and hashes cannot detect. When aligning labels to windows, use eight contiguous valid slots per one-second hop, reset history at invalid or abandoned starts, and use only captured windows fully contained in an annotated interval for window metrics. Preserve boundary and uncertain windows for event review.

```powershell
python -m algorithm.app.lopy_dataset algorithm/data/lopy/catalog.json --output algorithm/data/lopy/manifest-v1.json
python -m algorithm.app.lopy_dataset algorithm/data/lopy/catalog-next.json --previous algorithm/data/lopy/manifest-v1.json --output algorithm/data/lopy/manifest-v2.json
```

Keep the latest published manifest as `--previous` for every update. Once a manifest contains a final test, the prior-manifest check locks membership and annotations for that test, plus the prior session assignments and original recording identities. Report valid event denominators, false confirmations per negative hour and measured onset-to-confirmation delay where synchronization permits.

## Desktop checks completed

The 38 focused tests passed, including simulated tick wrap, skipped-slot resynchronization, complete PCM/timing import and same-model replay, truncation rejection, opt-in staging, and split-lock tests. Full desktop discovery ran 65 tests and reported the nine existing legacy import/layout errors for missing prior-version modules. These checks provide no physical ADC, heap, timing or SD measurements.
