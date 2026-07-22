#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from codex_exec_support import DEFAULT_CODEX_CWD


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_dotenv_if_present():
    root = _repo_root()
    sys.path.insert(0, str(root))
    try:
        from scripts.dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    load_dotenv(root / ".env", override=False)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_last_agent_message_text(jsonl_text: str) -> str | None:
    last = None
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message" and item.get("text"):
                last = item["text"]
        elif event.get("type") == "response.completed":
            response = event.get("response", {})
            if response.get("output_text"):
                last = response["output_text"]
    return last


def _format_tokens_for_prompt(tokens: list[dict]) -> str:
    lines = [
        "token_index | surface | base | pos_major | pos_sub | reading_kana | infl_type | infl_form",
    ]
    for i, t in enumerate(tokens, start=1):
        surface = str(t.get("surface", ""))
        base = str(t.get("base", ""))
        pos_major = str(t.get("pos_major", ""))
        pos_sub = str(t.get("pos_sub", ""))
        reading_kana = str(t.get("reading_kana", ""))
        infl_type = str(t.get("infl_type", ""))
        infl_form = str(t.get("infl_form", ""))
        lines.append(
            f"{i} | {surface} | {base} | {pos_major} | {pos_sub} | {reading_kana} | {infl_type} | {infl_form}"
        )
    return "\n".join(lines)


def _build_prompt_detailed(batch: list[dict]) -> str:
    lines: list[str] = [
        "你是日语老师，学习者水平N4。",
        "请为下面每个句子做“逐词+语法功能”标注，并严格只输出 JSON（不要输出任何其它文字）。",
        "",
        "输出 JSON 结构固定为：",
        '{ "annotations": [ { "id": 1, "zh": "...", "tokens": [...], "grammar": [...] } ] }',
        "",
        "硬性要求：",
        "- zh：自然中文整句翻译。",
        "- tokens：必须覆盖该句给出的所有 token（包含助词/助动词；标点也要给出 token_index，但 meaning_zh 可以为空字符串，grammar_note 可为 null）。",
        "  每个 token 输出：token_index(从1开始), reading_kana(平假名), meaning_zh(中文释义/作用), grammar_note(该token在句中的语法功能，简短，可为null)。",
        "- grammar：列出该句出现的主要语法点（可 0–8 个）。每个：pattern, meaning_zh, usage_note, level(可为N3/N2/N1或null)。",
        "- 不要添加句子里不存在的内容；不要输出多余文字。",
        "",
        "句子：",
    ]
    for item in batch:
        jp = str(item.get("jp", "")).replace("\n", "").strip()
        tokens = item.get("tokens")
        if not isinstance(tokens, list):
            tokens = []
        lines.append(f'\nID {item["id"]}: {jp}')
        lines.append(_format_tokens_for_prompt(tokens))
    return "\n".join(lines).strip() + "\n"


def _build_prompt_summary(batch: list[dict]) -> str:
    lines = [
        "你是日语老师，学习者水平N4。",
        "请为下面每个句子做标注，并严格只输出 JSON（不要输出任何其它文字）。",
        "",
        "输出必须符合这个结构：",
        '{ "annotations": [ { "id": 1, "zh": "...", "words": [...], "grammar": [...] } ] }',
        "",
        "要求：",
        "- zh：自然中文翻译（不要逐词硬翻）。",
        "- words：最多6个对N4有价值的词/短语（尽量关键/偏难）。每个包含：jp, reading(假名), pos, meaning_zh, note(可为null)。",
        "- grammar：最多3个语法点（没有就 []）。每个包含：pattern, meaning_zh, usage_note, level(可为N3/N2/N1或null)。",
        "- 不要捏造没有出现在句子里的词/语法点。",
        "",
        "句子：",
    ]
    for item in batch:
        jp = str(item.get("jp", "")).replace("\n", "").strip()
        lines.append(f'{item["id"]}. {jp}')
    return "\n".join(lines).strip() + "\n"


def _read_config_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _collect_codex_config_args(config_file: Path | None, config_overrides: list[str]) -> list[str]:
    args: list[str] = []
    if config_file and config_file.exists():
        for line in _read_config_lines(config_file):
            args.extend(["-c", line])
    for item in config_overrides:
        item = (item or "").strip()
        if not item:
            continue
        args.extend(["-c", item])
    extra = os.environ.get("CODEX_EXTRA_ARGS")
    if extra:
        args.extend(shlex.split(extra))
    return args


