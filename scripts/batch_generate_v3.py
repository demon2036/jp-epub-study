#!/usr/bin/env python3
"""批量生成日语汉字详解 - 结构化 JSON 版本"""
import asyncio
from dataclasses import dataclass
import json
import os
import signal
import shlex
import shutil
import sys
from datetime import datetime
from pathlib import Path

from kanji_memory_contract import validate_memory_payload
from kanji_pronunciation_audit import repair_memory_payload_pronunciations
from render_kanji import render

try:
    from json_repair import repair_json
except ImportError:  # pragma: no cover
    repair_json = None

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
REPO_ROOT = SCRIPT_DIR.parent
DB_FILE = DATA_DIR / "kanji_db_v2.json"
OLD_DB_FILE = DATA_DIR / "kanji_db.json"
JOYO_FILE = DATA_DIR / "joyo_kanji_2010.json"
KYOIKU_BY_GRADE_FILE = DATA_DIR / "kyoiku_kanji_2020_by_grade.json"
PROMPT_TEMPLATE = SCRIPT_DIR / "prompts" / "kanji_explain_json.md"
BATCH_PROMPT_TEMPLATE = SCRIPT_DIR / "prompts" / "kanji_explain_batch_json.md"
DEFAULT_CODEX_CONFIG_FILE = REPO_ROOT / "codex.cliproxy.config.txt"
DEFAULT_TIMEOUT_S = int(os.getenv("CLAUDE_TIMEOUT_S", "180"))
DEFAULT_CODEX_TIMEOUT_S = int(os.getenv("CODEX_TIMEOUT_S", "3600"))
DEFAULT_BACKEND = os.getenv("KANJI_BACKEND") or os.getenv("AGENT_TYPE", "claude")
DEFAULT_CODEX_BATCH_SIZE = int(os.getenv("CODEX_BATCH_SIZE", "10"))
CODEX_BIN = os.getenv("CODEX_BIN", "codex")
VALID_BACKENDS = {"claude", "codex"}
CODEX_MULTI_CONFIGS_ENV = "CODEX_MULTI_CONFIGS_JSON"
DEFAULT_CODEX_MODEL = os.getenv("CODEX_MODEL") or "gpt-5.5"
DEFAULT_CODEX_REASONING_EFFORT = os.getenv("CODEX_REASONING_EFFORT") or "xhigh"
CODEX_RUNTIME_PROVIDER = "crs"
CODEX_RUNTIME_PROVIDER_ENV_KEY = "CRS_OAI_KEY"
DEFAULT_CODEX_CRS_BASE_URL = os.getenv("CODEX_CRS_BASE_URL", "http://127.0.0.1:18325/v1")
DEFAULT_CODEX_MODEL_INSTRUCTIONS_FILE = os.getenv(
    "CODEX_MODEL_INSTRUCTIONS_FILE",
    "scripts/prompts/codex_kanji_batch_instructions.md",
)


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


DB_FILE = _env_path("KANJI_DB_FILE", DB_FILE)


@dataclass(frozen=True)
class CodexRuntimeConfig:
    name: str
    base_url: str
    api_key: str


def init_db() -> dict:
    """从旧数据库初始化新数据库结构"""
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text(encoding="utf-8"))

    source = os.getenv("KANJI_SOURCE", "").strip().lower()
    if source:
        source_kanji = _load_source_kanji(source)
        return _build_initial_db_from_kanji_list(
            source_kanji,
            source=source,
            grade_lookup=_load_kyoiku_grade_lookup(),
            source_limit=int(os.getenv("KANJI_SOURCE_LIMIT", "0") or "0"),
        )

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


def _load_kyoiku_grade_lookup() -> dict[str, int]:
    if not KYOIKU_BY_GRADE_FILE.exists():
        return {}
    payload = json.loads(KYOIKU_BY_GRADE_FILE.read_text(encoding="utf-8"))
    lookup: dict[str, int] = {}
    for grade, chars in (payload.get("by_grade") or {}).items():
        for kanji in chars:
            lookup[str(kanji)] = int(grade)
    return lookup


