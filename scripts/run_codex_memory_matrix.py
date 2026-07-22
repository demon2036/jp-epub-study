#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import markdown
from ebooklib import epub

from batch_generate_v3 import _extract_codex_agent_message, parse_json
from codex_exec_support import DEFAULT_CODEX_CWD
from kanji_memory_contract import validate_memory_payload
from render_kanji import render


REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_TEMPLATE = REPO_ROOT / "scripts" / "prompts" / "kanji_explain_json.md"
DEFAULT_SCHEMA = REPO_ROOT / "scripts" / "schemas" / "codex_kanji_memory_v1.schema.json"
DEFAULT_CONFIG_FILE = REPO_ROOT / "codex.cliproxy.config.txt"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "model_matrix"
DEFAULT_TIMEOUT_S = int(os.getenv("CODEX_TIMEOUT_S", "300"))
DEFAULT_CD = DEFAULT_CODEX_CWD
CSS = """
body { font-family: -apple-system, "PingFang SC", "Hiragino Sans", sans-serif; line-height: 1.9; color: #1f2937; padding: 1em; }
h1 { font-size: 1.8em; color: #1a365d; border-bottom: 2px solid #dbeafe; padding-bottom: 0.3em; }
h2 { font-size: 1.35em; color: #1d4ed8; margin-top: 1.5em; }
h3 { font-size: 1.15em; color: #374151; margin-top: 1.2em; }
h4 { font-size: 1.02em; color: #111827; margin-top: 1em; }
p.meta { color: #6b7280; font-size: 0.92em; }
section.variant { margin: 1.6em 0 2.2em; padding-bottom: 1.6em; border-bottom: 1px dashed #cbd5e1; }
table { border-collapse: collapse; width: 100%; margin: 0.8em 0; }
th, td { border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #eff6ff; font-weight: 600; }
blockquote { background: #f8fafc; border-left: 3px solid #60a5fa; padding: 0.7em 1em; margin: 1em 0; }
code { background: #e5e7eb; padding: 1px 4px; border-radius: 3px; }
.error { color: #991b1b; background: #fef2f2; padding: 0.8em; border-radius: 6px; }
"""


@dataclass(frozen=True)
class Variant:
    model: str
    effort: str

    @property
    def slug(self) -> str:
        return variant_slug(self.model, self.effort)

    @property
    def label(self) -> str:
        return variant_label(self.model, self.effort)


def variant_slug(model: str, effort: str) -> str:
    return f"{model}-{effort}"


def variant_label(model: str, effort: str) -> str:
    return f"{model} / {effort}"


def default_kanji_sample() -> list[str]:
    return ["並", "橋", "見", "生"]


def default_variants() -> list[Variant]:
    return [
        Variant("gpt-5.2", "xhigh"),
        Variant("gpt-5.4", "low"),
        Variant("gpt-5.4", "medium"),
        Variant("gpt-5.4", "high"),
        Variant("gpt-5.4", "xhigh"),
    ]


def filter_variants(
    variants: list[Variant],
    *,
    models: list[str] | None = None,
    efforts: list[str] | None = None,
) -> list[Variant]:
    model_filter = {item.strip() for item in (models or []) if item and item.strip()}
    effort_filter = {item.strip() for item in (efforts or []) if item and item.strip()}
    filtered = [
        item
        for item in variants
        if (not model_filter or item.model in model_filter)
        and (not effort_filter or item.effort in effort_filter)
    ]
    return filtered


def _load_dotenv_if_present() -> None:
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from scripts.dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    load_dotenv(REPO_ROOT / ".env", override=False)


def _read_config_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _load_prompt(kanji: str) -> str:
    return PROMPT_TEMPLATE.read_text(encoding="utf-8").replace("{kanji}", kanji)


def _build_codex_cmd(
    *,
    variant: Variant,
    schema_path: Path,
    config_lines: list[str],
    cd: Path,
) -> list[str]:
    cmd = [
        "codex",
        "-a",
        "never",
        "exec",
        "--json",
        "--skip-git-repo-check",
        "-s",
        "read-only",
        "--output-schema",
        str(schema_path),
        "-C",
        str(cd),
    ]
    for line in config_lines:
        cmd.extend(["-c", line])
    cmd.extend(["-c", f'model="{variant.model}"'])
    cmd.extend(["-c", f'model_reasoning_effort="{variant.effort}"'])
    cmd.append("-")
    return cmd

