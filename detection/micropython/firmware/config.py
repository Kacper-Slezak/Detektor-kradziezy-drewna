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
AUDIO_RATE_HZ = 1000               # experimental software acquisition (not true I2S)
VIBRATION_RATE_HZ = 100
ACCEL_RATE_HZ = 50
AUDIO_FRAME_MS = 50
WINDOW_S = 2.0
HOP_S = 1.0

# Sustained engine detection and motion confirmation; same logic as desktop.
LOW_RATIO_MIN = 0.48               # requires field adjustment (IIR, not desktop FFT)
ENGINE_CONFIRM_WINDOWS = 3
ENGINE_MEMORY_S = 18.0
IMPACT_MEMORY_S = 14.0
IMPACTS_FOR_ALARM = 2
COOLDOWN_S = 15.0

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
HARDWARE_PROFILE = 'lopy-analog-mic-vibration-adxl345-v1'

# Suppress all alarms when sample timing is poor or sensors are missing.
MAX_LATE_SAMPLES_RATIO = 0.08
MAX_SAMPLE_GAP_US = 4000
ALARM_OUTPUT_PIN = None            # e.g. 'P11' (3.3-V logic only); None disables it
ALARM_PULSE_MS = 100

# No network access, Wi-Fi or LoRa TX is performed by this firmware.
# Device telemetry is sent via USB UART as 'TG {json}'.
PRINT_EVERY_WINDOW = True