def _load_source_kanji(source: str) -> list[str]:
    source = source.lower()
    if source in {"joyo", "joyo_2010", "常用"}:
        payload = json.loads(JOYO_FILE.read_text(encoding="utf-8"))
        return [str(item) for item in payload["kanji"]]
    if source in {"kyoiku", "kyoiku_2020", "教育"}:
        payload = json.loads(KYOIKU_BY_GRADE_FILE.read_text(encoding="utf-8"))
        chars: list[str] = []
        for grade in sorted(payload["by_grade"], key=lambda item: int(item)):
            chars.extend(str(item) for item in payload["by_grade"][grade])
        return chars
    raise ValueError(f"unknown KANJI_SOURCE={source}")


def _build_initial_db_from_kanji_list(
    kanji_list: list[str],
    *,
    source: str,
    grade_lookup: dict[str, int] | None = None,
    source_limit: int = 0,
) -> dict:
    grade_lookup = grade_lookup or {}
    selected = kanji_list[:source_limit] if source_limit > 0 else list(kanji_list)
    return {
        "meta": {
            "version": 2,
            "total": len(selected),
            "completed": 0,
            "last_updated": datetime.now().isoformat(),
            "source": source,
            "source_limit": source_limit,
        },
        "kanji": {
            kanji: {
                "grade": grade_lookup.get(kanji, 7),
                "status": "pending",
                "data": None,
            }
            for kanji in selected
        },
    }


def save_db(db: dict):
    db["meta"]["last_updated"] = datetime.now().isoformat()
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def load_prompt(kanji: str) -> str:
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("{kanji}", kanji)


def load_batch_prompt(kanji_list: list[str]) -> str:
    template = BATCH_PROMPT_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("{kanji_json}", json.dumps({"kanji": kanji_list}, ensure_ascii=False))


def _load_codex_base_args() -> list[str]:
    config_lines = _read_codex_config_lines()

    json_args = os.getenv("CODEX_ARGS_JSON")
    if json_args:
        try:
            parsed = json.loads(json_args)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list) and all(isinstance(arg, str) for arg in parsed):
            return [*config_lines, *parsed]
        return config_lines

    arg_str = os.getenv("CODEX_ARGS")
    if not arg_str:
        return config_lines
    try:
        return [*config_lines, *shlex.split(arg_str, posix=os.name != "nt")]
    except ValueError:
        return config_lines


def _resolve_codex_config_file() -> Path | None:
    env_path = os.getenv("CODEX_CONFIG_FILE")
    if env_path:
        candidate = Path(env_path)
        return candidate if candidate.is_absolute() else (REPO_ROOT / candidate).resolve()
    return DEFAULT_CODEX_CONFIG_FILE if DEFAULT_CODEX_CONFIG_FILE.exists() else None


def _read_codex_config_lines() -> list[str]:
    config_file = _resolve_codex_config_file()
    if config_file is None or not config_file.exists():
        return []

    args: list[str] = []
    for raw in config_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        args.extend(["-c", line])
    return args


def _has_approval_override(args: list[str]) -> bool:
    return (
        "--yolo" in args
        or "--bypass-approvals-and-sandbox" in args
        or "-a" in args
        or "--ask-for-approval" in args
    )


