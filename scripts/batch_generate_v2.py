#!/usr/bin/env python3
"""批量生成日语汉字详解 - 写入JSON数据库，支持断点续传"""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
DB_FILE = DATA_DIR / "kanji_db.json"
PROMPT_TEMPLATE = SCRIPT_DIR / "prompts" / "kanji_explain.md"

def load_db() -> dict:
    return json.loads(DB_FILE.read_text(encoding="utf-8"))

def save_db(db: dict):
    db["meta"]["last_updated"] = datetime.now().isoformat()
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

def load_prompt(word: str) -> str:
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("{kanji}", word)

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

async def run_claude(word: str) -> tuple[str, str]:
    """异步调用 claude CLI"""
    prompt = load_prompt(word)
    cmd = ["claude", "-p", "--output-format", "text", "--max-turns", "3", prompt]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return word, ""
    return word, stdout.decode().strip()

async def batch_generate(concurrency: int = 3):
    """并发生成，写入JSON数据库"""
    db = load_db()
    pending = [k for k, v in db["kanji"].items() if v["status"] == "pending"]

    if not pending:
        print("所有汉字已完成！", file=sys.stderr)
        return

    total_pending = len(pending)
    print(f"待生成: {total_pending} 个汉字，并发: {concurrency}", file=sys.stderr)
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    completed = [0]  # 用列表以便在闭包中修改

    async def process_one(kanji: str, idx: int):
        async with sem:
            print(f"[{idx}/{total_pending}] 生成中: {kanji}", file=sys.stderr)
            _, content = await run_claude(kanji)
            async with lock:
                if content:
                    content = clean_markdown(content)
                    db["kanji"][kanji]["content"] = content
                    db["kanji"][kanji]["status"] = "completed"
                    db["meta"]["completed"] += 1
                    completed[0] += 1
                    save_db(db)
                    print(f"[{completed[0]}/{total_pending}] 完成: {kanji}", file=sys.stderr)
                else:
                    db["kanji"][kanji]["status"] = "failed"
                    save_db(db)
                    print(f"[失败] {kanji}", file=sys.stderr)

    # 按年级顺序处理
    pending_sorted = sorted(pending, key=lambda k: (db["kanji"][k]["grade"], k))

    # 真正的并发执行
    tasks = [process_one(kanji, i+1) for i, kanji in enumerate(pending_sorted)]
    await asyncio.gather(*tasks)

    print(f"\n完成: {db['meta']['completed']}/{db['meta']['total']}", file=sys.stderr)

if __name__ == "__main__":
    concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    asyncio.run(batch_generate(concurrency))
