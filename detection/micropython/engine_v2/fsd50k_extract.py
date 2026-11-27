"""Extract the engine / weather / nature clips of the FSD50K eval set (Fonseca et al. 2022,
IEEE/ACM TASLP 30; Zenodo 4060432) from the split archive FSD50K.eval_audio.{z01,zip}.

No `zip`/`7z` here, so the two parts are read as one byte stream with Python's zipfile and
every member's header offset is corrected by the start of the disk it lives on.

    python fsd50k_extract.py            # reads $TG_DATA/fsd50k/{eval.z01,eval.zip,gt.zip}
Writes $TG_DATA/fsd50k/audio/<fname>.wav and $TG_DATA/fsd50k/selected.csv
"""

import csv
import io
import os
import zipfile

import devsim

ROOT = devsim.DATA / 'fsd50k'

POS = {'Engine', 'Idling', 'Heavy_engine_(low_frequency)', 'Truck', 'Bus',
       'Accelerating_and_revving_and_vroom', 'Medium_engine_(mid_frequency)',
       'Light_engine_(high_frequency)', 'Motorcycle', 'Engine_starting', 'Tractor'}
POS_BLOCK = {'Car_passing_by', 'Aircraft', 'Fixed-wing_aircraft_and_airplane', 'Helicopter',
             'Train', 'Rail_transport', 'Siren', 'Vehicle_horn_and_car_horn_and_honking',
             'Skateboard', 'Speech', 'Music'}
NEG_NATURE = {'Rain', 'Raindrop', 'Wind', 'Thunder', 'Thunderstorm', 'Stream', 'Ocean',
              'Waves_and_surf', 'Crackle', 'Fire', 'Cricket', 'Insect', 'Bird',
              'Bird_vocalization_and_bird_call_and_bird_song', 'Rustling_leaves', 'Water',
              'Frog', 'Chirp_and_tweet', 'Crow', 'Walk_and_footsteps', 'Knock', 'Wood',
              'Chop', 'Crushing', 'Gurgling', 'Drip', 'Pour', 'Splash_and_splatter', 'Bee_and_wasp_and_etc.',
              'Mosquito', 'Fly_and_housefly', 'Hiss'}
NEG_MECH = {'Helicopter', 'Fixed-wing_aircraft_and_airplane', 'Aircraft', 'Train',
            'Rail_transport', 'Car_passing_by'}
ANY_MACHINE = POS | NEG_MECH | {'Vehicle', 'Motor_vehicle_(road)', 'Car', 'Mechanical_fan',
                                'Mechanisms', 'Power_tool', 'Drill', 'Chainsaw', 'Sawing',
                                'Tools', 'Boat_and_Water_vehicle', 'Race_car_and_auto_racing',
                                'Traffic_noise_and_roadway_noise', 'Domestic_sounds_and_home_sounds',
                                'Speech', 'Music', 'Human_voice'}


def classify(labels):
    s = set(labels)
    if s & POS and not s & POS_BLOCK:
        return 'engine'
    if s & NEG_MECH and not s & POS:
        return 'mech'
    if s & NEG_NATURE and not s & ANY_MACHINE:
        return 'forest'
    return None


def open_split(parts):
    sizes = [os.path.getsize(p) for p in parts]
    starts = [0]
    for s in sizes[:-1]:
        starts.append(starts[-1] + s)

    class Cat(io.RawIOBase):
        def __init__(self):
            self.fs = [open(p, 'rb') for p in parts]
            self.pos = 0
            self.total = sum(sizes)

        def readable(self):
            return True

        def seekable(self):
            return True

        def seek(self, off, whence=0):
            self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.total + off)
            return self.pos

        def tell(self):
            return self.pos

        def readinto(self, b):
            n = len(b)
            out = 0
            while out < n and self.pos < self.total:
                i = max(k for k in range(len(starts)) if starts[k] <= self.pos)
                f = self.fs[i]
                f.seek(self.pos - starts[i])
                chunk = f.read(min(n - out, sizes[i] - (self.pos - starts[i])))
                if not chunk:
                    break
                b[out:out + len(chunk)] = chunk
                out += len(chunk)
                self.pos += len(chunk)
            return out

    cat = Cat()
    zf = zipfile.ZipFile(io.BufferedReader(cat, 1 << 20))
    return zf, starts, cat


def main():
    gt = zipfile.ZipFile(ROOT / 'gt.zip')
    name = [n for n in gt.namelist() if n.endswith('eval.csv')][0]
    rows = list(csv.DictReader(io.TextIOWrapper(gt.open(name))))
    sel = {}
    for r in rows:
        k = classify(r['labels'].split(','))
        if k:
            sel[r['fname']] = (k, r['labels'])
    print('selected', len(sel), {k: sum(1 for v in sel.values() if v[0] == k) for k in ('engine', 'mech', 'forest')})
    zf, starts, cat = open_split([ROOT / 'eval.z01', ROOT / 'eval.zip'])
    out = ROOT / 'audio'
    out.mkdir(exist_ok=True)
    n = 0
    for zi in zf.infolist():
        stem = os.path.splitext(os.path.basename(zi.filename))[0]
        if stem not in sel:
            continue
        # zipfile treats the stream as one disk and adds starts[-1] (central directory on
        # the last disk); CD offsets are relative to each member's own disk
        fixed = zi.header_offset - starts[-1] + starts[zi.volume]
        cat.seek(fixed)
        if cat.read(4) != b'PK\x03\x04':
            raise RuntimeError('bad local header for %s' % zi.filename)
        zi.header_offset = fixed
        with zf.open(zi) as src, open(out / (stem + '.wav'), 'wb') as dst:
            dst.write(src.read())
        n += 1
    with open(ROOT / 'selected.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['fname', 'kind', 'labels'])
        for k, (kind, lab) in sorted(sel.items()):
            if (out / (k + '.wav')).exists():
                w.writerow([k, kind, lab])
    print('extracted', n)


if __name__ == '__main__':
    main()
