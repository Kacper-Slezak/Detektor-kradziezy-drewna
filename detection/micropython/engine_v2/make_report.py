"""Generate RAPORT_v2.html: the full validation report (Polish) with inline SVG figures.

Every number in the report is computed here from the caches, so re-running the pipeline in
README.md and then this script reproduces the report.

    TG_TAG=v4 python make_report.py
"""

import hashlib
import html
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

import cache
import devsim
import metrics

TAG = os.environ.get('TG_TAG', 'v4')
HERE = Path(__file__).resolve().parent
OUT = HERE / 'RAPORT_v2.html'
NOMINAL = '120.0'


def sha256(p, limit=None):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def pct(k, n):
    return 100.0 * k / n if n else float('nan')


def cell(alarm, mask):
    k, n, lo, hi = metrics.rate(alarm, mask)
    if n == 0:
        return '<td class="num">–</td>'
    return ('<td class="num"><b>%.1f%%</b><span class="ci"> %d/%d · %.1f–%.1f</span></td>'
            % (pct(k, n), k, n, 100 * lo, 100 * hi))


# ----------------------------------------------------------------------------- SVG helpers

def svg_bars(rows, title, unit='%', vmax=100.0, width=720):
    """rows: list of (label, [(series_name, value, css_class), ...])"""
    bh = 14
    gap = 10
    lw = 230
    pw = width - lw - 60
    nser = len(rows[0][1]) if rows else 1
    h = len(rows) * (nser * bh + gap) + 40
    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, h, html.escape(title))]
    for t in range(0, 101, 25):
        x = lw + pw * t / 100.0
        out.append('<line class="grid" x1="%.1f" y1="20" x2="%.1f" y2="%d"/>' % (x, x, h - 10))
        out.append('<text class="axis" x="%.1f" y="14" text-anchor="middle">%d%s</text>'
                   % (x, vmax * t / 100, unit))
    y = 26
    for label, ser in rows:
        out.append('<text class="lab" x="%d" y="%.1f" text-anchor="end">%s</text>'
                   % (lw - 8, y + nser * bh / 2 + 4, html.escape(label)))
        for name, v, cls in ser:
            w = 0 if not np.isfinite(v) else pw * min(v, vmax) / vmax
            out.append('<rect class="%s" x="%d" y="%.1f" width="%.1f" height="%d" rx="2"/>'
                       % (cls, lw, y, w, bh - 3))
            out.append('<text class="val" x="%.1f" y="%.1f">%s %.1f%s</text>'
                       % (lw + w + 4, y + bh - 5, html.escape(name), v, unit))
            y += bh
        y += gap
    out.append('</svg>')
    return '\n'.join(out)


def roc(scores, labels):
    s = np.asarray(scores, float)
    y = np.asarray(labels, bool)
    order = np.argsort(-s)
    tp = np.cumsum(y[order]) / max(1, y.sum())
    fp = np.cumsum(~y[order]) / max(1, (~y).sum())
    return np.concatenate([[0], fp]), np.concatenate([[0], tp])