def _run_codex(
    prompt: str,
    *,
    schema_path: Path,
    model: str | None,
    cd: Path | None,
    config_args: list[str],
) -> dict:
    cmd = [
        "codex",
        "exec",
        "--json",
        "--skip-git-repo-check",
        "-s",
        "read-only",
        "--output-schema",
        str(schema_path),
        *config_args,
    ]
    if model:
        cmd.extend(["-m", model])
    if cd:
        cmd.extend(["-C", str(cd)])

    proc = subprocess.run(cmd + [prompt], capture_output=True, text=True, env=os.environ.copy())
    if proc.returncode != 0:
        raise RuntimeError(f"codex exec failed ({proc.returncode}):\n{proc.stderr.strip()}")

    msg = _extract_last_agent_message_text(proc.stdout)
    if not msg:
        raise RuntimeError("codex exec produced no agent_message")

    try:
        return json.loads(msg)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse JSON from codex output:\n{msg[:2000]}") from exc


def annotate_file(
    in_path: Path,
    out_path: Path,
    *,
    start_id: int,
    count: int,
    batch_size: int,
    only_missing: bool,
    include_spine: str | None,
    exclude_spine: str | None,
    mode: str,
    schema_path: Path,
    model: str | None,
    cd: Path | None,
    config_args: list[str],
):
    data = _read_json(in_path)
    sentences = data.get("sentences")
    if not isinstance(sentences, list):
        raise ValueError("Invalid input JSON: missing sentences[]")

    by_id = {}
    for s in sentences:
        sid = s.get("id")
        if isinstance(sid, int):
            by_id[sid] = s

    ids = [sid for sid in sorted(by_id) if sid >= start_id]
    if count > 0:
        ids = ids[:count]

    if only_missing:
        ids = [sid for sid in ids if not by_id[sid].get("zh")]

    include_re = re.compile(include_spine) if include_spine else None
    exclude_re = re.compile(exclude_spine) if exclude_spine else None
    if include_re or exclude_re:
        filtered: list[int] = []
        for sid in ids:
            spine_path = str(by_id[sid].get("spine_path") or "")
            if include_re and not include_re.search(spine_path):
                continue
            if exclude_re and exclude_re.search(spine_path):
                continue
            filtered.append(sid)
        ids = filtered

    if not ids:
        print("Nothing to annotate.")
        _write_json(out_path, data)
        return

    total = len(ids)
    idx = 0
    while idx < total:
        batch_ids = ids[idx : idx + batch_size]
        batch = []
        for sid in batch_ids:
            entry = by_id[sid]
            if mode != "summary" and not isinstance(entry.get("tokens"), list):
                raise RuntimeError(
                    "Detailed mode requires sentence tokens. Re-run extraction with Janome enabled "
                    "(install: pip install -r requirements.txt)."
                )
            batch.append(
                {
                    "id": sid,
                    "jp": entry.get("jp", ""),
                    "tokens": entry.get("tokens", []),
                }
            )

        if mode == "summary":
            prompt = _build_prompt_summary(batch)
        else:
            prompt = _build_prompt_detailed(batch)
        result = _run_codex(prompt, schema_path=schema_path, model=model, cd=cd, config_args=config_args)

        annotations = result.get("annotations")
        if not isinstance(annotations, list):
            raise RuntimeError("Invalid codex output: missing annotations[]")

        for ann in annotations:
            sid = ann.get("id")
            if not isinstance(sid, int) or sid not in by_id:
                continue
            by_id[sid]["zh"] = ann.get("zh", "")
            if mode == "summary":
                by_id[sid]["words"] = ann.get("words", []) if isinstance(ann.get("words"), list) else []
                by_id[sid]["grammar"] = ann.get("grammar", []) if isinstance(ann.get("grammar"), list) else []
                continue

            # detailed: fill token-level meaning/notes
            sent_tokens = by_id[sid].get("tokens")
            if not isinstance(sent_tokens, list) or not sent_tokens:
                continue

            token_notes = ann.get("tokens")
            if isinstance(token_notes, list):
                for note in token_notes:
                    if not isinstance(note, dict):
                        continue
                    token_index = note.get("token_index")
                    if not isinstance(token_index, int) or token_index <= 0 or token_index > len(sent_tokens):
                        continue
                    target = sent_tokens[token_index - 1]
                    if not isinstance(target, dict):
                        continue
                    if "reading_kana" in note and isinstance(note.get("reading_kana"), str):
                        target["reading_kana"] = note["reading_kana"]
                    if "meaning_zh" in note and isinstance(note.get("meaning_zh"), str):
                        target["meaning_zh"] = note["meaning_zh"]
                    target["grammar_note"] = note.get("grammar_note") if note.get("grammar_note") is None else str(note.get("grammar_note"))

            by_id[sid]["grammar"] = ann.get("grammar", []) if isinstance(ann.get("grammar"), list) else []

        idx += len(batch_ids)
        print(f"Annotated {idx}/{total} sentences", file=sys.stderr)

    _write_json(out_path, data)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Annotate sentence JSON using Codex CLI (detailed per-token or summary)."
    )
    parser.add_argument("in_json", type=Path, help="Input sentence JSON (from extract_epub_sentences.py)")
    parser.add_argument("--out", type=Path, default=None, help="Output JSON path (default: overwrite input)")
    parser.add_argument("--start-id", type=int, default=1, help="Start sentence id (default: 1)")
    parser.add_argument("--count", type=int, default=50, help="How many sentences to annotate (default: 50)")
    parser.add_argument("--batch-size", type=int, default=1, help="How many sentences per Codex call (default: 1)")
    parser.add_argument("--only-missing", action="store_true", help="Only annotate sentences where zh is empty/null")
    parser.add_argument("--mode", choices=["detailed", "summary"], default="detailed")
    parser.add_argument("--include-spine-regex", type=str, default=None, help="Only annotate matching spine_path")
    parser.add_argument("--exclude-spine-regex", type=str, default=None, help="Skip matching spine_path")
    parser.add_argument(
        "--skip-copyright",
        action="store_true",
        help="Convenience: skip typical copyright/colophon pages (caution/colophon/bookwalker)",
    )
    parser.add_argument("--model", type=str, default=None, help="Codex model override (optional)")
    parser.add_argument(
        "--cd",
        type=Path,
        default=DEFAULT_CODEX_CWD,
        help=f"Directory for Codex exec -C (default: {DEFAULT_CODEX_CWD})",
    )
    parser.add_argument(
        "--codex-config-file",
        type=Path,
        default=None,
        help="File with Codex -c overrides (1 per line). Defaults to CODEX_CONFIG_FILE env var if set.",
    )
    parser.add_argument(
        "--codex-config",
        action="append",
        default=[],
        help="Extra Codex config override, repeatable (key=value).",
    )
    return parser