def _validate_memory_payload(payload: dict) -> str | None:
    return validate_memory_payload(payload)


async def _run_one(
    *,
    kanji: str,
    variant: Variant,
    schema_path: Path,
    config_lines: list[str],
    timeout_s: int,
    cd: Path,
) -> dict:
    prompt = _load_prompt(kanji)
    cmd = _build_codex_cmd(variant=variant, schema_path=schema_path, config_lines=config_lines, cd=cd)
    start = asyncio.get_running_loop().time()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(input=prompt.encode()), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        stdout, stderr = await proc.communicate()
        elapsed = asyncio.get_running_loop().time() - start
        return {
            "kanji": kanji,
            "variant": asdict(variant),
            "status": "timeout",
            "elapsed_s": round(elapsed, 2),
            "error": f"timeout_after={timeout_s}s",
            "stderr": stderr.decode(errors="replace"),
            "prompt": prompt,
        }

    elapsed = asyncio.get_running_loop().time() - start
    stdout_text = stdout.decode(errors="replace")
    stderr_text = stderr.decode(errors="replace")
    if proc.returncode != 0:
        return {
            "kanji": kanji,
            "variant": asdict(variant),
            "status": "failed",
            "elapsed_s": round(elapsed, 2),
            "error": f"exit_code={proc.returncode}",
            "stdout": stdout_text,
            "stderr": stderr_text,
            "prompt": prompt,
        }

    message = _extract_codex_agent_message(stdout_text)
    if not message:
        return {
            "kanji": kanji,
            "variant": asdict(variant),
            "status": "failed",
            "elapsed_s": round(elapsed, 2),
            "error": "missing_agent_message",
            "stdout": stdout_text,
            "stderr": stderr_text,
            "prompt": prompt,
        }

    data = parse_json(message)
    if data is None:
        return {
            "kanji": kanji,
            "variant": asdict(variant),
            "status": "failed",
            "elapsed_s": round(elapsed, 2),
            "error": "json_parse_failed",
            "stdout": stdout_text,
            "stderr": stderr_text,
            "raw_text": message,
            "prompt": prompt,
        }

    validation_error = _validate_memory_payload(data)
    if validation_error:
        return {
            "kanji": kanji,
            "variant": asdict(variant),
            "status": "failed",
            "elapsed_s": round(elapsed, 2),
            "error": validation_error,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "raw_text": message,
            "prompt": prompt,
        }

    return {
        "kanji": kanji,
        "variant": asdict(variant),
        "status": "completed",
        "elapsed_s": round(elapsed, 2),
        "data": data,
        "stderr": stderr_text,
        "prompt": prompt,
    }


async def run_matrix(
    *,
    kanji_list: list[str],
    variants: list[Variant],
    schema_path: Path,
    config_lines: list[str],
    timeout_s: int,
    concurrency: int,
    cd: Path,
    on_result: Callable[[dict, int, int, Counter[str]], None] | None = None,
) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    results: list[dict] = []
    total = len(kanji_list) * len(variants)
    done = 0
    lock = asyncio.Lock()
    status_counts: Counter[str] = Counter()

    async def worker(kanji: str, variant: Variant) -> None:
        nonlocal done
        async with sem:
            print(f"[run] {kanji} :: {variant.label}", file=sys.stderr)
            result = await _run_one(
                kanji=kanji,
                variant=variant,
                schema_path=schema_path,
                config_lines=config_lines,
                timeout_s=timeout_s,
                cd=cd,
            )
            async with lock:
                results.append(result)
                done += 1
                status_counts[result["status"]] += 1
                if on_result is not None:
                    on_result(result, done, total, status_counts)
                print(
                    f"[done {done}/{total}] {kanji} :: {variant.label} :: {result['status']}",
                    file=sys.stderr,
                )

    await asyncio.gather(*(worker(kanji, variant) for kanji in kanji_list for variant in variants))
    return results