def _first_nonempty_string(mapping: dict, *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
    return ""


def _load_codex_runtime_configs() -> list[CodexRuntimeConfig]:
    raw = os.getenv(CODEX_MULTI_CONFIGS_ENV, "").strip()
    if not raw:
        return []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{CODEX_MULTI_CONFIGS_ENV} is not valid JSON") from exc

    if not isinstance(parsed, list):
        raise ValueError(f"{CODEX_MULTI_CONFIGS_ENV} must be a JSON array")

    configs: list[CodexRuntimeConfig] = []
    for idx, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{CODEX_MULTI_CONFIGS_ENV}[{idx - 1}] must be an object")

        name = _first_nonempty_string(item, "name") or f"codex-{idx}"
        base_url = _first_nonempty_string(item, "base_url", "url")
        if not base_url:
            raise ValueError(f"{CODEX_MULTI_CONFIGS_ENV}[{idx - 1}] missing base_url")

        api_key = _first_nonempty_string(item, "api_key", "key")
        if not api_key:
            api_key_env = _first_nonempty_string(item, "api_key_env", "key_env")
            if not api_key_env:
                raise ValueError(
                    f"{CODEX_MULTI_CONFIGS_ENV}[{idx - 1}] missing api_key/api_key_env"
                )
            api_key = os.getenv(api_key_env, "").strip()
            if not api_key:
                raise ValueError(
                    f"{CODEX_MULTI_CONFIGS_ENV}[{idx - 1}] env var {api_key_env} is empty"
                )

        configs.append(CodexRuntimeConfig(name=name, base_url=base_url, api_key=api_key))
    return configs


def _default_codex_runtime_config() -> CodexRuntimeConfig | None:
    configs = _load_codex_runtime_configs()
    if configs:
        return configs[0]
    api_key = os.getenv(CODEX_RUNTIME_PROVIDER_ENV_KEY, "").strip()
    if not api_key:
        return None
    return CodexRuntimeConfig(
        name=CODEX_RUNTIME_PROVIDER,
        base_url=os.getenv("CODEX_CRS_BASE_URL", DEFAULT_CODEX_CRS_BASE_URL),
        api_key=api_key,
    )


def _build_runtime_codex_config_lines(runtime_config: CodexRuntimeConfig) -> list[str]:
    lines = [
        f'model_provider="{CODEX_RUNTIME_PROVIDER}"',
        f'model="{DEFAULT_CODEX_MODEL}"',
        f'model_reasoning_effort="{DEFAULT_CODEX_REASONING_EFFORT}"',
        'model_reasoning_summary="auto"',
        "show_raw_agent_reasoning=true",
        "disable_response_storage=true",
        'preferred_auth_method="apikey"',
        f'model_providers.{CODEX_RUNTIME_PROVIDER}.name="{CODEX_RUNTIME_PROVIDER}"',
        f'model_providers.{CODEX_RUNTIME_PROVIDER}.base_url="{runtime_config.base_url}"',
        f'model_providers.{CODEX_RUNTIME_PROVIDER}.wire_api="responses"',
        f'model_providers.{CODEX_RUNTIME_PROVIDER}.requires_openai_auth=false',
        f'model_providers.{CODEX_RUNTIME_PROVIDER}.env_key="{CODEX_RUNTIME_PROVIDER_ENV_KEY}"',
        f"model_providers.{CODEX_RUNTIME_PROVIDER}.supports_websockets=true",
        f"model_providers.{CODEX_RUNTIME_PROVIDER}.websocket_connect_timeout_ms=15000",
    ]
    if DEFAULT_CODEX_MODEL_INSTRUCTIONS_FILE:
        lines.append(f'model_instructions_file="{DEFAULT_CODEX_MODEL_INSTRUCTIONS_FILE}"')
    return lines


def _build_codex_env(runtime_config: CodexRuntimeConfig | None) -> dict[str, str] | None:
    if runtime_config is None:
        return None
    env = os.environ.copy()
    env[CODEX_RUNTIME_PROVIDER_ENV_KEY] = runtime_config.api_key
    return env


def _build_codex_cmd(prompt: str, runtime_config: CodexRuntimeConfig | None = None) -> list[str]:
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
    if runtime_config is not None:
        cmd.extend(["--yolo", "exec", "--skip-git-repo-check", "--json"])
        for line in _build_runtime_codex_config_lines(runtime_config):
            cmd.extend(["-c", line])
        cmd.append(prompt)
        return cmd

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


def parse_batch_response(text: str, requested_kanji: list[str]) -> tuple[dict[str, dict], str]:
    payload = parse_json(text)
    if payload is None:
        return {}, "json_parse_failed"

    items = payload.get("items")
    if not isinstance(items, list):
        return {}, "batch_missing_items"

    requested = list(requested_kanji)
    requested_set = set(requested)
    parsed: dict[str, dict] = {}
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            return {}, f"batch_item_{idx}_not_object"
        kanji = str(item.get("kanji") or "").strip()
        data = item.get("data")
        if kanji not in requested_set:
            return {}, f"unexpected_kanji_in_batch: {kanji or '<empty>'}"
        if kanji in parsed:
            return {}, f"duplicate_kanji_in_batch: {kanji}"
        if not isinstance(data, dict):
            return {}, f"batch_item_missing_data: {kanji}"
        repair_memory_payload_pronunciations(data, kanji=kanji)
        validation_error = validate_memory_payload(data)
        if validation_error:
            return {}, f"{kanji}: {validation_error}"
        parsed[kanji] = data

    missing = [kanji for kanji in requested if kanji not in parsed]
    if missing:
        return {}, "missing_kanji_in_batch: " + "".join(missing)
    return parsed, ""


async def _call_claude(prompt: str, timeout_s: int) -> tuple[int, str, str]:
    cmd = ["claude", "-p", "--output-format", "text", "--max-turns", "3", prompt]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **_subprocess_group_kwargs(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        stdout, stderr = await _kill_timed_out_process(proc)
        return 124, stdout.decode(errors="replace"), stderr.decode(errors="replace")
    return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


def _subprocess_group_kwargs() -> dict:
    return {"start_new_session": True} if os.name != "nt" else {}


async def _kill_timed_out_process(proc: asyncio.subprocess.Process) -> tuple[bytes, bytes]:
    if proc.returncode is None:
        try:
            if os.name == "nt":
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        return await asyncio.wait_for(proc.communicate(), timeout=5)
    except asyncio.TimeoutError:
        return b"", b""


async def _call_codex(
    prompt: str,
    timeout_s: int,
    runtime_config: CodexRuntimeConfig | None = None,
) -> tuple[int, str, str]:
    effective_runtime_config = runtime_config or _default_codex_runtime_config()
    cmd = _build_codex_cmd("-", runtime_config=effective_runtime_config)
    env = _build_codex_env(effective_runtime_config)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        **_subprocess_group_kwargs(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode()),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        stdout, stderr = await _kill_timed_out_process(proc)
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


async def run_codex_once(
    kanji: str,
    timeout_s: int,
    runtime_config: CodexRuntimeConfig | None = None,
) -> tuple[dict | None, str]:
    """单次调用 codex CLI，返回 (解析结果, 错误信息)"""
    code, stdout_text, stderr_text = await _call_codex(
        load_prompt(kanji),
        timeout_s,
        runtime_config=runtime_config,
    )
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

    repair_memory_payload_pronunciations(data, kanji=kanji)
    validation_error = validate_memory_payload(data)
    if validation_error:
        return None, validation_error

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
    runtime_config: CodexRuntimeConfig | None = None,
) -> tuple[str, dict | None, str]:
    """带重试的 codex CLI 调用"""
    last_error = ""
    for attempt in range(max_retries + 1):
        data, error = await run_codex_once(
            kanji,
            timeout_s=timeout_s,
            runtime_config=runtime_config,
        )
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
    runtime_config: CodexRuntimeConfig | None = None,
) -> tuple[str, dict | None, str]:
    backend = backend.lower()
    if backend == "claude":
        return await run_claude(kanji, timeout_s=timeout_s, max_retries=max_retries)
    if backend == "codex":
        return await run_codex(
            kanji,
            timeout_s=timeout_s,
            max_retries=max_retries,
            runtime_config=runtime_config,
        )
    return kanji, None, f"unknown_backend={backend}"


