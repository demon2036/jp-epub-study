"""Compare selected characters with the primary-source common-reading table."""
from pathlib import Path
import argparse
import json
import re

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-text', type=Path,
                    help='Re-extract the table from pdftotext -layout output instead of the saved snapshot')
args = parser.parse_args()
if args.source_text:
    source = args.source_text.read_text()
    start = source.find('亜（亞）')
    assert start >= 0, 'The source text must contain the common-kanji reading table'
    source = source[start:]
    allchars = set((ROOT.parents[1] / 'data/joyo_kanji_2010.txt').read_text().split())
    rows = {}
    active = None
    for line in source.split('\n'):
        match = re.match(r'^\s{0,16}(\S)(?:（[^）]+）)?\s+([ぁ-ゖァ-ヺ]+)(?:\s+(.*))?$', line)
        if match and match[1] in allchars:
            active = match[1]
            rows.setdefault(active, []).append({'kana': match[2], 'examples': (match[3] or '').strip()})
            continue
        match = re.match(r'^\s{24,35}([ぁ-ゖァ-ヺ]+)\s+(.+)$', line)
        if active and match:
            rows[active].append({'kana': match[1], 'examples': match[2].strip()})
else:
    rows = json.loads((ROOT / 'research/official-readings.json').read_text())

assembled = json.loads((ROOT / 'assembled.json').read_text())
selected = {char: rows.get(char, []) for char in assembled['order']}
assert all(selected.values()), 'Every selected character must have a parsed primary-source row'

def hira(text):
    return ''.join(chr(ord(char) - 96) if 'ァ' <= char <= 'ヶ' else char for char in text)

gaps = []
for char, expected in selected.items():
    actual = {r['kana'] for r in assembled['readings'][char]}
    missing = [r for r in expected if hira(r['kana']) not in actual]
    if missing:
        gaps.append({'char': char, 'missing': missing})

(ROOT / 'research/official-readings.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
(ROOT / 'research/official-reading-gaps.json').write_text(json.dumps(gaps, ensure_ascii=False, indent=2))
print(json.dumps({'parsed_characters': len(rows), 'target_characters': len(selected),
                  'target_readings': sum(map(len, selected.values())),
                  'missing_entries': sum(len(x['missing']) for x in gaps), 'gaps': gaps}, ensure_ascii=False, indent=2))
assert not gaps, 'The book is missing readings from the common-kanji table'