def _group_results(results: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for result in results:
        grouped.setdefault(result["kanji"], []).append(result)
    for kanji_results in grouped.values():
        kanji_results.sort(key=lambda item: (item["variant"]["model"], item["variant"]["effort"]))
    return grouped


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_jsonl_line(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_jsonl_results(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _result_sort_key(result: dict, *, kanji_order: list[str], variants: list[Variant]) -> tuple[int, int]:
    kanji_index = {kanji: idx for idx, kanji in enumerate(kanji_order)}
    variant_index = {(variant.model, variant.effort): idx for idx, variant in enumerate(variants)}
    result_variant = result.get("variant") or {}
    return (
        kanji_index.get(result.get("kanji"), len(kanji_order)),
        variant_index.get((result_variant.get("model"), result_variant.get("effort")), len(variants)),
    )


def _write_progress(
    path: Path,
    *,
    total: int,
    done: int,
    status_counts: Counter[str],
    meta: dict,
) -> None:
    _write_json(
        path,
        {
            "meta": meta,
            "done": done,
            "total": total,
            "status_counts": dict(status_counts),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )


def create_comparison_epub(*, results: list[dict], output_path: Path, title: str) -> Path:
    book = epub.EpubBook()
    book.set_identifier(f"kanji-model-matrix:{output_path.stem}")
    book.set_title(title)
    book.set_language("ja")
    book.add_author("Codex model matrix")

    style = epub.EpubItem(uid="style", file_name="style.css", media_type="text/css", content=CSS)
    book.add_item(style)

    md = markdown.Markdown(extensions=["tables", "fenced_code"])
    chapters: list[epub.EpubHtml] = []
    toc = []

    grouped = _group_results(results)

    intro = epub.EpubHtml(title="Overview", file_name="overview.xhtml", lang="ja")
    variant_lines = []
    for variant in default_variants():
        variant_lines.append(f"<li><code>{variant.label}</code></li>")
    intro.set_content(
        "<html><head><meta charset='utf-8'/><link rel='stylesheet' href='style.css'/></head><body>"
        f"<h1>{title}</h1>"
        f"<p class='meta'>生成时间：{datetime.now().isoformat(timespec='seconds')}</p>"
        "<p>本 EPUB 按汉字分章，每章内按模型变体顺序展示输出结果，便于横向比较 prompt 效果。</p>"
        "<h2>模型矩阵</h2><ul>"
        + "".join(variant_lines)
        + "</ul></body></html>"
    )
    intro.add_item(style)
    book.add_item(intro)
    chapters.append(intro)
    toc.append(epub.Link("overview.xhtml", "Overview", "overview"))

    for kanji, kanji_results in grouped.items():
        html_parts = [f"<h1>{kanji}</h1>"]
        for result in kanji_results:
            label = variant_label(result["variant"]["model"], result["variant"]["effort"])
            html_parts.append("<section class='variant'>")
            html_parts.append(f"<h2>{label}</h2>")
            html_parts.append(
                f"<p class='meta'>status={result['status']} · elapsed={result.get('elapsed_s', 0)}s</p>"
            )
            if result["status"] == "completed":
                body = md.convert(render(kanji, result["data"]))
                md.reset()
                html_parts.append(body)
            else:
                error = result.get("error", "unknown_error")
                stderr_tail = (result.get("stderr") or "").strip()[-1200:]
                html_parts.append(f"<div class='error'><strong>{error}</strong><pre>{stderr_tail}</pre></div>")
            html_parts.append("</section>")

        chapter = epub.EpubHtml(title=kanji, file_name=f"{kanji}.xhtml", lang="ja")
        chapter.set_content(
            "<html><head><meta charset='utf-8'/><link rel='stylesheet' href='style.css'/></head><body>"
            + "".join(html_parts)
            + "</body></html>"
        )
        chapter.add_item(style)
        book.add_item(chapter)
        chapters.append(chapter)
        toc.append(epub.Link(chapter.file_name, kanji, f"kanji-{kanji}"))

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapters

    output_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output_path), book, {})
    return output_path


def _parse_kanji_args(values: list[str] | None) -> list[str]:
    if not values:
        return default_kanji_sample()
    out: list[str] = []
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if item:
                out.append(item)
    return out


def main() -> int:
    _load_dotenv_if_present()

    parser = argparse.ArgumentParser(description="Run a fixed Codex model matrix for the kanji memory prompt.")
    parser.add_argument("--kanji", action="append", default=None, help="Kanji list, repeatable or comma-separated")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="Per-call timeout in seconds")
    parser.add_argument("--concurrency", type=int, default=5, help="Maximum concurrent Codex calls")
    parser.add_argument("--model", action="append", default=None, help="Only run matching model(s), repeatable")
    parser.add_argument("--effort", action="append", default=None, help="Only run matching reasoning effort(s), repeatable")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Output schema path")
    parser.add_argument("--config-file", type=Path, default=DEFAULT_CONFIG_FILE, help="Codex config override file")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help="Directory for run artifacts")
    parser.add_argument("--cd", type=Path, default=DEFAULT_CD, help="Codex working directory")
    args = parser.parse_args()

    kanji_list = _parse_kanji_args(args.kanji)
    if not kanji_list:
        raise SystemExit("No kanji to run")

    schema_path = args.schema if args.schema.is_absolute() else (REPO_ROOT / args.schema)
    if not schema_path.exists():
        raise SystemExit(f"Missing schema: {schema_path}")

    config_file = args.config_file if args.config_file.is_absolute() else (REPO_ROOT / args.config_file)
    config_lines = _read_config_lines(config_file) if config_file.exists() else []

    variants = filter_variants(default_variants(), models=args.model, efforts=args.effort)
    if not variants:
        raise SystemExit("No variants selected")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    results_jsonl_path = run_dir / "results.jsonl"
    progress_path = run_dir / "progress.json"
    results_path = run_dir / "results.json"
    prompt_snapshot = run_dir / "prompt_template.md"
    epub_path = run_dir / "kanji_memory_model_matrix.epub"

    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "prompt_template": str(PROMPT_TEMPLATE.relative_to(REPO_ROOT)),
        "schema": str(schema_path.relative_to(REPO_ROOT)),
        "kanji": kanji_list,
        "variants": [asdict(variant) | {"slug": variant.slug, "label": variant.label} for variant in variants],
    }
    _write_text(prompt_snapshot, PROMPT_TEMPLATE.read_text(encoding="utf-8"))
    _write_progress(progress_path, total=len(kanji_list) * len(variants), done=0, status_counts=Counter(), meta=meta)

    def on_result(result: dict, done: int, total: int, status_counts: Counter[str]) -> None:
        _write_jsonl_line(results_jsonl_path, result)
        _write_progress(progress_path, total=total, done=done, status_counts=status_counts, meta=meta)

    _ = asyncio.run(
        run_matrix(
            kanji_list=kanji_list,
            variants=variants,
            schema_path=schema_path,
            config_lines=config_lines,
            timeout_s=int(args.timeout),
            concurrency=max(1, int(args.concurrency)),
            cd=args.cd,
            on_result=on_result,
        )
    )

    persisted_results = _load_jsonl_results(results_jsonl_path)
    persisted_results.sort(key=lambda item: _result_sort_key(item, kanji_order=kanji_list, variants=variants))
    payload = {
        "meta": meta | {"completed_at": datetime.now().isoformat(timespec="seconds")},
        "results": persisted_results,
    }

    _write_json(results_path, payload)
    _write_progress(
        progress_path,
        total=len(kanji_list) * len(variants),
        done=len(persisted_results),
        status_counts=Counter(item["status"] for item in persisted_results),
        meta=payload["meta"] | {"finalized": True},
    )
    create_comparison_epub(results=persisted_results, output_path=epub_path, title="日语汉字记忆 Prompt 模型矩阵对比")

    print(f"Wrote: {results_path}")
    print(f"Wrote: {prompt_snapshot}")
    print(f"Wrote: {results_jsonl_path}")
    print(f"Wrote: {progress_path}")
    print(f"Wrote: {epub_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
