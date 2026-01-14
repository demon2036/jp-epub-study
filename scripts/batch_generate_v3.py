#!/usr/bin/env python3
"""批量生成日语汉字详解 - 结构化 JSON 版本"""
import asyncio
import json
import os
import shlex
import shutil
import sys
from datetime import datetime
from pathlib import Path

from render_kanji import render

try:
    from json_repair import repair_json
except ImportError:  # pragma: no cover
    repair_json = None

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
DB_FILE = DATA_DIR / "kanji_db_v2.json"
OLD_DB_FILE = DATA_DIR / "kanji_db.json"
PROMPT_TEMPLATE = SCRIPT_DIR / "prompts" / "kanji_explain_json.md"
DEFAULT_TIMEOUT_S = int(os.getenv("CLAUDE_TIMEOUT_S", "180"))
DEFAULT_CODEX_TIMEOUT_S = int(os.getenv("CODEX_TIMEOUT_S", str(DEFAULT_TIMEOUT_S)))
DEFAULT_BACKEND = os.getenv("KANJI_BACKEND") or os.getenv("AGENT_TYPE", "claude")
CODEX_BIN = os.getenv("CODEX_BIN", "codex")
VALID_BACKENDS = {"claude", "codex"}


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


def _load_codex_base_args() -> list[str]:
    json_args = os.getenv("CODEX_ARGS_JSON")
    if json_args:
        try:
            parsed = json.loads(json_args)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list) and all(isinstance(arg, str) for arg in parsed):
            return parsed
        return []

    arg_str = os.getenv("CODEX_ARGS")
    if not arg_str:
        return []
    try:
        return shlex.split(arg_str, posix=os.name != "nt")
    except ValueError:
        return []


def _has_approval_override(args: list[str]) -> bool:
    return (
        "--yolo" in args
        or "--bypass-approvals-and-sandbox" in args
        or "-a" in args
        or "--ask-for-approval" in args
    )


def _build_codex_cmd(prompt: str) -> list[str]:
    base_cmd = [CODEX_BIN]
    resolved = shutil.which(CODEX_BIN)
    if not resolved and os.name == "nt" and not CODEX_BIN.lower().endswith(".ps1"):
        resolved = shutil.which(f"{CODEX_BIN}.ps1")
    if resolved:
        if os.name == "nt":
            lower = resolved.lower()
            if lower.endswith(".ps1"):
                base_cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", resolved]
            elif lower.endswith(".cmd") or lower.endswith(".bat"):
                base_cmd = ["cmd.exe", "/c", resolved]
            else:
                base_cmd = [resolved]
        else:
            base_cmd = [resolved]

    cmd = base_cmd
    base_args = _load_codex_base_args()
    cmd.extend(base_args)
    if not _has_approval_override(base_args):
        cmd.extend(["-a", "never"])
    cmd.extend(["exec", "-s", "read-only", "--skip-git-repo-check", "--json"])
    model = os.getenv("CODEX_MODEL")
    if model:
        cmd.extend(["-m", model])
    cmd.append(prompt)
    return cmd


def _extract_codex_agent_message(text: str) -> str | None:
    last_text = None
    for line in text.splitlines():
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
                last_text = item["text"]
        elif event.get("type") == "response.completed":
            response = event.get("response", {})
            if response.get("output_text"):
                last_text = response["output_text"]
    return last_text


def _escape_unescaped_control_chars_in_strings(text: str) -> str:
    """修复字符串内未转义的换行/tab 等，减少 JSON 解析失败"""
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
                continue
            if ch == "\\":
                out.append(ch)
                escaped = True
                continue
            if ch == "\"":
                out.append(ch)
                in_string = False
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            out.append(ch)
        else:
            if ch == "\"":
                out.append(ch)
                in_string = True
            else:
                out.append(ch)
    return "".join(out)


def _extract_fenced_code_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("```"):
            j = i + 1
            while j < len(lines) and lines[j].strip() != "```":
                j += 1
            if j < len(lines):
                content = lines[i + 1 : j]
                if content and content[0].strip().lower() in ("json", ""):
                    content = content[1:]
                blocks.append("\n".join(content).strip())
                i = j + 1
                continue
        i += 1
    return blocks


def _extract_braced_json(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1].strip()


