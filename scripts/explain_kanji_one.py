#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as f:
        tmp = Path(f.name)
        f.write(content)
        f.flush()
    tmp.replace(path)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_last_agent_message(stdout: str) -> str:
    last_message = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "item.completed":
            continue
        item = event.get("item") or {}
        if item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            last_message = text
    if not last_message:
        raise RuntimeError("No agent_message found in codex --json output.")
    return last_message


def _parse_json_object(text: str) -> dict:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        obj = json.loads(text[start : end + 1])
    if not isinstance(obj, dict):
        raise RuntimeError("Agent output is not a JSON object.")
    return obj


def _build_prompt(kanji: str, grade: int) -> str:
    return (
        "你是一名日语汉字老师，请面向中文母语学习者，详细解释下面这个“单个汉字”。\n"
        "\n"
        "输出要求：\n"
        "- 只输出一个 JSON 对象，不要输出任何多余文字/markdown/代码块。\n"
        "- JSON 必须能被 json.loads 直接解析。\n"
        "- JSON 结构固定为：\n"
        '  {"kanji":"<原样汉字>","grade":<1-6整数>,"explanation":"<string>"}\n'
        "- explanation 请包含：核心含义（中文）、音读/训读、常见词汇例子（>=5个，带假名读音）、"
        "部首、笔画数、易混字对比、记忆/书写要点。\n"
        "- 为了保证 JSON 有效：explanation 里不要出现未转义的换行符；如需换行，请用 \\n 两个字符表示。\n"
        "\n"
        f"输入：kanji={kanji} grade={grade}\n"
    )


def run_codex(prompt: str, *, model: str | None, sandbox: str) -> dict:
    cmd = ["codex"]
    if model:
        cmd += ["-m", model]
    cmd += [
        "-a",
        "never",
        "exec",
        "-s",
        sandbox,
        "--skip-git-repo-check",
        "--json",
        prompt,
    ]

    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "codex exec failed\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}\n"
        )

    last_message = _extract_last_agent_message(completed.stdout)
    return _parse_json_object(last_message)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Test: launch Codex for a single kanji and save {grade: {kanji: explanation}} JSON."
    )
    parser.add_argument("kanji", help="Single kanji character, e.g. 日")
    parser.add_argument("--grade", type=int, default=1, help="Grade (1-6). Default: 1")
    parser.add_argument(
        "--out",
        default="data/kyoiku_kanji_explanations_test.json",
        help="Output JSON path (default: %(default)s).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="If output already contains this (grade, kanji), skip.",
    )
    parser.add_argument("--model", help="Optional model override for `codex -m`.")
    parser.add_argument(
        "--sandbox",
        default="read-only",
        choices=("read-only", "workspace-write", "danger-full-access"),
        help="Codex sandbox mode (default: %(default)s).",
    )
    args = parser.parse_args(argv)

    kanji = args.kanji.strip()
    if len(kanji) != 1:
        raise SystemExit("`kanji` must be exactly 1 character.")
    if not (1 <= args.grade <= 6):
        raise SystemExit("`--grade` must be in 1..6.")

    out_path = Path(args.out)
    data = _load_json(out_path)

    grade_key = str(args.grade)
    grade_bucket = data.get(grade_key)
    if grade_bucket is None:
        grade_bucket = {}
        data[grade_key] = grade_bucket
    if not isinstance(grade_bucket, dict):
        raise SystemExit(f"Invalid output JSON: expected object at grade '{grade_key}'.")

    if args.resume and kanji in grade_bucket:
        print(f"Skip (already exists): grade={args.grade} kanji={kanji}", file=sys.stderr)
        return 0

    prompt = _build_prompt(kanji, args.grade)
    result = run_codex(prompt, model=args.model, sandbox=args.sandbox)

    if result.get("kanji") != kanji:
        raise SystemExit(f"Agent returned mismatched kanji: {result.get('kanji')!r} != {kanji!r}")
    if int(result.get("grade")) != args.grade:
        raise SystemExit(f"Agent returned mismatched grade: {result.get('grade')!r} != {args.grade!r}")

    explanation = result.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        raise SystemExit("Agent returned empty or non-string explanation.")

    grade_bucket[kanji] = explanation
    _atomic_write_text(out_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote: {out_path} (grade={args.grade} kanji={kanji})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
