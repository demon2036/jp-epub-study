from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CODEX_CWD = REPO_ROOT
MAX_INLINE_FILE_CHARS = 20_000
_FILE_REF_TOKEN_RE = re.compile(r"(?<!\S)@(?P<path>\S+)")
_TRAILING_PUNCTUATION = ".,:;!?)]}"


def resolve_codex_cwd(cd: Path | None = None) -> Path:
    if cd is None:
        return DEFAULT_CODEX_CWD
    return cd if cd.is_absolute() else (DEFAULT_CODEX_CWD / cd).resolve()


def _split_trailing_punctuation(token: str) -> tuple[str, str]:
    core = token
    trailing = ""
    while core and core[-1] in _TRAILING_PUNCTUATION:
        trailing = core[-1] + trailing
        core = core[:-1]
    return core, trailing


def _format_file_block(display_path: str, content: str) -> str:
    return (
        f"[Referenced file: {display_path}]\n"
        "```text\n"
        f"{content}\n"
        "```"
    )


def expand_prompt_file_refs(prompt: str, base_dir: Path | None = None) -> str:
    resolved_base = resolve_codex_cwd(base_dir)

    def replace(match: re.Match[str]) -> str:
        raw_token = match.group("path")
        raw_path, trailing = _split_trailing_punctuation(raw_token)
        candidate = Path(raw_path)
        resolved_path = candidate if candidate.is_absolute() else (resolved_base / candidate).resolve()
        if not resolved_path.is_file():
            raise FileNotFoundError(f"Referenced file not found: {raw_path} (base: {resolved_base})")

        content = resolved_path.read_text(encoding="utf-8", errors="replace")
        if len(content) > MAX_INLINE_FILE_CHARS:
            content = content[:MAX_INLINE_FILE_CHARS] + "\n... [truncated]"
        try:
            display_path = str(resolved_path.relative_to(resolved_base))
        except ValueError:
            display_path = str(resolved_path)
        return _format_file_block(display_path, content) + trailing

    return _FILE_REF_TOKEN_RE.sub(replace, prompt)
