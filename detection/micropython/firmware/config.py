"""Pycom LoPy v4.6 diagnostic configuration, NOT an alarm-enabled build.

SparkFun BOB-12758 is the selected analog microphone, but its pin assignment,
ADC range, acquisition accuracy and real-world timing MUST be checked on hardware.
"""
MODEL_FLAVOR = 'v4_6'
STARTUP_ACTION = 'diagnose'
MODE = 'audio'
AUDIO_ENABLED = True
AUDIO_PIN = 'P16'  # Example pin only; check LoPy ADC1 wiring first.
ADC_ATTENUATION = '11DB'
AUDIO_RATE_HZ = 4000
WINDOW_S = 2.0
HOP_S = 1.0
VIBRATION_INPUT = 'off'
ACCEL_ENABLED = False
ALARM_OUTPUT_PIN = None
PERSISTENCE_SECONDS = 15
PERSISTENCE_FRACTION = 0.60
COOLDOWN_S = 60.0
RESET_AFTER_S = 8
MAX_LATE_SAMPLES_RATIO = 0.08
MAX_SAMPLE_GAP_US = 250
MAX_PROCESSING_GAP_US = 20000
ENABLE_PHYSICAL_ALARM = False
CLOCK_IS_LOCAL_AND_SYNCED = False