async def run_codex_batch_once(
    kanji_batch: list[str],
    timeout_s: int,
    runtime_config: CodexRuntimeConfig | None = None,
) -> tuple[dict[str, dict], str]:
    code, stdout_text, stderr_text = await _call_codex(
        load_batch_prompt(kanji_batch),
        timeout_s,
        runtime_config=runtime_config,
    )
    if code == 124:
        return {}, f"timeout_after={timeout_s}s"
    if code != 0:
        stderr_tail = stderr_text[-200:].replace("\n", "\\n")
        return {}, f"exit_code={code}, stderr_tail={stderr_tail}"

    message = _extract_codex_agent_message(stdout_text)
    if not message:
        tail = stdout_text[-300:].replace("\n", "\\n")
        return {}, f"codex_no_agent_message, len={len(stdout_text)}, tail={tail}"
    return parse_batch_response(message, kanji_batch)


async def run_codex_batch(
    kanji_batch: list[str],
    timeout_s: int,
    max_retries: int = 2,
    runtime_config: CodexRuntimeConfig | None = None,
) -> tuple[dict[str, dict], str]:
    last_error = ""
    for attempt in range(max_retries + 1):
        parsed, error = await run_codex_batch_once(
            kanji_batch,
            timeout_s=timeout_s,
            runtime_config=runtime_config,
        )
        if parsed:
            return parsed, ""
        last_error = error
        if attempt < max_retries:
            label = "".join(kanji_batch)
            print(f"  [批量重试 {attempt+1}/{max_retries}] {label}: {error[:80]}", file=sys.stderr)
            await asyncio.sleep(1)
    return {}, last_error


