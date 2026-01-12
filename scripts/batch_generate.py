#!/usr/bin/env python3
"""批量生成日语词汇详解 - 支持并发"""
import asyncio
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROMPT_TEMPLATE = SCRIPT_DIR / "prompts" / "kanji_explain.md"
OUT_DIR = SCRIPT_DIR.parent / "data" / "kanji_explanations"

def load_prompt(word: str) -> str:
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("{kanji}", word)

async def run_claude(word: str) -> tuple[str, str]:
    """异步调用 claude CLI"""
    prompt = load_prompt(word)
    cmd = ["claude", "-p", "--output-format", "text", "--max-turns", "3", prompt]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        print(f"[错误] {word}: {stderr.decode()}", file=sys.stderr)
        return word, ""

    return word, stdout.decode().strip()

def clean_markdown(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
            if lines and lines[0].strip().lower() in ("markdown", "md", ""):
                lines = lines[1:]
            text = "\n".join(lines)
    return text.strip()

async def batch_generate(words: list[str], concurrency: int = 5):
    """并发生成多个词汇的解释"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(concurrency)

    async def limited_run(word: str):
        async with sem:
            print(f"[开始] {word}", file=sys.stderr)
            word, content = await run_claude(word)
            if content:
                content = clean_markdown(content)
                out_path = OUT_DIR / f"{word}.md"
                out_path.write_text(content + "\n", encoding="utf-8")
                print(f"[完成] {word} -> {out_path}", file=sys.stderr)
            return word, bool(content)

    tasks = [limited_run(w) for w in words]
    results = await asyncio.gather(*tasks)

    success = sum(1 for _, ok in results if ok)
    print(f"\n完成: {success}/{len(words)} 个词汇", file=sys.stderr)

def make_epub():
    """生成 epub"""
    from make_epub import create_epub
    md_files = list(OUT_DIR.glob("*.md"))
    if md_files:
        output = OUT_DIR / "日语词汇详解.epub"
        create_epub(md_files, output, "日语词汇详解")

if __name__ == "__main__":
    # 小学一年级前 5 个汉字
    GRADE1_FIRST5 = ["一", "二", "三", "四", "五"]

    # 清理旧文件
    for f in OUT_DIR.glob("*.md"):
        f.unlink()

    # 并发生成
    asyncio.run(batch_generate(GRADE1_FIRST5, concurrency=5))

    # 生成 epub
    make_epub()
