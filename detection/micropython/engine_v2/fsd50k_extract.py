"""Extract the engine / weather / nature clips of the FSD50K eval set (Fonseca et al. 2022,
IEEE/ACM TASLP 30; Zenodo 4060432) from the split archive FSD50K.eval_audio.{z01,zip}.

No `zip`/`7z` here and Python's zipfile refuses multi-disk Zip64, so the two parts are read
as one byte stream and the central directory is parsed by hand; every member is located
by (disk, offset), inflated with zlib and checked against its CRC-32.

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

    return Cat()


def central_directory(cat):
    """Parse the (Zip64) central directory by hand: zipfile refuses multi-disk archives.
    PKWARE APPNOTE 6.3.x, sections 4.3.12 (central header), 4.3.14-15 (Zip64 EOCD)."""
    import struct
    tail = 1 << 16
    cat.seek(cat.total - tail)
    buf = cat.read(tail)
    i = buf.rfind(b'PK\x06\x07')                       # Zip64 EOCD locator
    if i < 0:
        raise RuntimeError('no Zip64 locator')
    j = buf.rfind(b'PK\x06\x06', 0, i)                 # Zip64 EOCD record (same, last disk)
    rec = buf[j:j + 56]
    (_, _, _, _, disk_no, cd_disk, n_disk, n_tot, cd_size, cd_off) = struct.unpack('<IQHHIIQQQQ', rec)
    return disk_no, cd_disk, n_tot, cd_size, cd_off


def entries(cat, starts):
    import struct
    disk_no, cd_disk, n_tot, cd_size, cd_off = central_directory(cat)
    cat.seek(starts[cd_disk] + cd_off)
    cd = cat.read(cd_size)
    p = 0
    out = []
    for _ in range(n_tot):
        (sig, _, _, _, method, _, _, crc, csize, usize, nlen, xlen, clen, disk, _, _, off) = \
            struct.unpack('<IHHHHHHIIIHHHHHII', cd[p:p + 46])
        assert sig == 0x02014b50
        name = cd[p + 46:p + 46 + nlen].decode('utf-8', 'replace')
        extra = cd[p + 46 + nlen:p + 46 + nlen + xlen]
        q = 0
        while q + 4 <= len(extra):
            hid, hsz = struct.unpack('<HH', extra[q:q + 4])
            if hid == 1:                                   # Zip64 extended information
                vals = extra[q + 4:q + 4 + hsz]
                k = 0
                if usize == 0xFFFFFFFF:
                    usize = struct.unpack('<Q', vals[k:k + 8])[0]; k += 8
                if csize == 0xFFFFFFFF:
                    csize = struct.unpack('<Q', vals[k:k + 8])[0]; k += 8
                if off == 0xFFFFFFFF:
                    off = struct.unpack('<Q', vals[k:k + 8])[0]; k += 8
                if disk == 0xFFFF:
                    disk = struct.unpack('<I', vals[k:k + 4])[0]; k += 4
            q += 4 + hsz
        out.append((name, method, csize, usize, disk, off, crc))
        p += 46 + nlen + xlen + clen
    return out


def read_member(cat, starts, e):
    import struct
    import zlib
    name, method, csize, usize, disk, off, crc = e
    cat.seek(starts[disk] + off)
    h = cat.read(30)
    sig, _, _, meth, _, _, _, _, _, nlen, xlen = struct.unpack('<IHHHHHIIIHH', h)
    if sig != 0x04034b50:
        raise RuntimeError('bad local header for %s' % name)
    cat.read(nlen + xlen)
    data = cat.read(csize)
    if method == 8:
        data = zlib.decompress(data, -15)
    elif method != 0:
        raise RuntimeError('method %d' % method)
    if zlib.crc32(data) & 0xFFFFFFFF != crc:
        raise RuntimeError('CRC mismatch for %s' % name)
    return data


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
    parts = [ROOT / 'eval.z01', ROOT / 'eval.zip']
    sizes = [os.path.getsize(p) for p in parts]
    starts = [0, sizes[0]]
    cat = open_split(parts)
    out = ROOT / 'audio'
    out.mkdir(exist_ok=True)
    n = 0
    for e in entries(cat, starts):
        stem = os.path.splitext(os.path.basename(e[0]))[0]
        if stem not in sel or not e[0].endswith('.wav'):
            continue
        (out / (stem + '.wav')).write_bytes(read_member(cat, starts, e))
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
