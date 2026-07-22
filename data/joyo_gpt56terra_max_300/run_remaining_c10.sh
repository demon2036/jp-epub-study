#!/usr/bin/env bash
set -euo pipefail

cd /home/john/jp

RUN_DIR="data/joyo_gpt56terra_max_300"
DB="$RUN_DIR/joyo_gpt56terra_max_300_db.json"
EPUB="$RUN_DIR/joyo_gpt56terra_max_2136.epub"
AUDIT_REPORT="$RUN_DIR/joyo_gpt56terra_max_2136_pronunciation_audit.json"
STATUS="$RUN_DIR/status_remaining_c10.json"
MAX_ROUNDS="${MAX_ROUNDS:-8}"

: "${CRS_OAI_KEY:?Set CRS_OAI_KEY before running}"
export KANJI_DB_FILE="$DB"
export KANJI_SOURCE="joyo"
export KANJI_SOURCE_LIMIT="2136"
export KANJI_BACKEND="codex"
export CODEX_CRS_BASE_URL="http://45.77.1.146:8310/v1"
export CODEX_MODEL="gpt-5.6-terra"
export CODEX_REASONING_EFFORT="max"
export CODEX_BATCH_SIZE="1"
export DB STATUS

write_status() {
  python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

db_path = Path(os.environ["DB"])
out = {"updated_at": datetime.now(timezone.utc).isoformat(), "db": str(db_path)}
if db_path.exists():
    db = json.loads(db_path.read_text(encoding="utf-8"))
    counts = {}
    for entry in db.get("kanji", {}).values():
        status = entry.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    out.update({"meta": db.get("meta", {}), "status_counts": counts})
Path(os.environ["STATUS"]).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False))
PY
}

all_complete() {
  python3 - <<'PY'
import json
import os
import sys
from pathlib import Path

db = json.loads(Path(os.environ["DB"]).read_text(encoding="utf-8"))
counts = {}
for entry in db.get("kanji", {}).values():
    status = entry.get("status", "unknown")
    counts[status] = counts.get(status, 0) + 1
total = int(db.get("meta", {}).get("total", 0))
completed = int(counts.get("completed", 0))
print(json.dumps({"total": total, "completed": completed, "status_counts": counts}, ensure_ascii=False))
sys.exit(0 if total > 0 and completed == total and not counts.get("pending") and not counts.get("failed") else 1)
PY
}

on_exit() {
  code=$?
  write_status || true
  echo "=== runner exited code=${code} at $(date -Is) ==="
  exit "$code"
}
trap on_exit EXIT

write_status
for round in $(seq 1 "$MAX_ROUNDS"); do
  echo "=== generation round ${round}/${MAX_ROUNDS}: $(date -Is) ==="
  # Exactly ten concurrent, one-kanji Codex requests. Failed requests are retried in later rounds.
  python3 scripts/batch_generate_v3.py -b codex --batch-size 1 --retry-failed 10 0 3600
  write_status
  if all_complete; then
    echo "=== all 2136 kanji completed; auditing pronunciations ==="
    python3 scripts/kanji_pronunciation_audit.py --fix --report "$AUDIT_REPORT" "$DB"
    echo "=== building EPUB ==="
    python3 scripts/make_epub_v2.py --db "$DB" --output "$EPUB"
    echo "=== EPUB written: $EPUB ==="
    exit 0
  fi
  echo "=== incomplete after round ${round}; retrying remaining items in 15 seconds ==="
  sleep 15
done

echo "ERROR: unfinished items remain after ${MAX_ROUNDS} rounds; EPUB was not built." >&2
all_complete
