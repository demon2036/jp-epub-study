#!/usr/bin/env python3
"""
Unified launcher CLI: Launch or resume worker agent tasks.

Usage:
    python scripts/agent_launch.py --output "task_name" "your prompt"
    python scripts/agent_launch.py --resume <session_id> --output "task_name" "continue prompt"

Set AGENT_TYPE env var to switch backend (codex/claude). Default: codex
"""

import sys
import os
import json
import argparse

# Import from the agent package
from agent import launch, resume


def main():
    parser = argparse.ArgumentParser(description="启动或恢复 Worker Agent")
    parser.add_argument("--output", "-o",
                        help="输出文件名（不含.md后缀），Worker 会将回答写入 answers/{output}.md")
    parser.add_argument("--sop", "-s",
                        help="SOP 文件名（不含.md后缀），Worker 会将 SOP 写入 sop/{sop}.md")
    parser.add_argument("--resume", "-r", metavar="SESSION_ID",
                        help="恢复指定 session")
    parser.add_argument("prompt", nargs="?", help="任务 prompt")

    args = parser.parse_args()

    if not args.prompt:
        parser.print_help()
        print(f'\nSet AGENT_TYPE env var to switch backend (current: {os.environ.get("AGENT_TYPE", "codex")})')
        sys.exit(1)

    if args.resume:
        result = resume(args.resume, args.prompt, args.output, args.sop)
    else:
        result = launch(args.prompt, args.output, args.sop)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