def svg_roc(curves, title, width=420, xmax=0.2):
    pad = 46
    W = width - pad - 14
    H = 300
    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, H + pad + 10, html.escape(title))]
    for t in np.linspace(0, 1, 6):
        y = 10 + H * (1 - t)
        out.append('<line class="grid" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (pad, y, pad + W, y))
        out.append('<text class="axis" x="%d" y="%.1f" text-anchor="end">%d%%</text>' % (pad - 6, y + 4, 100 * t))
    for t in np.linspace(0, xmax, 5):
        x = pad + W * t / xmax
        out.append('<line class="grid" x1="%.1f" y1="10" x2="%.1f" y2="%d"/>' % (x, x, 10 + H))
        out.append('<text class="axis" x="%.1f" y="%d" text-anchor="middle">%.0f%%</text>' % (x, 26 + H, 100 * t))
    out.append('<text class="axis" x="%d" y="%d" text-anchor="middle">fałszywe alarmy (las, pogoda, przeloty)</text>'
               % (pad + W / 2, H + 44))
    for name, fpr, tpr, cls in curves:
        m = fpr <= xmax
        pts = ' '.join('%.1f,%.1f' % (pad + W * a / xmax, 10 + H * (1 - b)) for a, b in zip(fpr[m], tpr[m]))
        out.append('<polyline class="%s line" points="%s"/>' % (cls, pts))
    ly = 24
    for name, _, _, cls in curves:
        out.append('<rect class="%s" x="%d" y="%d" width="12" height="4"/>' % (cls, pad + 12, ly))
        out.append('<text class="lab" x="%d" y="%d">%s</text>' % (pad + 30, ly + 6, html.escape(name)))
        ly += 18
    out.append('</svg>')
    return '\n'.join(out)


# ----------------------------------------------------------------------------- sequences

def run_seq(seq, th, ts):
    i = 0
    while i < len(seq):
        if seq[i] >= th:
            return i + 1
        if seq[i] >= ts and i + 1 < len(seq):
            if seq[i + 1] >= ts:
                return i + 2
            i += 2
        else:
            i += 1
    return None


def seq_table(dec, burst, M, th, ts):
    groups = {}
    for i in range(len(dec)):
        if M['level'][i] != NOMINAL:
            continue
        groups.setdefault((M['group'][i], M['kind'][i], M['src'][i], M['bg'][i], M['snr'][i]), []).append(i)
    res = {}
    for (g, k, s, bg, snr), idx in groups.items():
        if len(idx) < 4:
            continue
        idx = sorted(idx, key=lambda i: float(M['start'][i]))
        key = (k, s, snr if k == 'engine_mix' else '')
        r = run_seq(dec[idx], th, ts)
        b = bool(burst[idx].any())
        res.setdefault(key, []).append((r, b, len(idx)))
    return res


# ----------------------------------------------------------------------------- main

def main():
    S, M = cache.load(TAG)
    del S
    dec = np.load(devsim.DATA / 'cache' / ('dec_ens8_%s.npy' % TAG))
    rb = np.load(devsim.DATA / 'cache' / ('res_burst_%s.npy' % TAG))
    burst = rb[:, 0] == 1
    bconf = rb[:, 1].astype(float)
    model = json.loads((HERE / 'model_v2.json').read_text())
    th, ts = model['T_HIGH'], model['T_SUSP']
    kind, src, lev, cls, snr = M['kind'], M['src'], M['level'], M['cls'], M['snr']
    nom = lev == NOMINAL
    y = M['label'] == '1'
    susp = dec >= ts
    high = dec >= th
    cv = (src == 'esc50') | (src == 'soc2')

    G = [
        ('Silnik: ESC-50 "engine" (CV)', (kind == 'engine') & (src == 'esc50')),
        ('Silnik: maszyny soc2, 32 nagrania (CV)', (kind == 'engine') & (src == 'soc2')),
        ('Silnik: zewnętrzne (traktory, ciężarówki)', (kind == 'engine') & ((src == 'soc') | (src == 'sample'))),
        ('Silnik: FSD50K, niezależny korpus', (kind == 'engine') & (src == 'fsd')),
        ('Silnik + pogoda 0 dB (CV)', (kind == 'engine_mix') & cv & (snr == '0.0')),
        ('Silnik + pogoda +6 dB (CV)', (kind == 'engine_mix') & cv & (snr == '6.0')),
        ('Silnik + burza/deszcz/wiatr +3 dB (CV)', (kind == 'engine_mix') & cv & (snr == '3.0')),
        ('Silnik + burza/deszcz/wiatr −3 dB (CV)', (kind == 'engine_mix') & cv & (snr == '-3.0')),
        ('Silnik + pogoda, FSD50K', (kind == 'engine_mix') & (src == 'fsd')),
        ('FP: przyroda i pogoda ESC-50 (CV)', (kind == 'forest') & (src == 'esc50')),
        ('FP: przyroda i pogoda FSD50K', (kind == 'forest') & (src == 'fsd')),
        ('FP: nagranie lasu (z odległym szumem drogi)', (kind == 'forest') & (src == 'sample')),
        ('FP: przelot śmigłowca/samolotu/pociągu ESC-50', (kind == 'mech') & (src == 'esc50')),
        ('FP: przeloty FSD50K', (kind == 'mech') & (src == 'fsd')),
    ]
    g_rows = []
    for name, m in G:
        m = m & nom
        if not m.any():
            continue
        g_rows.append('<tr><th>%s</th>%s%s%s</tr>' % (html.escape(name), cell(susp, m), cell(high, m), cell(burst, m)))

    # per weather class (ESC-50 + FSD50K), nominal level
    WX = [('Burza', ['thunderstorm'], ['fsd_Thunderstorm', 'fsd_Thunder']),
          ('Deszcz', ['rain'], ['fsd_Rain', 'fsd_Raindrop']),
          ('Wiatr', ['wind'], ['fsd_Wind']),
          ('Fale, strumień', ['sea_waves'], ['fsd_Waves_and_surf', 'fsd_Ocean', 'fsd_Stream']),
          ('Ogień (trzaski)', ['crackling_fire'], ['fsd_Fire', 'fsd_Crackle']),
          ('Krople wody', ['water_drops'], ['fsd_Water']),
          ('Świerszcze', ['crickets'], ['fsd_Cricket']),
          ('Owady', ['insects'], ['fsd_Insect']),
          ('Ptaki', ['chirping_birds', 'crow'], ['fsd_Bird', 'fsd_Crow']),
          ('Żaby', ['frog'], ['fsd_Frog']),
          ('Kroki, liście', ['footsteps'], ['fsd_Walk_and_footsteps', 'fsd_Rustling_leaves']),
          ('Stukanie w drewno', ['door_wood_knock'], ['fsd_Knock', 'fsd_Wood', 'fsd_Chop']),
          ('Śmigłowiec', ['helicopter'], ['fsd_Helicopter']),
          ('Samolot', ['airplane'], ['fsd_Fixed-wing_aircraft_and_airplane', 'fsd_Aircraft']),
          ('Pociąg', ['train'], ['fsd_Train', 'fsd_Rail_transport']),
          ('Przejazd auta', [], ['fsd_Car_passing_by'])]
    wx_rows = []
    wx_chart = []
    for name, ec, fc in WX:
        me = np.isin(cls, ec) & (src == 'esc50') & nom
        mf = np.isin(cls, fc) & (src == 'fsd') & nom
        wx_rows.append('<tr><th>%s</th>%s%s%s%s%s%s</tr>' % (
            name, cell(susp, me), cell(high, me), cell(burst, me),
            cell(susp, mf), cell(high, mf), cell(burst, mf)))
        m = me | mf
        if m.any():
            wx_chart.append((name, [('v2 podejrzenie', pct(susp[m].sum(), m.sum()), 'c2'),
                                    ('v2 alarm od razu', pct(high[m].sum(), m.sum()), 'c1'),
                                    ('burst alarm', pct(burst[m].sum(), m.sum()), 'c3')]))

    # level invariance
    lv_rows = []
    for name, m in G[:2] + G[9:10]:
        lv_rows.append('<tr><th>%s</th>%s</tr>' % (html.escape(name), ''.join(
            cell(susp, m & (lev == l)) + cell(burst, m & (lev == l)) for l in ('40.0', '120.0', '360.0'))))

    # product-level sequences
    seqs = seq_table(dec, burst, M, th, ts)
    SEQN = [(('engine', 'soc2', ''), 'Maszyny soc2 (CV)'), (('engine', 'soc', ''), 'Maszyny zewnętrzne'),
            (('engine_mix', 'soc2', '0.0'), 'Maszyny soc2 + pogoda 0 dB'),
            (('engine_mix', 'soc2', '6.0'), 'Maszyny soc2 + pogoda +6 dB'),
            (('engine_mix', 'soc2', '-3.0'), 'Maszyny soc2 + burza/deszcz/wiatr −3 dB'),
            (('engine_mix', 'soc2', '3.0'), 'Maszyny soc2 + burza/deszcz/wiatr +3 dB'),
            (('forest', 'sample', ''), 'Nagranie lasu 288 s'), (('forest', 'soc2', ''), 'Las Valla 109 s'),
            (('forest', 'fsd', ''), 'Przyroda/pogoda FSD50K (klipy ≥20 s)'),
            (('mech', 'fsd', ''), 'Przeloty FSD50K')]
    seq_rows = []
    for key, name in SEQN:
        v = seqs.get(key, [])
        if not v:
            continue
        a = [r for r, b, n in v if r is not None]
        bb = sum(1 for r, b, n in v if b)
        lo, hi = metrics.wilson(len(a), len(v))
        seq_rows.append('<tr><th>%s</th><td class="num">%d</td><td class="num">%d</td>'
                        '<td class="num"><b>%.0f%%</b><span class="ci"> %d/%d · %.0f–%.0f</span></td>'
                        '<td class="num">%s</td><td class="num">%.0f%%</td></tr>'
                        % (name, len(v), sum(n for r, b, n in v), pct(len(a), len(v)), len(a), len(v),
                           100 * lo, 100 * hi, ('%.1f' % np.median(a)) if a else '–', pct(bb, len(v))))

    # ROC on CV + FSD at nominal level
    rm = (cv | (src == 'fsd')) & nom & ((kind == 'engine') | (kind == 'forest') | (kind == 'mech'))
    f2, t2 = roc(dec[rm], y[rm])
    fb, tb = roc(bconf[rm], y[rm])
    auc2 = metrics.auc(dec[rm], y[rm])
    aucb = metrics.auc(bconf[rm], y[rm])
    roc_svg = svg_roc([('v2 (AUC %.3f)' % auc2, f2, t2, 'c1'), ('burst (AUC %.3f)' % aucb, fb, tb, 'c3')],
                      'ROC: silnik vs las, pogoda, przeloty')
    fm = (src == 'fsd') & nom & ((kind == 'engine') | (kind == 'forest') | (kind == 'mech'))
    auc_f2 = metrics.auc(dec[fm], y[fm]) if fm.any() else float('nan')
    auc_fb = metrics.auc(bconf[fm], y[fm]) if fm.any() else float('nan')

    snr_chart = []
    for name, m in [('czysty silnik', (kind == 'engine') & cv), ('+6 dB pogoda', (kind == 'engine_mix') & cv & (snr == '6.0')),
                    ('+3 dB burza/deszcz/wiatr', (kind == 'engine_mix') & cv & (snr == '3.0')),
                    ('0 dB pogoda', (kind == 'engine_mix') & cv & (snr == '0.0')),
                    ('−3 dB burza/deszcz/wiatr', (kind == 'engine_mix') & cv & (snr == '-3.0'))]:
        m = m & nom
        snr_chart.append((name, [('v2 podejrzenie', pct(susp[m].sum(), m.sum()), 'c2'),
                                 ('burst alarm', pct(burst[m].sum(), m.sum()), 'c3')]))

    # data inventory
    counts = {}
    for i in np.where(nom)[0]:
        counts[(src[i], kind[i])] = counts.get((src[i], kind[i]), 0) + 1
    inv = ''.join('<tr><td>%s</td><td>%s</td><td class="num">%d</td></tr>' % (s, k, n)
                  for (s, k), n in sorted(counts.items()))
    soc2_rows = []
    man = devsim.DATA / 'soc2' / 'manifest.csv'
    for line in open(man):
        p = line.strip().split(',')
        if len(p) >= 3 and p[0] in ('pos', 'neg'):
            f = devsim.DATA / 'soc2' / (p[1] + '.wav')
            soc2_rows.append('<tr><td>%s</td><td>%s</td><td><code>%s</code></td><td><code>%s</code></td></tr>'
                             % (html.escape(p[1]), 'silnik' if p[0] == 'pos' else 'las', html.escape(p[2]), sha256(f)[:16]))
    arch = []
    for p, desc, url in [
            (devsim.DATA / 'esc50' / 'esc50.zip', 'ESC-50 (Piczak 2015), CC BY-NC 3.0', 'https://github.com/karoldvl/ESC-50/archive/master.zip'),
            (devsim.DATA / 'ice' / 'diesel.zip', 'Sounds of Vehicle ICE, diesel (Zenodo 18777405), CC BY 4.0', 'https://zenodo.org/api/records/18777405/files/Diesel%20Motor%20Sounds.zip/content'),
            (devsim.DATA / 'ice' / 'petrol.zip', 'Sounds of Vehicle ICE, petrol (Zenodo 18777405), CC BY 4.0', 'https://zenodo.org/api/records/18777405/files/Petrol%20Motor%20Sounds.zip/content'),
            (devsim.DATA / 'fsd50k' / 'eval.z01', 'FSD50K eval audio cz. 1 (Zenodo 4060432), licencje CC per klip', 'https://zenodo.org/api/records/4060432/files/FSD50K.eval_audio.z01/content'),
            (devsim.DATA / 'fsd50k' / 'eval.zip', 'FSD50K eval audio cz. 2', 'https://zenodo.org/api/records/4060432/files/FSD50K.eval_audio.zip/content'),
            (devsim.DATA / 'fsd50k' / 'gt.zip', 'FSD50K ground truth', 'https://zenodo.org/api/records/4060432/files/FSD50K.ground_truth.zip/content')]:
        if p.exists():
            arch.append('<tr><td>%s</td><td><code>%s</code></td><td><code>%s</code></td></tr>'
                        % (desc, html.escape(url), sha256(p)))

    tests = subprocess.run([sys.executable, '-m', 'unittest', 'test_v2_device'], cwd=HERE,
                           capture_output=True, text=True)
    tlines = [ln for ln in tests.stderr.splitlines() if ln.startswith(('Ran', 'OK', 'FAILED'))]
    main_py = HERE.parent / 'deploy' / 'v2' / 'main.py'
    git = subprocess.run(['git', 'log', '--oneline', '-12'], cwd=HERE, capture_output=True, text=True).stdout

    tpl = (HERE / 'report_template.html').read_text()
    rep = {
        '{{TAG}}': TAG, '{{T_HIGH}}': '%.2f' % th, '{{T_SUSP}}': '%.2f' % ts,
        '{{G_ROWS}}': '\n'.join(g_rows), '{{WX_ROWS}}': '\n'.join(wx_rows),
        '{{WX_CHART}}': svg_bars(wx_chart, 'Fałszywe alarmy według klasy pogody'),
        '{{SNR_CHART}}': svg_bars(snr_chart, 'Wykrycie silnika w złej pogodzie'),
        '{{LV_ROWS}}': '\n'.join(lv_rows), '{{SEQ_ROWS}}': '\n'.join(seq_rows),
        '{{ROC}}': roc_svg, '{{AUC_V2}}': '%.3f' % auc2, '{{AUC_B}}': '%.3f' % aucb,
        '{{AUC_F2}}': '%.3f' % auc_f2, '{{AUC_FB}}': '%.3f' % auc_fb,
        '{{INV}}': inv, '{{SOC2}}': '\n'.join(soc2_rows), '{{ARCH}}': '\n'.join(arch),
        '{{TESTS}}': html.escape(' · '.join(tlines)), '{{MAIN_SIZE}}': '%d' % main_py.stat().st_size,
        '{{MAIN_SHA}}': sha256(main_py), '{{GIT}}': html.escape(git),
        '{{NSESS}}': '%d' % len(dec),
    }
    for k, v in rep.items():
        tpl = tpl.replace(k, v)
    OUT.write_text(tpl)
    print('wrote', OUT, len(tpl), 'bytes')


if __name__ == '__main__':
    main()
