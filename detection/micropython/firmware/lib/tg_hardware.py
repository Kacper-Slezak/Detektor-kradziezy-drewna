"""Only the analog microphone ADC input required for v4.6 diagnostics.

Target: ORIGINAL Pycom LoPy with the selected SparkFun BOB-12758 (OPA344).
No GPIO alarm output is exposed by this module. Wiring is NOT verified.
"""

class SensorHub:
    def __init__(self, cfg):
        from machine import ADC
        if not cfg.AUDIO_ENABLED or cfg.MODE != 'audio':
            raise ValueError('v4.6 requires audio-only mode')
        attn = getattr(ADC, 'ATTN_' + cfg.ADC_ATTENUATION)
        self.adc = ADC(0)
        self.audio = self.adc.channel(pin=cfg.AUDIO_PIN, attn=attn)

    def read_audio(self):
        return self.audio() / 4095.0