def _chunked(items: list[str], size: int) -> list[list[str]]:
    if size <= 1:
        return [[item] for item in items]
    return [items[idx : idx + size] for idx in range(0, len(items), size)]


def _allocate_codex_worker_counts(concurrency: int, config_count: int) -> list[int]:
    if config_count <= 0:
        return []
    base, extra = divmod(max(0, concurrency), config_count)
    return [base + (1 if idx < extra else 0) for idx in range(config_count)]


async def batch_generate(
    concurrency: int = 3,
    limit: int = 0,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    backend: str = DEFAULT_BACKEND,
    include_failed: bool = False,
    batch_size: int = 1,
):
    """并发生成，写入 JSON 数据库"""
    backend = backend.lower()
    db = init_db()
    pending_sorted = _select_kanji_queue(db, include_failed=include_failed)
    if limit > 0:
        pending_sorted = pending_sorted[:limit]

    if not pending_sorted:
        print("所有汉字已完成！", file=sys.stderr)
        return

    total = len(pending_sorted)
    lock = asyncio.Lock()
    done = [0]

    async def persist_result(kanji: str, data: dict | None, error: str):
        async with lock:
            if data:
                was_completed = db["kanji"][kanji]["status"] == "completed"
                db["kanji"][kanji]["data"] = data
                db["kanji"][kanji]["status"] = "completed"
                db["kanji"][kanji].pop("error", None)
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

    async def process(kanji: str, idx: int):
        print(f"[{idx}/{total}] 生成中: {kanji}", file=sys.stderr)
        _, data, error = await run_backend(backend, kanji, timeout_s=timeout_s)
        await persist_result(kanji, data, error)

    async def persist_batch_result(kanji_batch: list[str], data_by_kanji: dict[str, dict], error: str):
        if data_by_kanji:
            for kanji in kanji_batch:
                await persist_result(kanji, data_by_kanji.get(kanji), "")
            return
        for kanji in kanji_batch:
            await persist_result(kanji, None, error)

    if backend == "codex" and batch_size > 1:
        batches = _chunked(pending_sorted, batch_size)
        codex_runtime_configs = _load_codex_runtime_configs()
        if codex_runtime_configs:
            worker_counts = _allocate_codex_worker_counts(concurrency, len(codex_runtime_configs))
            distribution = ", ".join(
                f"{cfg.name}={count}" for cfg, count in zip(codex_runtime_configs, worker_counts)
            )
            print(
                f"待生成: {total} 个汉字，批大小: {batch_size}, 批数: {len(batches)}, "
                f"并发: {concurrency}, backend: {backend}, 配置分配: {distribution}",
                file=sys.stderr,
            )
            queue: asyncio.Queue[tuple[list[str], int]] = asyncio.Queue()
            for i, kanji_batch in enumerate(batches, start=1):
                queue.put_nowait((kanji_batch, i))

            async def batch_worker(runtime_config: CodexRuntimeConfig):
                while True:
                    try:
                        kanji_batch, idx = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    label = "".join(kanji_batch)
                    print(
                        f"[批 {idx}/{len(batches)}] 生成中: {label} @ {runtime_config.name}",
                        file=sys.stderr,
                    )
                    data_by_kanji, error = await run_codex_batch(
                        kanji_batch,
                        timeout_s=timeout_s,
                        runtime_config=runtime_config,
                    )
                    await persist_batch_result(kanji_batch, data_by_kanji, error)

            tasks = [
                asyncio.create_task(batch_worker(runtime_config))
                for runtime_config, count in zip(codex_runtime_configs, worker_counts)
                for _ in range(count)
            ]
            await asyncio.gather(*tasks)
            print(f"\n完成: {db['meta']['completed']}/{db['meta']['total']}", file=sys.stderr)
            return

        print(
            f"待生成: {total} 个汉字，批大小: {batch_size}, 批数: {len(batches)}, "
            f"并发: {concurrency}, backend: {backend}",
            file=sys.stderr,
        )
        sem = asyncio.Semaphore(concurrency)

        async def process_batch_with_sem(kanji_batch: list[str], idx: int):
            async with sem:
                label = "".join(kanji_batch)
                print(f"[批 {idx}/{len(batches)}] 生成中: {label}", file=sys.stderr)
                data_by_kanji, error = await run_codex_batch(kanji_batch, timeout_s=timeout_s)
                await persist_batch_result(kanji_batch, data_by_kanji, error)

        tasks = [process_batch_with_sem(kanji_batch, i) for i, kanji_batch in enumerate(batches, start=1)]
        await asyncio.gather(*tasks)
        print(f"\n完成: {db['meta']['completed']}/{db['meta']['total']}", file=sys.stderr)
        return

    codex_runtime_configs = _load_codex_runtime_configs() if backend == "codex" else []
    if backend == "codex" and codex_runtime_configs:
        worker_counts = _allocate_codex_worker_counts(concurrency, len(codex_runtime_configs))
        distribution = ", ".join(
            f"{cfg.name}={count}" for cfg, count in zip(codex_runtime_configs, worker_counts)
        )
        print(
            f"待生成: {total} 个汉字，并发: {concurrency}, backend: {backend}, 配置分配: {distribution}",
            file=sys.stderr,
        )
        queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        for i, kanji in enumerate(pending_sorted, start=1):
            queue.put_nowait((kanji, i))

        async def worker(runtime_config: CodexRuntimeConfig):
            while True:
                try:
                    kanji, idx = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                print(f"[{idx}/{total}] 生成中: {kanji} @ {runtime_config.name}", file=sys.stderr)
                _, data, error = await run_backend(
                    backend,
                    kanji,
                    timeout_s=timeout_s,
                    runtime_config=runtime_config,
                )
                await persist_result(kanji, data, error)

        tasks = [
            asyncio.create_task(worker(runtime_config))
            for runtime_config, count in zip(codex_runtime_configs, worker_counts)
            for _ in range(count)
        ]
        await asyncio.gather(*tasks)
        print(f"\n完成: {db['meta']['completed']}/{db['meta']['total']}", file=sys.stderr)
        return

    print(f"待生成: {total} 个汉字，并发: {concurrency}, backend: {backend}", file=sys.stderr)
    sem = asyncio.Semaphore(concurrency)

    async def process_with_sem(kanji: str, idx: int):
        async with sem:
            await process(kanji, idx)

    tasks = [process_with_sem(kanji, i + 1) for i, kanji in enumerate(pending_sorted)]
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


