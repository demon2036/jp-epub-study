#!/usr/bin/env bash
set -euo pipefail
cd /home/john/jp

RUN_DIR="data/joyo_gpt56sol_max_2136"
DB="$RUN_DIR/joyo_kanji_gpt56sol_max_2136_db.json"
EPUB="$RUN_DIR/joyo_kanji_gpt56sol_max_2136.epub"
AUDIT_REPORT="$RUN_DIR/joyo_kanji_gpt56sol_max_2136_pronunciation_audit.json"
MANIFEST="$RUN_DIR/joyo_kanji_gpt56sol_max_2136_manifest.json"
STATUS="$RUN_DIR/status.json"

export KANJI_DB_FILE="$DB"
export KANJI_SOURCE="joyo"
export KANJI_SOURCE_LIMIT="2136"
export KANJI_BACKEND="codex"
export CODEX_CRS_BASE_URL="http://45.77.1.146:8338/v1"
export CRS_OAI_KEY="${CRS_OAI_KEY:?Set CRS_OAI_KEY before running}"
export CODEX_MODEL="gpt-5.6-sol"
export CODEX_REASONING_EFFORT="max"
export CODEX_BATCH_SIZE="5"

write_status() {
  python3 - <<'PY'
import json, os
from datetime import datetime
from pathlib import Path
p = Path(os.environ["STATUS"])
db_path = Path(os.environ["DB"])
out = {"updated_at": datetime.now().isoformat(), "db": str(db_path)}
if db_path.exists():
    db = json.loads(db_path.read_text(encoding="utf-8"))
    counts = {}
    for entry in db.get("kanji", {}).values():
        status = entry.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    out.update({"meta": db.get("meta", {}), "status_counts": counts})
p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False))
PY
}

export DB EPUB AUDIT_REPORT MANIFEST STATUS
trap 'code=$?; echo "$code" > "$RUN_DIR/exit_code"; write_status || true' EXIT
write_status

for round in 1 2 3 4 5; do
  echo "=== generation round $round/5: $(date -Is) ==="
  python3 scripts/batch_generate_v3.py -b codex --batch-size 5 --retry-failed 128 0 3600
  write_status
  if python3 - <<'PY'
import json, os, sys
from pathlib import Path
db = json.loads(Path(os.environ["DB"]).read_text(encoding="utf-8"))
counts = {}
for entry in db.get("kanji", {}).values():
    status = entry.get("status", "unknown")
    counts[status] = counts.get(status, 0) + 1
sys.exit(0 if counts.get("completed", 0) == db.get("meta", {}).get("total", 0) else 1)
PY
  then
    break
  fi
done

python3 scripts/kanji_pronunciation_audit.py --fix --report "$AUDIT_REPORT" "$DB"
python3 scripts/make_epub_v2.py --db "$DB" --output "$EPUB"
python3 - <<'PY'
import json, os
from datetime import datetime
from pathlib import Path
db = json.loads(Path(os.environ["DB"]).read_text(encoding="utf-8"))
counts = {}
for entry in db.get("kanji", {}).values():
    status = entry.get("status", "unknown")
    counts[status] = counts.get(status, 0) + 1
manifest = {
    "created_at": datetime.now().isoformat(),
    "model": "gpt-5.6-sol",
    "reasoning_effort": "max",
    "source": "joyo_2010_all_2136",
    "batch_size": 5,
    "concurrency": 128,
    "routing": "round-robin",
    "endpoint": "45.77.1.146:8338",
    "status_counts": counts,
    "meta": db.get("meta", {}),
}
Path(os.environ["MANIFEST"]).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(manifest, ensure_ascii=False))
PY
write_status
