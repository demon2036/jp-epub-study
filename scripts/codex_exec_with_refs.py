#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

from codex_exec_support import DEFAULT_CODEX_CWD, expand_prompt_file_refs, resolve_codex_cwd


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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run codex exec from the jp repo root and inline @file references before sending the prompt."
    )
    parser.add_argument("prompt", nargs="?", help="Prompt text. Use '-' to read from stdin.")
    parser.add_argument("--cd", type=Path, default=DEFAULT_CODEX_CWD, help=f"Codex working directory (default: {DEFAULT_CODEX_CWD})")
    parser.add_argument("--model", type=str, default=None, help="Codex model override")
    parser.add_argument("--sandbox", choices=["read-only", "workspace-write", "danger-full-access"], default="read-only")
    parser.add_argument("--output-schema", type=Path, default=None, help="Optional JSON schema path")
    parser.add_argument(
        "--codex-config-file",
        type=Path,
        default=None,
        help="File with Codex -c overrides (1 per line). Defaults to CODEX_CONFIG_FILE env var or codex.crs.config.txt.",
    )
    parser.add_argument("--codex-config", action="append", default=[], help="Extra Codex config override, repeatable")
    return parser


def _resolve_config_file(path: Path | None) -> Path | None:
    if path is not None:
        return path if path.is_absolute() else (DEFAULT_CODEX_CWD / path)
    env_path = os.environ.get("CODEX_CONFIG_FILE")
    if env_path:
        env_file = Path(env_path)
        return env_file if env_file.is_absolute() else (DEFAULT_CODEX_CWD / env_file)
    fallback = DEFAULT_CODEX_CWD / "codex.crs.config.txt"
    return fallback if fallback.exists() else None


def _read_prompt(prompt_arg: str | None) -> str:
    if prompt_arg == "-" or prompt_arg is None:
        return sys.stdin.read()
    return prompt_arg


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    prompt = _read_prompt(args.prompt)
    if not prompt.strip():
        raise SystemExit("Prompt is empty")

    cd = resolve_codex_cwd(args.cd)
    expanded_prompt = expand_prompt_file_refs(prompt, cd)
    config_file = _resolve_config_file(args.codex_config_file)
    config_args = _collect_codex_config_args(config_file, list(args.codex_config or []))

    cmd = [
        "codex",
        "-a",
        "never",
        "exec",
        "--skip-git-repo-check",
        "-s",
        args.sandbox,
        "-C",
        str(cd),
        *config_args,
    ]
    if args.output_schema:
        cmd.extend(["--output-schema", str(args.output_schema)])
    if args.model:
        cmd.extend(["-m", args.model])
    cmd.append(expanded_prompt)

    completed = subprocess.run(cmd)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