def _pop_bool_flag(args: list[str], flag: str) -> bool:
    if flag not in args:
        return False
    args.remove(flag)
    return True


def _default_timeout_for_backend(backend: str) -> int:
    return DEFAULT_CODEX_TIMEOUT_S if backend.lower() == "codex" else DEFAULT_TIMEOUT_S


def _default_batch_size_for_backend(backend: str) -> int:
    return DEFAULT_CODEX_BATCH_SIZE if backend.lower() == "codex" else 1


def _select_kanji_queue(db: dict, *, include_failed: bool) -> list[str]:
    allowed_statuses = {"pending"}
    if include_failed:
        allowed_statuses.add("failed")
    queue = [k for k, v in db["kanji"].items() if v["status"] in allowed_statuses]
    return sorted(queue, key=lambda k: (db["kanji"][k]["grade"], k))


if __name__ == "__main__":
    argv = sys.argv[1:]
    backend = DEFAULT_BACKEND
    flag_backend = _pop_flag(argv, "--backend") or _pop_flag(argv, "-b")
    if flag_backend:
        backend = flag_backend
    backend = backend.lower()
    retry_failed = _pop_bool_flag(argv, "--retry-failed")
    flag_batch_size = _pop_flag(argv, "--batch-size")

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
        batch_size = int(flag_batch_size) if flag_batch_size else _default_batch_size_for_backend(backend)
        asyncio.run(
            batch_generate(
                concurrency,
                limit,
                timeout_s=timeout,
                backend=backend,
                include_failed=retry_failed,
                batch_size=batch_size,
            )
        )
