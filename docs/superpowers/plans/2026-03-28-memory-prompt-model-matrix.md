# Memory Prompt Model Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a memory-first kanji prompt, run a fixed Codex model matrix against a representative sample, and export the parsed results as a comparison EPUB.

**Architecture:** Keep the existing kanji pipeline intact while adding a comparison-oriented runner. Update the shared renderer to support both legacy and new prompt schemas, then build a dedicated matrix script that runs Codex with CRS overrides and exports one EPUB grouped by kanji and variant.

**Tech Stack:** Python, asyncio, Codex CLI, CRS provider config, Markdown, EbookLib, unittest

---

### Task 1: Write compatibility tests for the renderer

**Files:**
- Create: `tests/test_render_kanji.py`
- Modify: `/home/john/jp/scripts/render_kanji.py`

- [ ] **Step 1: Write failing tests for legacy and new schema rendering**

Use `unittest` to assert:
- legacy data still renders reading details and memory chain
- new schema renders semantic core and all four memory-group sections

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_render_kanji -v`
Expected: FAIL because the current renderer does not know the new schema

- [ ] **Step 3: Implement minimal renderer changes**

Update `scripts/render_kanji.py` to detect the new schema and render both formats.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_render_kanji -v`
Expected: PASS

### Task 2: Define the new prompt and output schema

**Files:**
- Modify: `/home/john/jp/scripts/prompts/kanji_explain_json.md`
- Create: `/home/john/jp/scripts/schemas/codex_kanji_memory_v1.schema.json`

- [ ] **Step 1: Replace the active prompt with the memory-first four-bucket version**

- [ ] **Step 2: Add a strict JSON schema matching the new prompt**

- [ ] **Step 3: Sanity-check the schema JSON**

Run: `python -m json.tool scripts/schemas/codex_kanji_memory_v1.schema.json >/dev/null`
Expected: PASS

### Task 3: Build the Codex model matrix runner and EPUB exporter

**Files:**
- Create: `/home/john/jp/scripts/run_codex_memory_matrix.py`
- Modify: `/home/john/jp/scripts/make_epub_v2.py` (only if shared helpers are needed)

- [ ] **Step 1: Write failing tests for basic runner helpers**

Add tests for:
- variant slug generation
- default sample set
- comparison artifact path naming

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_codex_memory_matrix -v`
Expected: FAIL because the runner does not exist yet

- [ ] **Step 3: Implement the runner**

The runner should:
- load the prompt template
- apply CRS config overrides
- run the fixed variant matrix concurrently
- parse structured output
- save JSON and prompt snapshots
- generate a comparison EPUB

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_codex_memory_matrix -v`
Expected: PASS

### Task 4: Verify the integrated workflow

**Files:**
- Use: `/home/john/jp/scripts/run_codex_memory_matrix.py`

- [ ] **Step 1: Run the full local test suite for touched units**

Run: `python -m unittest tests.test_render_kanji tests.test_codex_memory_matrix -v`
Expected: PASS

- [ ] **Step 2: Execute a real matrix run**

Run: `python scripts/run_codex_memory_matrix.py`
Expected: completion with a timestamped output directory containing `results.json` and `.epub`

- [ ] **Step 3: Check produced artifacts**

Run: `find data/model_matrix -maxdepth 2 -type f | sort`
Expected: prompt snapshot, results JSON, and EPUB artifact listed for the latest run
