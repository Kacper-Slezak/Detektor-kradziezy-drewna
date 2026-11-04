# Integration into the original repository

Your archive contains `python/algorithm/app`, `core`, `data`, `results`, etc.
Keep the desktop Python implementation intact and put this project in your existing `firmware/lopy/` directory.

Suggested structure:

```text
Detektor-kradziezy-drewna/
  detection/
    algorithm/       # existing desktop application
    firmware/
      lopy/
        firmware/    # upload this subfolder's CONTENTS to the LoPy /flash
        tools/       # PC-side serial capture and plotting
        tests/       # desktop regression tests
```

**Important:** Pycom's device imports `config` and `/flash/lib/*` and auto-runs
`/flash/main.py`. It should NOT import the desktop `algorithm` Python package.
Desktop `model.json` is v2 with FFT features; the device's
`/flash/tg_calibration.json` is a different schema/version. Do not copy the
original model file into device flash as a substitute for field calibration.

Do not copy the virtual environment (`.venv`), recordings, fixtures or large
results into the LoPy filesystem.
