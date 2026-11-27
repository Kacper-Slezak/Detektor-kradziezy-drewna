"""Build deploy/v2/main.py: Kiryl's standalone burst firmware with the v2 detector.

Takes deploy/burst/main.py (Wi-Fi, frames, sleep, ADC capture stay unchanged), replaces
`analizuj_sygnaly` with the v2 detector (tg_v2_device.py inlined + model_v2.json), and
replaces `main()` with a version that confirms a suspicious session with a second one
after a short timer sleep.

    python build_main.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / 'deploy' / 'burst' / 'main.py'
OUT = HERE.parent / 'deploy' / 'v2' / 'main.py'

ANALYSE = '''

V2_T_HIGH = {t_high!r}
V2_T_SUSP = {t_susp!r}
V2_CONFIRM_SLEEP_MS = 120000   # 2nd look after 2 min: a machine loading timber is still there
V2_NVS_KEY = "v2_conf"
V2_MODELS = {models}
V2_OSTATNI = [0.0, False]       # last session: mean logit, suspicious


def _v2_sig(x):
    x = -30.0 if x < -30.0 else (30.0 if x > 30.0 else x)
    return 1.0 / (1.0 + math.exp(-x))


def analizuj_sygnaly(mic_aktywny, vib_aktywny, prog=None):
    """Record one session (nagraj_audio) and score it.
    Returns (czy_alarm, event_type, confidence); V2_OSTATNI holds the logit and whether
    the session is suspicious enough to be confirmed by a second one."""
    st = V2State()
    n = 0
    for blk in nagraj_audio():
        if len(blk) != 8000:
            raise ValueError("blk")
        st.add_block(blk)
        n += 1
    if n < 2:
        raise RuntimeError("No audio")
    vec = st.session_vector()
    st = None
    gc.collect()
    lg = 0.0
    for m in V2_MODELS:
        lg += score(vec, m)
    lg /= len(V2_MODELS)
    susp = lg >= V2_T_SUSP
    V2_OSTATNI[0] = lg
    V2_OSTATNI[1] = susp
    hi = V2_T_HIGH if prog is None else prog
    czy = lg >= hi or (vib_aktywny and susp)
    conf = int(round(100.0 * _v2_sig(lg)))
    if vib_aktywny and czy:
        conf += 10
    conf = max(0, min(100, conf))
    return czy, (1 if czy else 0), conf


def v2_bench(n_blokow=10):
    """REPL: import main; main.v2_bench()  -> ms per 1 s block and free heap, no Wi-Fi."""
    gc.collect()
    print("V2_HEAP_START", gc.mem_free() if hasattr(gc, "mem_free") else -1)
    st = V2State()
    blk = bytearray(8000)
    x = 12345
    for i in range(4000):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        v = 2048 + int(300.0 * math.sin(2.0 * math.pi * 45.0 * i / 4000.0)) + (x % 61) - 30
        blk[2 * i] = v & 0xFF
        blk[2 * i + 1] = (v >> 8) & 0xFF
    gc.collect()
    print("V2_HEAP_STATE", gc.mem_free() if hasattr(gc, "mem_free") else -1)
    for b in range(n_blokow):
        t0 = time.ticks_ms()
        st.add_block(blk)
        print("V2_BLOCK_MS", b, time.ticks_diff(time.ticks_ms(), t0))
    t0 = time.ticks_ms()
    vec = st.session_vector()
    lg = 0.0
    for m in V2_MODELS:
        lg += score(vec, m)
    print("V2_SCORE_MS", time.ticks_diff(time.ticks_ms(), t0), "logit", lg / len(V2_MODELS))
    gc.collect()
    print("V2_HEAP_END", gc.mem_free() if hasattr(gc, "mem_free") else -1)

'''

MAIN = '''def _v2_nvs_get(k):
    try:
        v = pycom.nvs_get(k)
        return 0 if v is None else v
    except (ValueError, OSError):
        return 0


def _v2_nvs_set(k, v):
    try:
        pycom.nvs_set(k, v)
    except Exception:
        pass


def _v2_alarm(conf, vib):
    sb = 1 | (2 if vib else 0)
    gc.collect()
    try:
        polacz_wifi()
        wyslij_payload(przygotuj_ramke_alarm(1, conf, 100, sb))
    except Exception as e:
        print("Alarm err:", e)


def main():
    wi = machine.wake_reason()
    pw = wi[0] if wi else -1
    if pw == machine.RTC_WAKE and _v2_nvs_get(V2_NVS_KEY):
        # second look at a suspicious session
        prev = _v2_nvs_get(V2_NVS_KEY)
        _v2_nvs_set(V2_NVS_KEY, 0)
        vib = (prev & 2) != 0 or (pin_vib is not None and pin_vib.value() == 1)
        print("Wake: RTC confirm")
        try:
            czy, et, conf = analizuj_sygnaly(True, vib, prog=V2_T_SUSP)
            print("Confirm result: alarm/conf/logit", czy, conf, V2_OSTATNI[0])
            if czy:
                _v2_alarm(conf, vib)
                idz_spac_na_sztywno(CZAS_SNU_SZTYWNEGO_MS)
                return
        except Exception as e:
            print("Det err:", e)
        idz_spac_na_czujniki()
    elif pw == machine.RTC_WAKE:
        print("Wake: RTC")
        gc.collect()
        try:
            polacz_wifi()
            wyslij_payload(przygotuj_ramke_heartbeat(100, 0, 0))
        except Exception as e:
            print("HB err:", e)
        idz_spac_na_czujniki()
    elif pw == machine.PIN_WAKE:
        print("Wake: GPIO", wi)
        pl = wi[1] if len(wi) > 1 and wi[1] else ()
        ids = [(p.id() if hasattr(p, "id") else str(p)) for p in pl]
        mic = (pin_mic is not None and pin_mic.value() == 1) or (PIN_MIKROFON_ID in ids)
        vib = (pin_vib is not None and pin_vib.value() == 1) or (PIN_DRGANIA_ID in ids)
        czy = False
        conf = 0
        try:
            print("Detection start: mic/vib", mic, vib)
            czy, et, conf = analizuj_sygnaly(mic, vib)
            print("Detection result: alarm/conf/logit/susp", czy, conf, V2_OSTATNI[0], V2_OSTATNI[1])
        except Exception as e:
            print("Det err:", e)
        gc.collect()
        if czy:
            _v2_alarm(conf, vib)
            idz_spac_na_sztywno(CZAS_SNU_SZTYWNEGO_MS)
        elif V2_OSTATNI[1]:
            _v2_nvs_set(V2_NVS_KEY, 1 | (2 if vib else 0))
            idz_spac_na_sztywno(V2_CONFIRM_SLEEP_MS)
        else:
            idz_spac_na_czujniki()
    else:
        print("Boot: wake reason", pw)
        _v2_nvs_set(V2_NVS_KEY, 0)
        ramka = przygotuj_ramke_boot(_nvs_inc("boot_id", True), FIRMWARE_VER, 1, 100)
        gc.collect()
        try:
            polacz_wifi()
            wyslij_payload(ramka)
        except Exception as e:
            print("Boot err:", e)
        idz_spac_na_czujniki()


'''


def device_code():
    src = (HERE / 'tg_v2_device.py').read_text()
    lines = []
    for ln in src.splitlines():
        if ln.startswith('import math') or ln.startswith('from array import array'):
            continue
        lines.append(ln)
    return 'import math\nfrom array import array\n' + strip_comments('\n'.join(lines))


def fmt_model(m):
    def tup(v):
        return '(' + ', '.join('%.6g' % x for x in v) + ',)'

    def i8(v):
        return repr(bytes((x + 256) % 256 for x in v))
    return ('dict(MU=%s, SD=%s, W1=%s, S1=%.6g, B1=%s, W2=%s, S2=%.6g, B2=%.6g)'
            % (tup(m['MU']), tup(m['SD']), i8(m['W1']), m['S1'], tup(m['B1']), i8(m['W2']),
               m['S2'], m['B2']))


def strip_comments(src):
    """Drop comment-only lines, docstrings and blank lines (smaller source on the LoPy)."""
    import ast
    tree = ast.parse(src)
    doc_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, 'value', None), ast.Constant) \
                    and isinstance(first.value.value, str):
                doc_lines.update(range(first.lineno, first.end_lineno + 1))
    out = []
    for i, ln in enumerate(src.splitlines(), 1):
        if i in doc_lines or not ln.strip() or ln.strip().startswith('#'):
            continue
        out.append(ln)
    return '\n'.join(out) + '\n'


def build():
    base = SRC.read_text()
    a = base.index('def analizuj_sygnaly')
    b = base.index('def _nvs_inc')
    c = base.index('def main():')
    d = base.index('if __name__ == "__main__":')
    model = json.loads((HERE / 'model_v2.json').read_text())
    models = '(\n    ' + ',\n    '.join(fmt_model(m) for m in model['models']) + ',\n)'
    out = (base[:a] + device_code()
           + ANALYSE.format(t_high=round(model['T_HIGH'], 4), t_susp=round(model['T_SUSP'], 4),
                            models=models)
           + '\n' + base[b:c] + MAIN + base[d:])
    out = out.replace('FIRMWARE_VER = 1', 'FIRMWARE_VER = 2')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(out)
    compile(out, str(OUT), 'exec')
    import io
    import tokenize
    toks = tokenize.generate_tokens(io.StringIO(out).readline)
    assert not any(t.type == getattr(tokenize, 'FSTRING_START', -1) for t in toks), 'f-string'
    print('wrote', OUT, len(out.encode()), 'bytes')


if __name__ == '__main__':
    build()
