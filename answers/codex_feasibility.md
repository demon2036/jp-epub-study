# Codex Feasibility for batch_generate_v3

## Juice
- Juice (token budget): 16384

## Current State
- `scripts/batch_generate_v3.py` only calls the Claude CLI via `_call_claude`.
- The batch pipeline expects plain text output that can be parsed by `parse_json`.
- There is no codex CLI call path or backend selector in this script.

## Why Codex Is Not Active Yet
- The script never invokes `codex`, so it cannot be used without code changes.
- `parse_json` expects plain JSON text, but the codex CLI produces a JSON event stream
  when `--json` is enabled. Raw codex stdout will not parse as JSON text here.

## Evidence in This Repo
- Claude-only batch path: `scripts/batch_generate_v3.py`
- Codex CLI usage and event parsing pattern: `scripts/explain_kanji.py`
- Strict JSON schema prompt: `scripts/prompts/kanji_explain_json.md`
- Renderer expects stable schema: `scripts/render_kanji.py`

## Feasibility Summary
- Codex is feasible because the repo already uses it successfully in
  `scripts/explain_kanji.py`. That script:
  - runs `codex ... --json`
  - scans the event stream for `item.completed`
  - extracts the final `agent_message` text
- The prompt template is backend-agnostic but strict: it demands pure JSON and a
  fixed schema, which is compatible with codex as long as the extraction is done.

## Minimal Changes Needed (No Code Applied Here)
- Add a codex call in `scripts/batch_generate_v3.py`, similar to the one in
  `scripts/explain_kanji.py`.
- Parse the codex event stream to extract the final assistant text before
  calling `parse_json`.
- Add a backend selector (for example `--backend` or `AGENT_TYPE`) to choose
  between claude and codex without editing the script each time.
- Keep error strings consistent with the existing Claude error format to avoid
  surprises in the DB.

## Schema Constraints to Preserve
- The output must match the JSON schema in `scripts/prompts/kanji_explain_json.md`.
- `scripts/render_kanji.py` expects fields like:
  - `summary`
  - `readings` with `anchor` and `examples`
  - `etymology`, `culture`, `memory_chain`
- Any missing or renamed field will break rendering.

## Practical Prerequisites for Codex
- The `codex` CLI must be installed and available on PATH.
- Authentication must be configured (the CLI must be able to run non-interactively).
- Network access is required for model calls.

## Conclusion
- Right now, `scripts/batch_generate_v3.py` cannot use codex because it only
  calls Claude.
- With a small patch that adds a codex branch and event extraction, codex is
  usable without changing the downstream JSON schema.
