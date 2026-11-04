"""Pycom LoPy-specific hardware drivers, not generic machine ADC/I2C APIs."""


class ADXL345:
    """External ADXL345 on I2C, 100 Hz, full-res +/-2g; values in g."""
    def __init__(self, i2c, address=0x53):
        self.i2c = i2c
        self.addr = address
        who = i2c.readfrom_mem(address, 0x00, 1)[0]
        if who != 0xE5:
            raise OSError('ADXL345 wrong DEVID, expected 0xE5: %s' % hex(who))
        i2c.writeto_mem(address, 0x2D, bytes((0x00,)))
        i2c.writeto_mem(address, 0x31, bytes((0x08,)))
        i2c.writeto_mem(address, 0x2C, bytes((0x0A,)))
        i2c.writeto_mem(address, 0x2D, bytes((0x08,)))

    @staticmethod
    def _i16(a, b):
        n = a | (b << 8)
        return n - 65536 if n & 0x8000 else n

    def read_g(self):
        buf = self.i2c.readfrom_mem(self.addr, 0x32, 6)
        return (self._i16(buf[0], buf[1]) * 0.00390625,
                self._i16(buf[2], buf[3]) * 0.00390625,
                self._i16(buf[4], buf[5]) * 0.00390625)


class SensorHub:
    def __init__(self, cfg):
        from machine import ADC, I2C, Pin
        self.cfg = cfg
        self.audio = None
        self.vibration_analog = None
        self.vibration_digital = None
        self.accel = None
        self.alarm_pin = None
        self.adc = None
        attn_name = 'ATTN_' + cfg.ADC_ATTENUATION
        attn = getattr(ADC, attn_name)
        if cfg.AUDIO_ENABLED or cfg.VIBRATION_INPUT == 'analog':
            self.adc = ADC(0)
        if cfg.AUDIO_ENABLED:
            self.audio = self.adc.channel(pin=cfg.AUDIO_PIN, attn=attn)
        if cfg.VIBRATION_INPUT == 'analog':
            self.vibration_analog = self.adc.channel(pin=cfg.VIBRATION_PIN, attn=attn)
        elif cfg.VIBRATION_INPUT == 'digital':
            self.vibration_digital = Pin(cfg.VIBRATION_PIN, mode=Pin.IN)
        elif cfg.VIBRATION_INPUT != 'off':
            raise ValueError('Invalid VIBRATION_INPUT')
        if cfg.ACCEL_ENABLED:
            i2c = I2C(0, I2C.MASTER, baudrate=100000,
                      pins=(cfg.ACCEL_SDA_PIN, cfg.ACCEL_SCL_PIN))
            self.accel = ADXL345(i2c, cfg.ACCEL_I2C_ADDRESS)
        if cfg.ALARM_OUTPUT_PIN:
            self.alarm_pin = Pin(cfg.ALARM_OUTPUT_PIN, mode=Pin.OUT)
            self.alarm_pin(0)

    def read_audio(self):
        # Pycom ADCChannel objects are callable; 12-bit 0..4095.
        return self.audio() / 4095.0

    def read_vibration(self):
        if self.vibration_analog is not None:
            return self.vibration_analog() / 4095.0
        if self.vibration_digital is not None:
            return float(self.vibration_digital() == self.cfg.VIBRATION_ACTIVE_LEVEL)
        return None

    def pulse_alarm(self):
        if self.alarm_pin:
            import time
            self.alarm_pin(1)
            time.sleep_ms(self.cfg.ALARM_PULSE_MS)
            self.alarm_pin(0)
