"""Lightweight REPL compatibility probe for Pycom LoPy 1.0 (1.20.2.r6 / v1.11).

Run manually on LoPy REPL (paste or import) to verify every language feature,
array typecode, buffer operation, math function, and built-in relied upon by
the standalone Burst MLP and CNN v4.6 detection implementations—without loading
any trained model or allocating large buffers.

Usage on LoPy REPL:
    import lopy_compat_probe
    lopy_compat_probe.run()
"""

from array import array
import gc
import math
import os
import sys


def run():
    gc.collect()
    h0 = gc.mem_free() if hasattr(gc, 'mem_free') else -1
    print('UNAME:', os.uname() if hasattr(os, 'uname') else sys.platform)
    print('IMPL:', sys.implementation)
    print('HEAP_START:', h0)

    def _zeros(tc, size):
        arr = array(tc, range(size))
        z = 0.0 if tc == 'f' else 0
        for idx in range(size):
            arr[idx] = z
        return arr

    # 1. Verify array*int status (expected TypeError on Pycom MicroPython v1.11)
    try:
        _ = array('h', [0]) * 4
        print('CHECK array*int: SUPPORTED')
    except TypeError:
        print('CHECK array*int: UNSUPPORTED (expected on Pycom v1.11)')

    # 2. Verify range-backed array allocation for 'h', 'H', 'f'
    ah = _zeros('h', 64)
    aH = _zeros('H', 64)
    af = _zeros('f', 64)
    ah[0] = -32768
    ah[63] = 32752
    aH[63] = 1023
    af[0] = -6.0
    af[63] = 6.0
    assert len(ah) == 64 and ah[0] == -32768 and ah[63] == 32752
    assert len(aH) == 64 and aH[63] == 1023
    assert len(af) == 64 and abs(af[63] - 6.0) < 1e-5
    print('CHECK array(tc, range(n)) h/H/f: OK')

    # 3. Verify bytearray uint16 LE 12-bit ADC decode + signed PCM16 shift
    ba = bytearray(16)
    vals = (0, 1, 2048, 4095, 5000, 1024, 3072, 2047)
    for i in range(8):
        ba[2 * i] = vals[i] & 0xFF
        ba[2 * i + 1] = (vals[i] >> 8) & 0xFF
    decoded = []
    for i in range(8):
        raw = ba[2 * i] | (ba[2 * i + 1] << 8)
        if raw > 4095:
            raw = 4095
        decoded.append((raw << 4) - 32768)
    assert decoded[0] == -32768 and decoded[2] == 0 and decoded[3] == 32752 and decoded[4] == 32752
    print('CHECK bytearray LE ADC decode: OK')

    # 4. Verify raw bytes literal indexing + int8 sign conversion
    wb_lit = (
        b'\x00\x7f\x80\xff'
        b'\x01\xfe'
    )
    signed_vals = [b if b < 128 else b - 256 for b in wb_lit]
    assert signed_vals == [0, 127, -128, -1, 1, -2]
    print('CHECK bytes literal int8 decode: OK')

    # 5. Verify math functions and float32 exp clamping (-40..40)
    c = math.cos(2.0 * math.pi / 16.0)
    s = -math.sin(2.0 * math.pi / 16.0)
    sq = math.sqrt(2.0)
    lg = math.log(1.0 + 1e-6)
    sig_lo = 1.0 / (1.0 + math.exp(30.0))
    sig_hi = 1.0 / (1.0 + math.exp(-30.0))
    sig_40 = 1.0 / (1.0 + math.exp(40.0))
    assert c > 0.9 and s < -0.3 and sq > 1.4 and lg > 0.0
    assert sig_lo < 1e-10 and sig_hi > 0.9999 and sig_40 >= 0.0
    print('CHECK math cos/sin/sqrt/log/exp: OK')

    # 6. Verify built-ins: int(round(x)), max, min, sum, tuple([...]), swap
    r_val = int(round(87.6))
    assert isinstance(r_val, int) and r_val == 88
    t_bins = tuple([(hz * 512 + 3999) // 4000 for hz in (30, 65, 1900)])
    assert len(t_bins) == 3 and sum([1.5, 2.5]) == 4.0
    a1, a2 = _zeros('f', 4), _zeros('f', 4)
    a1[0] = 1.0
    a1, a2 = a2, a1
    assert a2[0] == 1.0 and a1[0] == 0.0
    print('CHECK builtins & reference swap: OK')

    # 7. Tiny 16-pt radix-2 FFT sanity check
    re = _zeros('f', 16)
    im = _zeros('f', 16)
    cos_t = _zeros('f', 8)
    sin_t = _zeros('f', 8)
    rev = _zeros('H', 16)
    for k in range(8):
        ang = 2.0 * math.pi * k / 16.0
        cos_t[k] = math.cos(ang)
        sin_t[k] = -math.sin(ang)
    for i in range(1, 16):
        rev[i] = (rev[i >> 1] >> 1) | ((i & 1) * 8)
    for i in range(16):
        re[rev[i]] = math.cos(2.0 * math.pi * 2.0 * i / 16.0)
    w = 2
    while w <= 16:
        half = w // 2
        stride = 16 // w
        for start in range(0, 16, w):
            for k in range(half):
                i = start + k
                j = i + half
                tw = k * stride
                r = cos_t[tw] * re[j] - sin_t[tw] * im[j]
                q = sin_t[tw] * re[j] + cos_t[tw] * im[j]
                re[j] = re[i] - r
                im[j] = im[i] - q
                re[i] += r
                im[i] += q
        w *= 2
    p2 = re[2] * re[2] + im[2] * im[2]
    assert p2 > 60.0  # Expect 8^2 = 64.0
    print('CHECK 16-pt in-place FFT: OK (bin2=%.2f)' % p2)

    gc.collect()
    h1 = gc.mem_free() if hasattr(gc, 'mem_free') else -1
    print('HEAP_END:', h1)
    print('=== ALL COMPATIBILITY CHECKS PASSED ===')


if __name__ == '__main__':
    run()
