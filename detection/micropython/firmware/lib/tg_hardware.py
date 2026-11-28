"""Analog microphone and optional ADXL345 for LoPy diagnostics.

Target: ORIGINAL Pycom LoPy with the selected SparkFun BOB-12758 (OPA344).
No GPIO alarm output is exposed by this module. Wiring is NOT verified.
"""

class ADXL345:
    """External accelerometer on I2C. Report three axes in g."""

    def __init__(self, i2c, address):
        self.i2c, self.address = i2c, address
        if i2c.readfrom_mem(address, 0x00, 1)[0] != 0xE5:
            raise OSError('Expected ADXL345 DEVID 0xe5')
        for register, value in ((0x2D, 0x00), (0x31, 0x08), (0x2C, 0x0A), (0x2D, 0x08)):
            i2c.writeto_mem(address, register, bytes((value,)))

    @staticmethod
    def _axis(lo, hi):
        value = lo | hi << 8
        return (value - 65536 if value & 32768 else value) * 0.00390625

    def read_g(self):
        data = self.i2c.readfrom_mem(self.address, 0x32, 6)
        return tuple(self._axis(data[i], data[i + 1]) for i in (0, 2, 4))


class SensorHub:
    def __init__(self, cfg):
        from machine import ADC
        if not cfg.AUDIO_ENABLED or cfg.MODE != 'audio':
            raise ValueError('Diagnostic mode requires an audio ADC')
        attn = getattr(ADC, 'ATTN_' + cfg.ADC_ATTENUATION)
        self.adc = ADC(0)
        self.audio = self.adc.channel(pin=cfg.AUDIO_PIN, attn=attn)
        self.accel = None
        if getattr(cfg, 'ACCEL_ENABLED', False):
            from machine import I2C
            i2c = I2C(0, I2C.MASTER, baudrate=100000, pins=(cfg.ACCEL_SDA_PIN, cfg.ACCEL_SCL_PIN))
            self.accel = ADXL345(i2c, cfg.ACCEL_I2C_ADDRESS)

    def read_audio(self):
        return self.audio() / 4095.0
