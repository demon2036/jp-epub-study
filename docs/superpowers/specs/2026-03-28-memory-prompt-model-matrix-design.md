# Memory Prompt Model Matrix Design

**Goal:** Compare a new "memory-first" kanji prompt across a fixed Codex model matrix and package the outputs into an EPUB for manual review.

## Scope

This change covers three connected pieces:

1. Replace the active kanji JSON prompt with a four-bucket memory structure:
   - scenario contrast
   - homophone contrast
   - near-synonym boundary
   - same-kanji semantic expansion
2. Add a repeatable Codex matrix runner for:
   - `gpt-5.2` with `xhigh`
   - `gpt-5.4` with `low`, `medium`, `high`, `xhigh`
3. Export the parsed results into a comparison EPUB so outputs can be reviewed by kanji and model variant.

## Workflow

The comparison flow should use a small representative kanji sample by default so the user can inspect prompt quality quickly instead of running the full corpus. The default sample should stress the target memory patterns:

- `並`: scenario contrast
- `橋`: homophone contrast
- `見`: near-synonym usage boundaries
- `生`: multi-reading and same-kanji semantic expansion

The runner should:

1. Load the active prompt template and substitute `{kanji}`.
2. Execute Codex calls concurrently with CRS config overrides.
3. Enforce a JSON schema during generation for stable parsing.
4. Save structured results and a rendered EPUB in a timestamped output directory.

## Rendering

The current renderer is tied to the older schema. It should be updated to:

- keep rendering legacy database entries
- render the new memory-first schema cleanly
- support reuse by the comparison EPUB generator

## Output

The matrix run should emit:

- a JSON results file
- a text file containing the active prompt template
- one comparison EPUB with one chapter per kanji and one section per model variant

## Risks

- Some kanji will not naturally support all four memory buckets. The prompt should require all four arrays to be present, but allow empty arrays when a bucket has no high-value content.
- Model outputs may still drift. A strict output schema and parser reuse should reduce repair work.
- Existing EPUB generation must keep working for legacy stored data.
