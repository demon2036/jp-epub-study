#!/usr/bin/env bash
set -euo pipefail
cd /home/john/jp

RUN_DIR="data/joyo_gpt55_2000"
DB="$RUN_DIR/joyo_kanji_gpt55_2000_db.json"
EPUB="$RUN_DIR/joyo_kanji_gpt55_2000.epub"
AUDIT_REPORT="$RUN_DIR/joyo_kanji_gpt55_2000_pronunciation_audit.json"
MANIFEST="$RUN_DIR/joyo_kanji_gpt55_2000_manifest.json"
STATUS="$RUN_DIR/status.json"

export KANJI_DB_FILE="$DB"
export KANJI_SOURCE="joyo"
export KANJI_SOURCE_LIMIT="2000"
export CODEX_CRS_BASE_URL="https://aether.fawney.fun/v1"
export CODEX_BATCH_SIZE="10"
export KANJI_BACKEND="codex"

write_status() {
  python3 - <<'PY'
import json, os
from datetime import datetime
from pathlib import Path
status_path = Path(os.environ['STATUS'])
db_path = Path(os.environ['DB'])
status = {
    'updated_at': datetime.now().isoformat(),
    'db': str(db_path),
    'epub': os.environ['EPUB'],
    'audit_report': os.environ['AUDIT_REPORT'],
    'manifest': os.environ['MANIFEST'],
}
if db_path.exists():
    db = json.loads(db_path.read_text(encoding='utf-8'))
    counts = {}
    for entry in db.get('kanji', {}).values():
        counts[entry.get('status', 'unknown')] = counts.get(entry.get('status', 'unknown'), 0) + 1
    status.update({'meta': db.get('meta', {}), 'status_counts': counts})
status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(status, ensure_ascii=False))
PY
}

export DB EPUB AUDIT_REPORT MANIFEST STATUS
trap 'code=$?; echo "=== pipeline exit code ${code}: $(date -Is) ==="; echo "$code" > "$RUN_DIR/exit_code"; write_status || true' EXIT
write_status

round=1
max_rounds=5
while [ "$round" -le "$max_rounds" ]; do
  echo "=== generation round $round/$max_rounds: $(date -Is) ==="
  python3 scripts/batch_generate_v3.py -b codex --batch-size 10 --retry-failed 10 0 3600
  write_status
  if python3 - <<'PY'
import json, os, sys
from pathlib import Path
db = json.loads(Path(os.environ['DB']).read_text(encoding='utf-8'))
meta = db.get('meta', {})
counts = {}
for entry in db.get('kanji', {}).values():
    counts[entry.get('status', 'unknown')] = counts.get(entry.get('status', 'unknown'), 0) + 1
complete = counts.get('completed', 0) == meta.get('total', 0)
print(json.dumps({'complete': complete, 'counts': counts, 'total': meta.get('total')}, ensure_ascii=False))
sys.exit(0 if complete else 1)
PY
  then
    break
  fi
  round=$((round + 1))
done

python3 - <<'PY'
import json, os, sys
from pathlib import Path
db = json.loads(Path(os.environ['DB']).read_text(encoding='utf-8'))
meta = db.get('meta', {})
counts = {}
for entry in db.get('kanji', {}).values():
    counts[entry.get('status', 'unknown')] = counts.get(entry.get('status', 'unknown'), 0) + 1
complete = counts.get('completed', 0) == meta.get('total', 0)
print(json.dumps({'final_generation_complete': complete, 'counts': counts, 'total': meta.get('total')}, ensure_ascii=False))
sys.exit(0 if complete else 2)
PY

python3 scripts/kanji_pronunciation_audit.py --fix --report "$AUDIT_REPORT" "$DB"
python3 scripts/make_epub_v2.py --db "$DB" --output "$EPUB"
python3 - <<'PY'
import json, os
from datetime import datetime
from pathlib import Path

db_path = Path(os.environ['DB'])
db = json.loads(db_path.read_text(encoding='utf-8'))
counts = {}
for entry in db.get('kanji', {}).values():
    counts[entry.get('status', 'unknown')] = counts.get(entry.get('status', 'unknown'), 0) + 1
manifest = {
    'created_at': datetime.now().isoformat(),
    'model': 'gpt-5.5',
    'reasoning_effort': 'xhigh',
    'source': 'joyo_2010_first_2000',
    'batch_size': 10,
    'concurrency': 10,
    'db': str(db_path),
    'epub': os.environ['EPUB'],
    'audit_report': os.environ['AUDIT_REPORT'],
    'status_counts': counts,
    'meta': db.get('meta', {}),
}
Path(os.environ['MANIFEST']).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(manifest, ensure_ascii=False))
PY
write_status
