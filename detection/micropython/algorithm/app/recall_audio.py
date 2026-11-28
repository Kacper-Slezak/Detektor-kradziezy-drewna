"""Acquire a small, pinned collection of genuine engine and forest recordings."""

import argparse
import csv
import hashlib
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MANIFEST = Path(__file__).resolve().parents[1] / 'real_recordings.csv'
AUDIO = Path('algorithm/data/real_recall')
MAX_BYTES = 33_000_000


def recordings(manifest):
    with manifest.open(encoding='utf8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    names, hashes, groups = set(), set(), {}
    for row in rows:
        name, role, group = row['file'], row['role'], row['group']
        digest = row['sha256'].lower()
        if (not re.fullmatch(r'[a-zA-Z0-9_-]+\.(wav|ogg|flac)', name)
                or name in names or not re.fullmatch(r'[a-f0-9]{64}', digest)
                or digest in hashes or not group or groups.setdefault(group, role) != role
                or role not in ('train', 'validation')
                or not row['credit'] or not row['license'] or not row['description']):
            raise ValueError('Invalid or duplicate recording: ' + name)
        if role == 'train':
            if int(row['start_s']) < 0 or int(row['end_s']) - int(row['start_s']) < 2:
                raise ValueError('Training recording needs an explicit engine interval: ' + name)
        elif row['start_s'] or row['end_s']:
            raise ValueError('Scene-level validation recordings cannot label individual windows')
        names.add(name)
        hashes.add(digest)
        row['sha256'] = digest
    return rows


def verify(data, row):
    if hashlib.sha256(data).hexdigest() != row['sha256']:
        raise ValueError('Audio checksum mismatch: ' + row['file'])


def acquire(manifest, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for row in recordings(manifest):
        path = destination / row['file']
        if path.exists():
            verify(path.read_bytes(), row)
        else:
            url = urlsplit(row['download_url'])
            if url.scheme != 'https':
                raise ValueError('Expected an HTTPS audio source')
            request = Request(row['download_url'], headers={'User-Agent': 'TimberGuardResearch/1.0'})
            with urlopen(request, timeout=30) as response:
                data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError('Audio exceeds the individual file budget')
            verify(data, row)
            with path.open('xb') as stream:
                stream.write(data)
        print('Verified', path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=MANIFEST)
    parser.add_argument('--destination', type=Path, default=AUDIO)
    args = parser.parse_args()
    acquire(args.manifest, args.destination)


if __name__ == '__main__':
    main()
