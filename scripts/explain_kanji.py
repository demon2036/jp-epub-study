#!/usr/bin/env python3
"""
日语词汇/汉字详解生成器 - 支持 codex/claude CLI

用法:
    python scripts/explain_kanji.py 日
    python scripts/explain_kanji.py 雛祭り --backend claude
    python scripts/explain_kanji.py hinamatsuri -b claude
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROMPT_TEMPLATE = SCRIPT_DIR / "prompts" / "kanji_explain.md"
DEFAULT_OUT_DIR = SCRIPT_DIR.parent / "data" / "kanji_explanations"


def load_prompt(word: str) -> str:
    """加载并填充 prompt 模板"""
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("{kanji}", word)


def run_cli(prompt: str, backend: str, model: str | None) -> str:
    """统一的 CLI 调用接口"""
    if backend == "codex":
        return _run_codex(prompt, model)
    elif backend == "claude":
        return _run_claude(prompt, model)
    else:
        raise ValueError(f"未知后端: {backend}")


def _run_codex(prompt: str, model: str | None) -> str:
    """调用 codex CLI"""
    cmd = ["codex", "-a", "never", "exec", "-s", "read-only", "--skip-git-repo-check", "--json"]
    if model:
        cmd.extend(["-m", model])
    cmd.append(prompt)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"codex 执行失败:\n{result.stderr}")

    # 从 JSON 流中提取最后的 agent_message
    for line in reversed(result.stdout.strip().splitlines()):
        try:
            event = json.loads(line)
            if event.get("type") == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message" and item.get("text"):
                    return item["text"]
        except json.JSONDecodeError:
            continue
    raise RuntimeError("codex 输出中未找到有效响应")


def _run_claude(prompt: str, model: str | None) -> str:
    """调用 claude CLI"""
    cmd = ["claude", "-p", "--output-format", "text", "--max-turns", "3"]
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"claude 执行失败:\n{result.stderr}")
    return result.stdout.strip()


def clean_markdown(text: str) -> str:
    """清理 AI 输出，移除可能的代码块包裹"""
    text = text.strip()
    # 移除 ```markdown ... ``` 包裹
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
            if lines and lines[0].strip().lower() in ("markdown", "md", ""):
                lines = lines[1:]
            text = "\n".join(lines)
    return text.strip()


def atomic_write(path: Path, content: str) -> None:
    """原子写入文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as f:
        f.write(content)
        tmp = Path(f.name)
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成日语词汇/汉字详解 Markdown 文件")
    parser.add_argument("word", help="词汇或汉字，如: 日, 雛祭り, hinamatsuri")
    parser.add_argument("--backend", "-b", default=os.environ.get("AGENT_TYPE", "codex"),
                        choices=["codex", "claude"], help="AI 后端 (默认: codex 或 $AGENT_TYPE)")
    parser.add_argument("--model", "-m", help="指定模型")
    parser.add_argument("--out-dir", "-o", type=Path, default=DEFAULT_OUT_DIR,
                        help=f"输出目录 (默认: {DEFAULT_OUT_DIR})")
    parser.add_argument("--resume", "-r", action="store_true",
                        help="如果输出文件已存在则跳过")
    args = parser.parse_args(argv)

    word = args.word.strip()
    if not word:
        print("错误: 词汇不能为空", file=sys.stderr)
        return 1

    # 输出路径: data/kanji_explanations/{word}.md
    out_path = args.out_dir / f"{word}.md"

    if args.resume and out_path.exists():
        print(f"跳过 (已存在): {out_path}", file=sys.stderr)
        return 0

    print(f"生成中: {word} (后端={args.backend})...", file=sys.stderr)

    prompt = load_prompt(word)
    response = run_cli(prompt, args.backend, args.model)
    content = clean_markdown(response)

    atomic_write(out_path, content + "\n")
    print(f"已保存: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
