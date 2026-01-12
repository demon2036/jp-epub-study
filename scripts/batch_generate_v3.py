#!/usr/bin/env python3
"""批量生成日语汉字详解 - 结构化 JSON 版本"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from render_kanji import render

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
DB_FILE = DATA_DIR / "kanji_db_v2.json"
OLD_DB_FILE = DATA_DIR / "kanji_db.json"
PROMPT_TEMPLATE = SCRIPT_DIR / "prompts" / "kanji_explain_json.md"


def init_db() -> dict:
    """从旧数据库初始化新数据库结构"""
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text(encoding="utf-8"))

    old_db = json.loads(OLD_DB_FILE.read_text(encoding="utf-8"))
    new_db = {
        "meta": {
            "version": 2,
            "total": old_db["meta"]["total"],
            "completed": 0,
            "last_updated": datetime.now().isoformat()
        },
        "kanji": {}
    }
    for k, v in old_db["kanji"].items():
        new_db["kanji"][k] = {"grade": v["grade"], "status": "pending", "data": None}
    return new_db


def save_db(db: dict):
    db["meta"]["last_updated"] = datetime.now().isoformat()
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def load_prompt(kanji: str) -> str:
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("{kanji}", kanji)


def parse_json(text: str) -> dict | None:
    """从响应中提取 JSON"""
    text = text.strip()
    # 去除可能的 markdown 代码块
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
            if lines and lines[0].strip().lower() in ("json", ""):
                lines = lines[1:]
            text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


async def run_claude_once(kanji: str) -> tuple[dict | None, str]:
    """单次调用 claude CLI，返回 (解析结果, 错误信息)"""
    prompt = load_prompt(kanji)
    cmd = ["claude", "-p", "--output-format", "text", "--max-turns", "3", prompt]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    stdout_text = stdout.decode()
    stderr_text = stderr.decode()

    if proc.returncode != 0:
        return None, f"exit_code={proc.returncode}, stderr={stderr_text[:300]}"

    data = parse_json(stdout_text)
    if data is None:
        return None, f"json_parse_failed, len={len(stdout_text)}, tail={stdout_text[-200:]}"

    return data, ""


async def run_claude(kanji: str, max_retries: int = 2) -> tuple[str, dict | None, str]:
    """带重试的 claude CLI 调用"""
    last_error = ""
    for attempt in range(max_retries + 1):
        data, error = await run_claude_once(kanji)
        if data:
            return kanji, data, ""
        last_error = error
        if attempt < max_retries:
            print(f"  [重试 {attempt+1}/{max_retries}] {kanji}: {error[:80]}", file=sys.stderr)
            await asyncio.sleep(1)  # 短暂等待后重试
    return kanji, None, last_error


async def batch_generate(concurrency: int = 3, limit: int = 0):
    """并发生成，写入 JSON 数据库"""
    db = init_db()
    pending = [k for k, v in db["kanji"].items() if v["status"] == "pending"]
    if limit > 0:
        pending = pending[:limit]

    if not pending:
        print("所有汉字已完成！", file=sys.stderr)
        return

    total = len(pending)
    print(f"待生成: {total} 个汉字，并发: {concurrency}", file=sys.stderr)
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    done = [0]

    async def process(kanji: str, idx: int):
        async with sem:
            print(f"[{idx}/{total}] 生成中: {kanji}", file=sys.stderr)
            _, data, error = await run_claude(kanji)
            async with lock:
                if data:
                    db["kanji"][kanji]["data"] = data
                    db["kanji"][kanji]["status"] = "completed"
                    db["meta"]["completed"] += 1
                    done[0] += 1
                    save_db(db)
                    print(f"[{done[0]}/{total}] 完成: {kanji}", file=sys.stderr)
                else:
                    db["kanji"][kanji]["status"] = "failed"
                    db["kanji"][kanji]["error"] = error  # 保存错误信息
                    save_db(db)
                    print(f"[失败] {kanji} | {error}", file=sys.stderr)

    pending_sorted = sorted(pending, key=lambda k: (db["kanji"][k]["grade"], k))
    tasks = [process(kanji, i + 1) for i, kanji in enumerate(pending_sorted)]
    await asyncio.gather(*tasks)
    print(f"\n完成: {db['meta']['completed']}/{db['meta']['total']}", file=sys.stderr)


def render_all():
    """将所有已完成的汉字渲染为 Markdown（用于调试）"""
    db = json.loads(DB_FILE.read_text(encoding="utf-8"))
    for kanji, entry in db["kanji"].items():
        if entry["status"] == "completed" and entry["data"]:
            md = render(kanji, entry["data"])
            print(f"=== {kanji} ===")
            print(md)
            print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "render":
        render_all()
    else:
        concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 3
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        asyncio.run(batch_generate(concurrency, limit))
