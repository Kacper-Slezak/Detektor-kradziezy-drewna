"""Settings for ORIGINAL Pycom LoPy (Pycom firmware; not generic ESP32).

IMPORTANT: Change pinouts and sensor types to match the actual electronics.
The defaults are a documented WIRING EXAMPLE, not a claim about your hardware.
"""

# Choose 'monitor', 'calibrate' or 'diagnose'. Calibration needs quiet surroundings.
STARTUP_ACTION = 'monitor'
MODE = 'fusion'                    # 'audio', 'vibration' or 'fusion'

AUDIO_ENABLED = True
AUDIO_PIN = 'P16'                   # analog microphone OUT (amplifier, centered at mid-supply)

VIBRATION_INPUT = 'analog'          # 'analog', 'digital', or 'off'
VIBRATION_PIN = 'P17'
VIBRATION_ACTIVE_LEVEL = 1          # for digital detectors

ACCEL_ENABLED = True
ACCEL_SDA_PIN = 'P9'
ACCEL_SCL_PIN = 'P10'
ACCEL_I2C_ADDRESS = 0x53            # ADXL345 (ALT ADDRESS tied LOW)

# Pycom ADC; P13..P20 are ADC1 inputs. Safe range is 0..3.3 V.
ADC_ATTENUATION = '11DB'
# Default old LoPy rate. Set to 4000 to EXPERIMENT with v3 wideband FFT1024.
# 4 kHz software ADC + FFT is NOT hardware validated and may fail closed.
AUDIO_RATE_HZ = 1000
VIBRATION_RATE_HZ = 100
ACCEL_RATE_HZ = 50
AUDIO_FRAME_MS = 50
WINDOW_S = 2.0
HOP_S = 1.0

# Conservative starter settings, NOT empirically calibrated classifier weights.
# Votes on 1-second FFT frames, one output each second.
ENGINE_WIDE_SCORE_MIN = 0.76     # applies only to 4 kHz wideband pathway
ENGINE_WIDE_RATIO_MIN = 1.20     # 250..900Hz energy / 35..230Hz energy
ENGINE_SCORE_MIN = 0.72
ENGINE_RMS_GATE_FACTOR = 0.60      # normal path: scale of calibrated noise floor
ENGINE_LOW_RIDGE_SCORE_MIN = 0.62  # experimental: persistent 70..109 Hz diesel order
ENGINE_LOW_RIDGE_RMS_GATE_FACTOR = 0.35  # only for low_ridge, spectral restrictions apply
ENGINE_CONFIRM_WINDOWS = 3        # at least 3 matching candidates
ENGINE_VOTE_S = 4.0               # of the last 5 one-second decisions
ENGINE_MEMORY_S = 25.0             # grace period after engine confirmation
IMPACT_MEMORY_S = 20.0             # 3 separate physical events, not 3 windows
IMPACT_PRE_ENGINE_S = 2.0          # small allowance for engine confirmation delay
IMPACTS_FOR_ALARM = 3
COOLDOWN_S = 60.0                  # one notification per evidence episode

# Minimum detector floors, not absolute guarantees of real-world performance.
MIN_AUDIO_RMS = 0.008
MIN_AUDIO_TRANSIENT = 3.0
MIN_VIBRATION_RMS = 0.020
MIN_VIBRATION_PEAK = 0.070
MIN_ACCEL_DYNAMIC_RMS = 0.015     # ADXL345 values are g
MIN_ACCEL_PEAK = 0.055

# Calibration uses quiet 2-s windows and robust median/MAD.
CALIBRATION_WINDOWS = 30
CALIBRATION_FILE = '/flash/tg_calibration.json'
HARDWARE_PROFILE = 'lopy-analog-mic-vibration-adxl345-v3-1k' if AUDIO_RATE_HZ == 1000 else 'lopy-analog-mic-vibration-adxl345-v3-4k'

# Suppress all alarms when sample timing is poor or sensors are missing.
MAX_LATE_SAMPLES_RATIO = 0.08
MAX_SAMPLE_GAP_US = 4000
MAX_PROCESSING_GAP_US = 20000      # fail closed if processing loses >20ms audio
ALARM_OUTPUT_PIN = None            # e.g. 'P11' (3.3-V logic only); None disables it
ALARM_PULSE_MS = 100

# No network access, Wi-Fi or LoRa TX is performed by this firmware.
# Device telemetry is sent via USB UART as 'TG {json}'.
PRINT_EVERY_WINDOW = True

# --- Timber Guard v4 experimental learned engine detector ---
# The training environment cannot validate analog sampling on LoPy.
# AUDIO_RATE_HZ=4000 unlocks wide-band ML features but is EXPERIMENTAL.
MODE = 'audio'
STARTUP_ACTION = 'diagnose'
VIBRATION_INPUT = 'off'
ACCEL_ENABLED = False
# Set to True only following independent field validation.
ENABLE_PHYSICAL_ALARM = False
# Never infer local time from an unsynced ESP32 RTC; NTP/local-time setup is
# deliberately NOT included. False means UNKNOWN and no clock-driven alarm.
CLOCK_IS_LOCAL_AND_SYNCED = False
WORK_START_HOUR = 8
WORK_END_HOUR = 18
WEEKEND_DAYS = (5, 6)
ML_SCORE_THRESHOLD = 0.50  # research baseline; not calibrated probability
PERSISTENCE_SECONDS = 15
PERSISTENCE_FRACTION = 0.60
RESET_AFTER_S = 8

# Timber Guard v4.2: INT8 tiny student distilled from YAMNet on a PC.
# This setting is an EXPERIMENT for original LoPy software ADC capture.
MODEL_FLAVOR = 'v4_2'
AUDIO_RATE_HZ = 4000
# Real alarm remains DISABLED and off-hours unknown until RTC is verified.
ENABLE_PHYSICAL_ALARM = False
CLOCK_IS_LOCAL_AND_SYNCED = False

# Strict timing: a 4-kHz sample is due every 250 us. If Python loses samples,
# v4.2 must mark the window invalid instead of emitting an alarm.
MAX_SAMPLE_GAP_US = 250
