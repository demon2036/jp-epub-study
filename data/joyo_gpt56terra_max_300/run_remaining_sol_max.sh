#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

RUN_DIR="data/joyo_gpt56terra_max_300"
DB="$RUN_DIR/joyo_gpt56terra_max_300_db.json"
TAG="joyo-terra-max-823"
EPUB="$RUN_DIR/joyo_terra823_sol1313_max_2136.epub"
SOL_EPUB="$RUN_DIR/joyo_gpt56sol_max_1313.epub"
AUDIT_REPORT="$RUN_DIR/joyo_terra823_sol1313_max_2136_pronunciation_audit.json"
MANIFEST="$RUN_DIR/joyo_terra823_sol1313_max_2136_manifest.json"
CONCURRENCY="${CONCURRENCY:-60}"
STATUS="$RUN_DIR/status_sol_max_c${CONCURRENCY}.json"
LOCK="$RUN_DIR/run_remaining_sol_max.lock"
MAX_ROUNDS="${MAX_ROUNDS:-20}"

: "${CRS_OAI_KEY:?Set CRS_OAI_KEY before running}"

export KANJI_DB_FILE="$DB"
export KANJI_SOURCE="joyo"
export KANJI_SOURCE_LIMIT="2136"
export KANJI_BACKEND="codex"
export CODEX_CRS_BASE_URL="http://45.77.1.146:8338/v1"
export CODEX_MODEL="gpt-5.6-sol"
export CODEX_REASONING_EFFORT="max"
export CODEX_BATCH_SIZE="1"
export DB TAG STATUS MANIFEST EPUB SOL_EPUB AUDIT_REPORT CONCURRENCY

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "ERROR: another Sol runner already holds $LOCK" >&2
  exit 73
fi

write_status() {
  python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

db_path = Path(os.environ["DB"])
db = json.loads(db_path.read_text(encoding="utf-8"))
counts = {}
for entry in db["kanji"].values():
    status = entry.get("status", "unknown")
    counts[status] = counts.get(status, 0) + 1
out = {
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "db": str(db_path),
    "model": "gpt-5.6-sol",
    "reasoning_effort": "max",
    "concurrency": int(os.environ["CONCURRENCY"]),
    "batch_size": 1,
    "meta": db.get("meta", {}),
    "status_counts": counts,
}
Path(os.environ["STATUS"]).write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(out, ensure_ascii=False))
PY
}

verify_terra_checkpoint() {
  python3 - <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path

db_path = Path(os.environ["DB"])
current = json.loads(db_path.read_text(encoding="utf-8"))
tagged = json.loads(
    subprocess.check_output(
        ["git", "show", f"{os.environ['TAG']}:{db_path}"], text=True
    )
)
changed = [
    kanji
    for kanji, entry in tagged["kanji"].items()
    if entry.get("status") == "completed" and current["kanji"].get(kanji) != entry
]
if changed:
    print(
        f"ERROR: Terra checkpoint entries changed ({len(changed)}): {''.join(changed[:20])}",
        file=sys.stderr,
    )
    sys.exit(1)
print("Terra checkpoint verified: 823 entries unchanged")
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
for entry in db["kanji"].values():
    status = entry.get("status", "unknown")
    counts[status] = counts.get(status, 0) + 1
total = int(db.get("meta", {}).get("total", 0))
completed = counts.get("completed", 0)
sys.exit(0 if total == 2136 and completed == total and len(counts) == 1 else 1)
PY
}

write_manifest() {
  python3 - <<'PY'
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

db_path = Path(os.environ["DB"])
db = json.loads(db_path.read_text(encoding="utf-8"))
epub_path = Path(os.environ["EPUB"])
sol_epub_path = Path(os.environ["SOL_EPUB"])
payload = {
    "created_at": datetime.now(timezone.utc).isoformat(),
    "database": str(db_path),
    "database_sha256": hashlib.sha256(db_path.read_bytes()).hexdigest(),
    "source": "joyo_2010_all_2136",
    "model_segments": [
        {
            "model": "gpt-5.6-terra",
            "reasoning_effort": "max",
            "count": 823,
            "checkpoint_tag": os.environ["TAG"],
        },
        {
            "model": "gpt-5.6-sol",
            "reasoning_effort": "max",
            "count": 1313,
            "endpoint": "http://45.77.1.146:8338/v1",
            "batch_size": 1,
            "concurrency_history": [
                {"concurrency": 10, "completed": 10},
                {"concurrency": 30, "completed": 95},
                {"concurrency": 60, "completed": 1208},
            ],
        },
    ],
    "meta": db.get("meta", {}),
    "epub": str(epub_path),
    "epub_sha256": hashlib.sha256(epub_path.read_bytes()).hexdigest(),
    "sol_only_epub": str(sol_epub_path),
    "sol_only_epub_sha256": hashlib.sha256(sol_epub_path.read_bytes()).hexdigest(),
    "pronunciation_audit": os.environ["AUDIT_REPORT"],
}
Path(os.environ["MANIFEST"]).write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
)
PY
}

generate_sol_epub() {
  python3 - <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path

db_path = Path(os.environ["DB"])
current = json.loads(db_path.read_text(encoding="utf-8"))
tagged = json.loads(
    subprocess.check_output(
        ["git", "show", f"{os.environ['TAG']}:{db_path}"], text=True
    )
)
terra = {
    kanji
    for kanji, entry in tagged["kanji"].items()
    if entry.get("status") == "completed"
}
completed = {
    kanji
    for kanji, entry in current["kanji"].items()
    if entry.get("status") == "completed"
}
sol = completed - terra
if len(terra) != 823 or len(sol) != 1313:
    print(
        f"ERROR: expected Terra=823 and Sol=1313, got {len(terra)} and {len(sol)}",
        file=sys.stderr,
    )
    sys.exit(1)

sys.path.insert(0, str(Path("scripts").resolve()))
from make_epub_v2 import create_epub

create_epub(
    db_path,
    Path(os.environ["SOL_EPUB"]),
    include_kanji=sol,
    title="常用漢字詳解（Sol Max・1313字）",
    identifier="joyo-kanji-sol-max-1313",
)
PY
}

on_exit() {
  code=$?
  write_status || true
  echo "=== Sol c${CONCURRENCY} runner exited code=$code at $(date -Is) ==="
}
trap on_exit EXIT

verify_terra_checkpoint
write_status

for round in $(seq 1 "$MAX_ROUNDS"); do
  if all_complete; then
    break
  fi
  echo "=== Sol generation round $round/$MAX_ROUNDS at $(date -Is) ==="
  python3 scripts/batch_generate_v3.py \
    -b codex --batch-size 1 --retry-failed "$CONCURRENCY" 0 3600
  verify_terra_checkpoint
  write_status
  if ! all_complete; then
    echo "=== incomplete after round $round; retrying in 20 seconds ==="
    sleep 20
  fi
done

if ! all_complete; then
  echo "ERROR: unfinished items remain after $MAX_ROUNDS rounds" >&2
  exit 1
fi

verify_terra_checkpoint
python3 scripts/kanji_pronunciation_audit.py --fix --report "$AUDIT_REPORT" "$DB"
verify_terra_checkpoint
python3 scripts/make_epub_v2.py \
  --db "$DB" \
  --output "$EPUB" \
  --title "常用漢字詳解（Terra Max 823字＋Sol Max 1313字）" \
  --identifier "joyo-kanji-terra823-sol1313-max-2136"
generate_sol_epub
write_manifest
write_status
echo "=== complete: $EPUB ==="