def parse_json(text: str) -> dict | None:
    """从响应中提取 JSON（兼容前后文本/markdown code fence/未转义换行）"""
    text = text.strip()
    if not text:
        return None

    candidates = [text]
    candidates.extend(_extract_fenced_code_blocks(text))
    braced = _extract_braced_json(text)
    if braced:
        candidates.append(braced)

    decoder = json.JSONDecoder()
    for cand in candidates:
        cand = cand.strip()
        if not cand:
            continue
        for attempt in (cand, _escape_unescaped_control_chars_in_strings(cand)):
            try:
                obj, _ = decoder.raw_decode(attempt)
            except json.JSONDecodeError:
                if repair_json:
                    try:
                        repaired = repair_json(attempt, return_objects=True)
                    except Exception:
                        continue
                    if isinstance(repaired, dict):
                        return repaired
                continue
            if isinstance(obj, dict):
                return obj
    return None


async def _call_claude(prompt: str, timeout_s: int) -> tuple[int, str, str]:
    cmd = ["claude", "-p", "--output-format", "text", "--max-turns", "3", prompt]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        stdout, stderr = await proc.communicate()
        return 124, stdout.decode(errors="replace"), stderr.decode(errors="replace")
    return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def _call_codex(prompt: str, timeout_s: int) -> tuple[int, str, str]:
    cmd = _build_codex_cmd("-")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode()),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        proc.kill()
        stdout, stderr = await proc.communicate()
        return 124, stdout.decode(errors="replace"), stderr.decode(errors="replace")
    return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def run_claude_once(kanji: str, timeout_s: int) -> tuple[dict | None, str]:
    """单次调用 claude CLI，返回 (解析结果, 错误信息)"""
    code, stdout_text, stderr_text = await _call_claude(load_prompt(kanji), timeout_s)
    if code == 124:
        return None, f"timeout_after={timeout_s}s"
    if code != 0:
        stderr_tail = stderr_text[-200:].replace("\n", "\\n")
        return None, f"exit_code={code}, stderr_tail={stderr_tail}"

    data = parse_json(stdout_text)
    if data is None:
        tail = stdout_text[-300:].replace("\n", "\\n")
        return None, f"json_parse_failed, len={len(stdout_text)}, tail={tail}"

    return data, ""


async def run_codex_once(kanji: str, timeout_s: int) -> tuple[dict | None, str]:
    """单次调用 codex CLI，返回 (解析结果, 错误信息)"""
    code, stdout_text, stderr_text = await _call_codex(load_prompt(kanji), timeout_s)
    if code == 124:
        return None, f"timeout_after={timeout_s}s"
    if code != 0:
        stderr_tail = stderr_text[-200:].replace("\n", "\\n")
        return None, f"exit_code={code}, stderr_tail={stderr_tail}"

    message = _extract_codex_agent_message(stdout_text)
    if not message:
        tail = stdout_text[-300:].replace("\n", "\\n")
        return None, f"codex_no_agent_message, len={len(stdout_text)}, tail={tail}"

    data = parse_json(message)
    if data is None:
        tail = message[-300:].replace("\n", "\\n")
        return None, f"json_parse_failed, len={len(message)}, tail={tail}"

    return data, ""


async def run_claude(
    kanji: str,
    timeout_s: int,
    max_retries: int = 2,
) -> tuple[str, dict | None, str]:
    """带重试的 claude CLI 调用"""
    last_error = ""
    for attempt in range(max_retries + 1):
        data, error = await run_claude_once(kanji, timeout_s=timeout_s)
        if data:
            return kanji, data, ""
        last_error = error
        if attempt < max_retries:
            print(f"  [重试 {attempt+1}/{max_retries}] {kanji}: {error[:80]}", file=sys.stderr)
            await asyncio.sleep(1)  # 短暂等待后重试
    return kanji, None, last_error


async def run_codex(
    kanji: str,
    timeout_s: int,
    max_retries: int = 2,
) -> tuple[str, dict | None, str]:
    """带重试的 codex CLI 调用"""
    last_error = ""
    for attempt in range(max_retries + 1):
        data, error = await run_codex_once(kanji, timeout_s=timeout_s)
        if data:
            return kanji, data, ""
        last_error = error
        if attempt < max_retries:
            print(f"  [重试 {attempt+1}/{max_retries}] {kanji}: {error[:80]}", file=sys.stderr)
            await asyncio.sleep(1)  # 短暂等待后重试
    return kanji, None, last_error