def main() -> int:
    _load_dotenv_if_present()

    parser = build_arg_parser()
    args = parser.parse_args()

    in_path: Path = args.in_json
    if not in_path.exists():
        raise SystemExit(f"Not found: {in_path}")

    out_path = args.out or in_path
    if args.mode == "summary":
        schema_name = "codex_sentence_batch_annotation_v1.schema.json"
    else:
        schema_name = "codex_sentence_batch_annotation_detailed_v1.schema.json"
    schema_path = Path(__file__).parent / "schemas" / schema_name
    if not schema_path.exists():
        raise SystemExit(f"Missing schema: {schema_path}")

    config_file = args.codex_config_file
    if config_file is None:
        env_path = os.environ.get("CODEX_CONFIG_FILE")
        if env_path:
            config_file = Path(env_path)
        elif (_repo_root() / "codex.crs.config.txt").exists():
            config_file = Path("codex.crs.config.txt")
    if config_file is not None and not config_file.is_absolute():
        config_file = _repo_root() / config_file
    config_args = _collect_codex_config_args(config_file, list(args.codex_config or []))

    exclude_spine = args.exclude_spine_regex
    if bool(args.skip_copyright):
        default_exclude = r"(xhtml/p-caution\\.xhtml|xhtml/p-colophon2?\\.xhtml|xhtml/p-bookwalker\\.xhtml)"
        exclude_spine = f"(?:{exclude_spine})|(?:{default_exclude})" if exclude_spine else default_exclude

    annotate_file(
        in_path,
        out_path,
        start_id=int(args.start_id),
        count=int(args.count),
        batch_size=max(1, int(args.batch_size)),
        only_missing=bool(args.only_missing),
        include_spine=args.include_spine_regex,
        exclude_spine=exclude_spine,
        mode=str(args.mode),
        schema_path=schema_path,
        model=args.model,
        cd=args.cd,
        config_args=config_args,
    )
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
