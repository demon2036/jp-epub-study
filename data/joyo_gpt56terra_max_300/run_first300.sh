#!/usr/bin/env bash
set -euo pipefail
cd /home/john/jp

RUN_DIR="data/joyo_gpt56terra_max_300"
DB="$RUN_DIR/joyo_gpt56terra_max_300_db.json"

export KANJI_DB_FILE="$DB"
export KANJI_SOURCE="joyo"
export KANJI_SOURCE_LIMIT="2136"
export KANJI_BACKEND="codex"
export CRS_OAI_KEY="${CRS_OAI_KEY:?Set CRS_OAI_KEY before running}"
export CODEX_CRS_BASE_URL="http://45.77.1.146:8310/v1"
export CODEX_MODEL="gpt-5.6-terra"
export CODEX_REASONING_EFFORT="max"
export CODEX_BATCH_SIZE="1"

# 50 个并发请求；每次请求只处理 1 个汉字；本轮仅取 300 个待处理字。
exec python3 scripts/batch_generate_v3.py -b codex --batch-size 1 50 300 3600
