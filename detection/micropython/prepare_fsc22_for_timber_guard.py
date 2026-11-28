"""Build an FSC22 forest-background manifest for Timber Guard v4.2.

Run from the `micropython` project root. The script does NOT overwrite the
original dataset_manifest.csv or any model/results. Python standard library only.

Example:
    python prepare_fsc22_for_timber_guard.py --fsc22 'C:/Datasets/FSC22-main'

It accepts either an extracted GitHub repository directory or its ZIP archive.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

# Exactly 7 environmental classes, all 4 human classes, and 6 plausible
# animal classes relevant to Poland. Dataset class names match FSC22 Metadata.
# Only the 'background' subset can be randomly mixed with engine recordings;
# negative examples from 'hard_negative' are learned as NO_ENGINE but not mixed.
CLASS_GROUPS = {
    # Environmental sounds
    'Rain': 'background',
    'Thunderstorm': 'background',
    'WaterDrops': 'background',
    'Wind': 'background',
    'Silence': 'hard_negative',
    'Fire': 'hard_negative',
    'TreeFalling': 'hard_negative',
    # Human sounds
    'Whistling': 'hard_negative',
    'Speaking': 'hard_negative',
    'Footsteps': 'hard_negative',
    'Clapping': 'hard_negative',
    # Animal sounds
    'Squirrel': 'background',
    'BirdChirping': 'background',
    'WingFlaping': 'background',  # FSC22 spells this without the second 'p'.
    'Frog': 'background',
    'Insect': 'background',
    'WolfHowl': 'background',
}

REQUIRED_FIELDS = {
    'dataset', 'container', 'audio_member', 'source_id', 'group',
    'target_engine', 'use_for_training', 'split', 'sha256', 'duration_s'
}


def source_group(name: str) -> str:
    """Keep different 5-second cuts of a single FreeSound source in one split."""
    stem = Path(name.strip()).stem
    match = re.match(r'^(\d+)', stem)
    if match:
        return match.group(1)
    return re.sub(r'(?i)_+[A-Z]$', '', stem) or stem


def source_split(source: str, seed: int) -> str:
    # Stable cross-platform grouped split. Does not rely on Python hash().
    number = int.from_bytes(
        hashlib.sha256(f'{seed}:FSC22:{source}'.encode('utf-8')).digest()[:8],
        'big'
    ) / 2**64
    return 'train' if number < 0.70 else ('val' if number < 0.85 else 'test')


class DatasetReader:
    """Read GitHub FSC22 ZIP, or its extracted folder."""

    def __init__(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(f'FSC22 path not found: {path}')
        self.path = path
        self.zf = zipfile.ZipFile(path) if path.is_file() else None
        if self.zf:
            names = [n for n in self.zf.namelist() if not n.endswith('/')]
        else:
            names = [p.relative_to(path).as_posix() for p in path.rglob('*') if p.is_file()]
        self.meta = None
        self.audio = {}
        for name in names:
            normalized = '/' + name.replace('\\', '/').lower().lstrip('/')
            if normalized.endswith('/metadata/metadata v1.0 fsc22.csv'):
                self.meta = name
            if '/audios/' in normalized and normalized.endswith('.wav'):
                key = name.split('/')[-1].lower()
                if key in self.audio:
                    raise ValueError(f'Duplicate audio filename inside FSC22: {key}')
                self.audio[key] = name
        if not self.meta:
            raise FileNotFoundError('Expected Metadata/Metadata V1.0 FSC22.csv in FSC22')
        if not self.audio:
            raise FileNotFoundError('Expected WAV files in FSC22/Audios/')

    def read(self, relative_name: str) -> bytes:
        if self.zf:
            return self.zf.read(relative_name)
        return (self.path / relative_name).read_bytes()

    def close(self):
        if self.zf:
            self.zf.close()


def build(args):
    manifest = args.manifest.resolve()
    data_dir = args.data_dir.resolve()
    output_manifest = data_dir / 'dataset_manifest_fsc22.csv'
    output_zip = data_dir / 'FSC22_forest_selected.zip'
    if manifest == output_manifest:
        raise ValueError('Use the original dataset_manifest.csv as --manifest')
    if not manifest.is_file():
        raise FileNotFoundError(f'Original manifest is missing: {manifest}')
    if output_zip.exists() or output_manifest.exists():
        raise FileExistsError('FSC22 outputs already exist. Delete or move the two generated files to rebuild: '
                              f'{output_zip.name}, {output_manifest.name}')
    data_dir.mkdir(parents=True, exist_ok=True)
    with manifest.open('r', newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        missing = REQUIRED_FIELDS - set(fields)
        if missing:
            raise ValueError('Original manifest is missing columns: ' + ', '.join(sorted(missing)))
        original = list(reader)

    # Keep ALL existing engines, hard negatives and old excluded rows, but
    # remove old selected natural background so FSC22 replaces it.
    kept = [r for r in original if not (
        r['use_for_training'] == '1' and r['group'] == 'background'
        and r['target_engine'] == '0'
    )]
    removed_count = len(original) - len(kept)
    used_hashes = {r['sha256'].strip().lower() for r in kept
                   if r.get('use_for_training') == '1' and r.get('sha256')}
    original_positive = sum(r.get('use_for_training') == '1' and
                            r.get('target_engine') == '1' for r in kept)
    if original_positive == 0:
        raise ValueError('No existing ENGINE files found in original manifest')

    dataset = DatasetReader(args.fsc22)
    added = []
    duplicates = 0
    missing_audio = []
    by_class = Counter()
    try:
        with io.StringIO(dataset.read(dataset.meta).decode('utf-8-sig')) as fh:
            meta_rows = list(csv.DictReader(fh))
        # Do not leave a partial ZIP behind on exceptions.
        try:
            with zipfile.ZipFile(output_zip, 'w', compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=3, allowZip64=True) as dst:
                for r in meta_rows:
                    class_name = (r.get('Class Name') or '').strip()
                    if class_name not in CLASS_GROUPS:
                        continue
                    filename = (r.get('Dataset File Name') or '').strip()
                    if not filename or '/' in filename or '\\' in filename:
                        raise ValueError(f'Invalid dataset filename: {filename!r}')
                    member = dataset.audio.get(filename.lower())
                    if member is None:
                        missing_audio.append(filename)
                        continue
                    raw = dataset.read(member)
                    sha = hashlib.sha256(raw).hexdigest()
                    if sha in used_hashes:
                        duplicates += 1
                        continue
                    used_hashes.add(sha)
                    original_name = (r.get('Source File Name') or filename).strip()
                    src = source_group(original_name)
                    split = source_split(src, args.seed)
                    archive_member = f'Audios/{filename}'
                    dst.writestr(archive_member, raw)
                    entry = dict.fromkeys(fields, '')
                    entry.update({
                        'dataset': 'FSC22',
                        'container': output_zip.name,
                        'audio_member': archive_member,
                        'source_id': src,
                        'group': CLASS_GROUPS[class_name],
                        'target_engine': '0',
                        'use_for_training': '1',
                        'split': split,
                        'sha256': sha,
                        'duration_s': '5.0',
                    })
                    # Preserve class information if original manifest has columns for it.
                    for col in ('category', 'class_name', 'label_name'):
                        if col in entry:
                            entry[col] = class_name
                    added.append(entry)
                    by_class[class_name] += 1
            if missing_audio:
                raise FileNotFoundError('FSC22 audio missing for the first files: '
                                        + ', '.join(missing_audio[:10]))
            if not added:
                raise ValueError('No FSC22 clips were selected')
            missing_classes = set(CLASS_GROUPS) - set(by_class)
            if missing_classes:
                raise ValueError('FSC22 classes not found in archive: '
                                 + ', '.join(sorted(missing_classes)))
            # Ensure all source groups are split-disjoint in the combined selection.
            groups = defaultdict(set)
            for r in kept + added:
                if r.get('use_for_training') == '1' and r.get('split') in ('train', 'val', 'test'):
                    groups[(r['dataset'], r['source_id'])].add(r['split'])
            leaks = [k for k, v in groups.items() if len(v) > 1]
            if leaks:
                raise ValueError(f'Cross-split source leakage: {leaks[:3]}')
            if not any(r['group'] == 'background' and r['split'] == 'train' for r in added):
                raise ValueError('No FSC22 background samples assigned to training')
            with output_manifest.open('w', newline='', encoding='utf-8') as fh:
                writer = csv.DictWriter(fh, fieldnames=fields)
                writer.writeheader()
                writer.writerows(kept + added)
        except Exception:
            output_zip.unlink(missing_ok=True)
            output_manifest.unlink(missing_ok=True)
            raise
    finally:
        dataset.close()
    counts = Counter((r['split'], r['group']) for r in added)
    report = {
        'original_selected_background_removed': removed_count,
        'original_engine_kept': original_positive,
        'original_selected_other_kept': sum(r['use_for_training'] == '1' and
                                            r['target_engine'] == '0' for r in kept),
        'selected_fsc22': len(added),
        'fsc22_exact_duplicates_skipped': duplicates,
        'per_class': dict(sorted(by_class.items())),
        'per_split_group': {f'{s}/{g}': n for (s, g), n in sorted(counts.items())},
        'selected_zip': str(output_zip),
        'new_manifest': str(output_manifest),
        'source_split': 'stable source-grouped 70/15/15 using SHA256',
        'original_manifest_overwritten': False,
        'note': 'FSC22 Nature classes can be used as augmentation noise only in train.'
    }
    report_file = data_dir / 'fsc22_selection_report.json'
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('\nREADY: run v4_2_prepare with --manifest', output_manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fsc22', type=Path, required=True,
                        help='Extracted FSC22 GitHub directory or downloaded ZIP')
    parser.add_argument('--manifest', type=Path,
                        default=Path('algorithm/data/dataset_manifest.csv'))
    parser.add_argument('--data-dir', type=Path, default=Path('algorithm/data'))
    parser.add_argument('--seed', type=int, default=2026)
    args = parser.parse_args()
    try:
        build(args)
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        print('ERROR:', e, file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