async def run_backend(
    backend: str,
    kanji: str,
    timeout_s: int,
    max_retries: int = 2,
) -> tuple[str, dict | None, str]:
    backend = backend.lower()
    if backend == "claude":
        return await run_claude(kanji, timeout_s=timeout_s, max_retries=max_retries)
    if backend == "codex":
        return await run_codex(kanji, timeout_s=timeout_s, max_retries=max_retries)
    return kanji, None, f"unknown_backend={backend}"


async def batch_generate(
    concurrency: int = 3,
    limit: int = 0,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    backend: str = DEFAULT_BACKEND,
):
    """并发生成，写入 JSON 数据库"""
    backend = backend.lower()
    db = init_db()
    pending = [k for k, v in db["kanji"].items() if v["status"] == "pending"]
    pending_sorted = sorted(pending, key=lambda k: (db["kanji"][k]["grade"], k))
    if limit > 0:
        pending_sorted = pending_sorted[:limit]

    if not pending_sorted:
        print("所有汉字已完成！", file=sys.stderr)
        return

    total = len(pending_sorted)
    print(f"待生成: {total} 个汉字，并发: {concurrency}, backend: {backend}", file=sys.stderr)
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    done = [0]

    async def process(kanji: str, idx: int):
        async with sem:
            print(f"[{idx}/{total}] 生成中: {kanji}", file=sys.stderr)        
            _, data, error = await run_backend(backend, kanji, timeout_s=timeout_s)
            async with lock:
                if data:
                    was_completed = db["kanji"][kanji]["status"] == "completed"
                    db["kanji"][kanji]["data"] = data
                    db["kanji"][kanji]["status"] = "completed"
                    if not was_completed:
                        db["meta"]["completed"] += 1
                    done[0] += 1
                    save_db(db)
                    print(f"[{done[0]}/{total}] 完成: {kanji}", file=sys.stderr)
                else:
                    db["kanji"][kanji]["status"] = "failed"
                    db["kanji"][kanji]["error"] = error  # 保存错误信息
                    save_db(db)
                    print(f"[失败] {kanji} | {error}", file=sys.stderr)

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


def _pop_flag(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    idx = args.index(flag)
    if idx + 1 >= len(args):
        print(f"Missing value for {flag}", file=sys.stderr)
        sys.exit(2)
    value = args[idx + 1]
    del args[idx : idx + 2]
    return value


def _default_timeout_for_backend(backend: str) -> int:
    return DEFAULT_CODEX_TIMEOUT_S if backend.lower() == "codex" else DEFAULT_TIMEOUT_S


if __name__ == "__main__":
    argv = sys.argv[1:]
    backend = DEFAULT_BACKEND
    flag_backend = _pop_flag(argv, "--backend") or _pop_flag(argv, "-b")
    if flag_backend:
        backend = flag_backend
    backend = backend.lower()

    if argv and argv[0] == "render":
        render_all()
        sys.exit(0)

    if backend not in VALID_BACKENDS:
        print(f"Unknown backend: {backend}", file=sys.stderr)
        sys.exit(2)

    if len(argv) > 1 and argv[0] == "one":
        kanji = argv[1]
        timeout = int(argv[2]) if len(argv) > 2 else _default_timeout_for_backend(backend)

        async def _one():
            db = init_db()
            if kanji not in db["kanji"]:
                print(f"Unknown kanji: {kanji}", file=sys.stderr)
                return

            print(f"[one] generating {kanji} (timeout={timeout}s, backend={backend})", file=sys.stderr)
            _, data, error = await run_backend(backend, kanji, timeout_s=timeout, max_retries=0)
            if data:
                was_completed = db["kanji"][kanji]["status"] == "completed"
                db["kanji"][kanji]["data"] = data
                db["kanji"][kanji]["status"] = "completed"
                db["kanji"][kanji].pop("error", None)
                if not was_completed:
                    db["meta"]["completed"] += 1
                save_db(db)
                print(f"[one] OK: {kanji}", file=sys.stderr)
            else:
                db["kanji"][kanji]["status"] = "failed"
                db["kanji"][kanji]["error"] = error
                save_db(db)
                print(f"[one] FAIL: {kanji} | {error}", file=sys.stderr)

        asyncio.run(_one())
    else:
        concurrency = int(argv[0]) if len(argv) > 0 else 3
        limit = int(argv[1]) if len(argv) > 1 else 0
        timeout = int(argv[2]) if len(argv) > 2 else _default_timeout_for_backend(backend)
        asyncio.run(batch_generate(concurrency, limit, timeout_s=timeout, backend=backend))
