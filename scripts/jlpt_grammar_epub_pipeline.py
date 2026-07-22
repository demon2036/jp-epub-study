#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
from ebooklib import epub

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_ROOT / "scripts" / "prompts"
SCHEMAS_DIR = REPO_ROOT / "scripts" / "schemas"
DEFAULT_WORKSPACE = Path("/tmp/grammar_codex_workspace")
DEFAULT_TIMEOUT_S = 900
DEFAULT_RETRIES = 2
CODEX_BIN = os.getenv("CODEX_BIN", "codex")
CRS_ENV_KEY = "CRS_OAI_KEY"
DEFAULT_BASE_URL = "https://api-vip.codex-for.me/v1"
DEFAULT_MODEL = "gpt-5.4"
DEFAULT_REASONING_EFFORT = "xhigh"
JP_RUBY_PATTERN = re.compile(r'^(?:[^\[\]]|[一-龯々〆ヵヶ]+\[[ぁ-ゖー]+\])+$')
KANJI_RUBY_RE = re.compile(r'([一-龯々〆ヵヶ]+)\[([ぁ-ゖー]+)\]')

EPUB_CSS = """
body { font-family: -apple-system, "PingFang SC", "Hiragino Sans", sans-serif; line-height: 1.9; color: #1f2937; padding: 1.2em; }
h1 { font-size: 1.9em; color: #173f79; border-bottom: 2px solid #dbe4f2; padding-bottom: 0.35em; margin-top: 0.4em; }
h2 { font-size: 1.45em; color: #214a84; margin-top: 1.4em; }
h3 { font-size: 1.15em; color: #214a84; margin-top: 1.15em; }
p { margin: 0.45em 0; }
.lead { color: #475569; }
.feel { background: #f6faff; border: 1px solid #dbe8f9; border-radius: 14px; padding: 0.9em 1em; font-weight: 700; }
.section { border: 1px solid #e2e8f4; border-radius: 14px; padding: 1em; margin: 1em 0; background: #fff; }
.scene { background: #fffaf2; border-color: #f2ddbf; }
.formula { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background: #eef5ff; border: 1px solid #d5e3f6; padding: 0.7em 0.85em; border-radius: 10px; color: #173f79; }
.example { padding: 0.75em 0.9em; border-left: 4px solid #93b4ea; background: #f8fbff; border-radius: 0 10px 10px 0; margin: 0.75em 0; }
.jp { font-weight: 700; }
.zh { color: #475569; }
.member-grid { display: block; }
.member-card { border: 1px solid #e2e8f4; border-radius: 12px; padding: 0.85em; margin: 0.8em 0; background: #fff; }
.note { background: #eef7f7; border: 1px solid #c8e6e3; border-radius: 12px; padding: 0.9em 1em; color: #115e59; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #d9e2ef; padding: 0.7em 0.8em; text-align: left; vertical-align: top; }
th { background: #f4f8ff; color: #173f79; }
.pair { border: 1px solid #e2e8f4; border-radius: 10px; padding: 0.7em 0.8em; margin: 0.6em 0; background: #fbfdff; }
.subexamples { margin-top: 0.9em; }
.subexample { border: 1px solid #e2e8f4; border-radius: 10px; padding: 0.75em 0.85em; margin: 0.6em 0; background: #fbfdff; }
.subexample .label { font-weight: 700; color: #173f79; margin-bottom: 0.25em; }
.scene-tag { display: inline-block; margin-bottom: 0.45em; padding: 0.15em 0.55em; border-radius: 999px; background: #eaf2ff; color: #214a84; font-size: 0.92em; font-weight: 700; }
.mini-note { color: #475569; margin-top: 0.25em; }
.contrast-cues { margin-top: 0.65em; padding: 0.65em 0.8em; border-radius: 10px; background: #f7fafc; border: 1px dashed #d8e2ef; }
.contrast-cues div { margin: 0.18em 0; }
ruby { ruby-align: center; ruby-position: over; }
rt { font-size: 0.52em; color: #64748b; }
""".strip()


@dataclass(frozen=True)
class SourceEntry:
    idx: int
    level: str
    grammar_en: str
    grammar_jp: str
    meaning: str
    entry_id: str
    slug: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = value.replace("~", " ")
    value = value.replace("/", " ")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "item"


def parse_grammar_markdown(path: Path, level: str) -> list[SourceEntry]:
    lines = read_text(path).splitlines()
    rows: list[SourceEntry] = []
    in_table = False
    for line in lines:
        if line.startswith("| # | Grammar | 文法 | Meaning |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.strip().startswith("|"):
            continue
        if re.match(r"\|---", line):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) != 4:
            continue
        try:
            idx = int(parts[0])
        except ValueError:
            continue
        grammar_en, grammar_jp, meaning = parts[1:]
        slug = slugify(grammar_en)
        entry_id = f"{level.lower()}_{idx:03d}_{slug}"
        rows.append(SourceEntry(idx=idx, level=level, grammar_en=grammar_en, grammar_jp=grammar_jp, meaning=meaning, entry_id=entry_id, slug=slug))
    if not rows:
        raise ValueError(f"No grammar rows parsed from {path}")
    return rows


def source_entries_payload(entries: list[SourceEntry]) -> list[dict[str, Any]]:
    return [
        {
            "idx": e.idx,
            "entry_id": e.entry_id,
            "grammar_en": e.grammar_en,
            "grammar_jp": e.grammar_jp,
            "meaning": e.meaning,
            "slug": e.slug,
            "level": e.level,
        }
        for e in entries
    ]


def load_json(path: Path) -> Any:
    return json.loads(read_text(path))


def dump_json(path: Path, data: Any) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def load_schema(name: str) -> dict[str, Any]:
    return load_json(SCHEMAS_DIR / name)


def render_template(name: str, **kwargs: Any) -> str:
    template = read_text(PROMPTS_DIR / name)
    return template.format(**kwargs)


def validate_with_schema(data: Any, schema_name: str) -> None:
    schema = load_schema(schema_name)
    jsonschema.validate(data, schema)


def validate_ruby_string(value: str, field_name: str) -> None:
    if not JP_RUBY_PATTERN.fullmatch(value):
        raise ValueError(f"invalid jp_ruby in {field_name}: {value}")


def build_entry_id_alias_map(valid_ids: set[str]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for entry_id in valid_ids:
        if "_" not in entry_id:
            continue
        _, suffix = entry_id.split("_", 1)
        alias_map.setdefault(suffix, entry_id)
    return alias_map


def canonicalize_entry_id(value: str, valid_ids: set[str]) -> str:
    if value in valid_ids:
        return value
    if "_" not in value:
        return value
    _, suffix = value.split("_", 1)
    return build_entry_id_alias_map(valid_ids).get(suffix, value)


def canonicalize_plan_member_ids(plan: dict[str, Any], valid_ids: set[str]) -> dict[str, Any]:
    alias_map = build_entry_id_alias_map(valid_ids)
    cloned = json.loads(json.dumps(plan, ensure_ascii=False))
    for family in cloned.get("families", []):
        family["member_ids"] = [
            alias_map.get(member_id.split("_", 1)[1], member_id) if "_" in member_id else member_id
            for member_id in family.get("member_ids", [])
        ]
    return cloned


def canonicalize_entry_ids_in_payload(data: dict[str, Any], valid_ids: set[str]) -> dict[str, Any]:
    alias_map = build_entry_id_alias_map(valid_ids)
    cloned = json.loads(json.dumps(data, ensure_ascii=False))
    entry_id = cloned.get("entry_id")
    if isinstance(entry_id, str) and "_" in entry_id:
        cloned["entry_id"] = alias_map.get(entry_id.split("_", 1)[1], entry_id)
    for contrast in cloned.get("contrasts", []):
        other_entry_id = contrast.get("other_entry_id")
        if isinstance(other_entry_id, str) and "_" in other_entry_id:
            contrast["other_entry_id"] = alias_map.get(other_entry_id.split("_", 1)[1], other_entry_id)
    return cloned


def validate_entry_ruby(data: dict[str, Any]) -> None:
    for idx, example in enumerate(data.get("scene_examples", []), start=1):
        validate_ruby_string(example["jp_ruby"], f"scene_examples[{idx}].jp_ruby")
    for idx, card in enumerate(data.get("structure_cards", []), start=1):
        validate_ruby_string(card["jp_ruby"], f"structure_cards[{idx}].jp_ruby")
    for idx, contrast in enumerate(data.get("contrasts", []), start=1):
        validate_ruby_string(contrast["example_self"]["jp_ruby"], f"contrasts[{idx}].example_self.jp_ruby")
        validate_ruby_string(contrast["example_other"]["jp_ruby"], f"contrasts[{idx}].example_other.jp_ruby")


def validate_plan(entries: list[SourceEntry], plan: dict[str, Any]) -> None:
    validate_with_schema(plan, "jlpt_grammar_family_plan_v1.schema.json")
    source_ids = {e.entry_id for e in entries}
    seen: list[str] = []
    for family in plan["families"]:
        seen.extend(family["member_ids"])
    seen_set = set(seen)
    missing = sorted(source_ids - seen_set)
    extra = sorted(seen_set - source_ids)
    duplicates = sorted({item for item in seen if seen.count(item) > 1})
    if missing or extra or duplicates:
        raise ValueError(
            "plan coverage error: "
            f"missing={missing[:10]} extra={extra[:10]} duplicates={duplicates[:10]}"
        )


def validate_entry(data: dict[str, Any]) -> None:
    validate_with_schema(data, "jlpt_grammar_entry_v1.schema.json")
    validate_entry_ruby(data)


def escape_xml(text_value: str) -> str:
    return html.escape(text_value, quote=False)


def ruby_text_to_html(text_value: str) -> str:
    escaped = escape_xml(text_value)
    return KANJI_RUBY_RE.sub(r"<ruby>\1<rt>\2</rt></ruby>", escaped)


def example_html(example: dict[str, str], css_class: str = "example") -> str:
    return (
        f'<div class="{css_class}">'
        f'<div class="scene-tag">{escape_xml(example["tag"])}</div>'
        f'<div class="jp">{ruby_text_to_html(example["jp_ruby"])}</div>'
        f'<div class="zh">{escape_xml(example["zh"])}</div>'
        f'<div class="mini-note">{escape_xml(example["note"])}</div>'
        '</div>'
    )


def contrast_pair_html(label: str, payload: dict[str, str]) -> str:
    return (
        '<div class="pair">'
        f'<b>{escape_xml(label)}：</b>'
        f'<div class="jp">{ruby_text_to_html(payload["jp_ruby"])}</div>'
        f'<div class="zh">{escape_xml(payload["zh"])}</div>'
        f'<div class="mini-note">{escape_xml(payload["note"])}</div>'
        '</div>'
    )


def create_book(level: str, entries: list[SourceEntry], plan: dict[str, Any], entry_map: dict[str, dict[str, Any]], output_path: Path) -> None:
    entry_lookup = {e.entry_id: e for e in entries}

    book = epub.EpubBook()
    title = f"JLPT {level} 语法家族全书"
    book.set_identifier(f"grammar-book::{level.lower()}")
    book.set_title(title)
    book.set_language("ja")
    book.add_author("AI 日语教师")

    style_item = epub.EpubItem(uid="style", file_name="style.css", media_type="text/css", content=EPUB_CSS)
    book.add_item(style_item)

    spine: list[Any] = ["nav"]
    toc: list[Any] = []
    chapter_counter = 0

    for family in plan["families"]:
        family_slug = family["family_id"]
        family_chapters: list[Any] = []

        intro_cards = []
        for member_id in family["member_ids"]:
            entry = entry_map[member_id]
            intro_cards.append(
                '<div class="member-card">'
                f'<h3>{escape_xml(entry_lookup[member_id].grammar_jp)}</h3>'
                f'<p>{escape_xml(level)}</p>'
                f'<p>{escape_xml(entry["card_blurb"])}</p>'
                '</div>'
            )
        intro_html = (
            f'<h1>{escape_xml(family["family_name"])}</h1>'
            f'<p class="lead">{escape_xml(family["family_lead"])}</p>'
            f'<div class="feel">{escape_xml(family["family_hook"])}</div>'
            '<div class="section">'
            '<h2>本章成员</h2>'
            '<div class="member-grid">'
            + ''.join(intro_cards)
            + '</div></div>'
        )
        intro_file = f"{family_slug}-intro.xhtml"
        intro_chapter = epub.EpubHtml(title=f'{family["family_name"]} 导读', file_name=intro_file, lang='ja')
        intro_chapter.set_content(f'<html><head><title>{escape_xml(family["family_name"])} 导读</title><link href="style.css" rel="stylesheet" type="text/css"/></head><body>{intro_html}</body></html>')
        intro_chapter.add_item(style_item)
        book.add_item(intro_chapter)
        family_chapters.append(intro_chapter)
        spine.append(intro_chapter)
        chapter_counter += 1

        for member_id in family["member_ids"]:
            src = entry_lookup[member_id]
            data = entry_map[member_id]
            scene_examples_html = ''.join(example_html(ex) for ex in data["scene_examples"])
            structure_cards_html = ''.join(
                '<div class="subexample">'
                f'<div class="label">{escape_xml(card["label"])}</div>'
                f'<div class="mini-note">{escape_xml(card["note"])}</div>'
                f'<div class="jp">{ruby_text_to_html(card["jp_ruby"])}</div>'
                f'<div class="zh">{escape_xml(card["zh"])}</div>'
                f'<div class="mini-note">{escape_xml(card["mini_note"])}</div>'
                '</div>'
                for card in data["structure_cards"]
            )
            usage_points_html = '<ul>' + ''.join(f'<li>{escape_xml(item)}</li>' for item in data["usage_points"]) + '</ul>'
            contrast_rows = []
            for contrast in data["contrasts"]:
                contrast_rows.append(
                    '<tr>'
                    f'<td><b>{escape_xml(contrast["title"])}</b></td>'
                    f'<td>{escape_xml(contrast["difference"])}</td>'
                    '<td>'
                    + contrast_pair_html(contrast["self_label"], contrast["example_self"])
                    + contrast_pair_html(contrast["other_label"], contrast["example_other"])
                    + '</td>'
                    f'<td>{escape_xml(contrast["exam_handle"])}</td>'
                    '</tr>'
                )
            member_html = (
                f'<h1>{escape_xml(src.grammar_jp)}</h1>'
                f'<p class="lead">家族：{escape_xml(family["family_name"])} · 级别：{escape_xml(level)}</p>'
                f'<div class="feel">{escape_xml(data["feel"])}<br/>{escape_xml(data["family_position"])} </div>'
                '<div class="section scene">'
                '<h2>场景镜头</h2>'
                f'<p>{escape_xml(data["scene_paragraph"])}</p>'
                f'{scene_examples_html}'
                '</div>'
                '<div class="section">'
                '<h2>句型骨架</h2>'
                f'<div class="formula">{escape_xml(data["formula"])}</div>'
                f'<p>{escape_xml(data["formula_explainer"])}</p>'
                '<div class="subexamples">'
                '<h3>骨架拆开看</h3>'
                f'{structure_cards_html}'
                '</div>'
                f'{usage_points_html}'
                '</div>'
                '<div class="section">'
                '<h2>对照组</h2>'
                '<table><thead><tr><th>对照组</th><th>感觉差异</th><th>对比例句</th><th>做题抓手</th></tr></thead><tbody>'
                + ''.join(contrast_rows)
                + '</tbody></table></div>'
                f'<div class="note"><b>记忆链：</b>{escape_xml(data["memory_chain"])}</div>'
            )
            member_file = f"{family_slug}-{src.slug}.xhtml"
            member_chapter = epub.EpubHtml(title=src.grammar_jp, file_name=member_file, lang='ja')
            member_chapter.set_content(f'<html><head><title>{escape_xml(src.grammar_jp)}</title><link href="style.css" rel="stylesheet" type="text/css"/></head><body>{member_html}</body></html>')
            member_chapter.add_item(style_item)
            book.add_item(member_chapter)
            family_chapters.append(member_chapter)
            spine.append(member_chapter)
            chapter_counter += 1

        review_rows = build_family_review_rows(family, entry_map, entry_lookup)
        review_html_rows = []
        for row in review_rows:
            review_html_rows.append(
                '<tr>'
                f'<td><b>{escape_xml(row["pair"])}</b></td>'
                f'<td>{escape_xml(row["difference"])}</td>'
                '<td>'
                + contrast_pair_html(row["example_a_label"], row["example_a"])
                + contrast_pair_html(row["example_b_label"], row["example_b"])
                + '</td>'
                f'<td>{escape_xml(row["exam_handle"])}</td>'
                '</tr>'
            )
        review_html = (
            f'<h1>{escape_xml(family["family_name"])} · 家族辨析复盘</h1>'
            f'<p class="lead">{escape_xml(family["progression_line"])} </p>'
            '<table><thead><tr><th>对照组</th><th>怎么区分</th><th>对比例句</th><th>做题抓手</th></tr></thead><tbody>'
            + ''.join(review_html_rows)
            + '</tbody></table>'
        )
        review_file = f"{family_slug}-review.xhtml"
        review_chapter = epub.EpubHtml(title=f'{family["family_name"]} 辨析复盘', file_name=review_file, lang='ja')
        review_chapter.set_content(f'<html><head><title>{escape_xml(family["family_name"])} 辨析复盘</title><link href="style.css" rel="stylesheet" type="text/css"/></head><body>{review_html}</body></html>')
        review_chapter.add_item(style_item)
        book.add_item(review_chapter)
        family_chapters.append(review_chapter)
        spine.append(review_chapter)
        chapter_counter += 1

        toc.append(
            (
                epub.Section(family["family_name"]),
                [
                    epub.Link(intro_file, f'{family["family_name"]} · 导读', f'family-{family_slug}-intro'),
                    *[
                        epub.Link(f"{family_slug}-{entry_lookup[mid].slug}.xhtml", entry_lookup[mid].grammar_jp, f'{family_slug}-{entry_lookup[mid].slug}')
                        for mid in family["member_ids"]
                    ],
                    epub.Link(review_file, f'{family["family_name"]} · 辨析复盘', f'family-{family_slug}-review'),
                ],
            )
        )

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine
    output_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output_path), book, {})


def build_family_review_rows(family: dict[str, Any], entry_map: dict[str, dict[str, Any]], entry_lookup: dict[str, SourceEntry]) -> list[dict[str, Any]]:
    family_ids = set(family["member_ids"])
    rows: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    # Prefer in-family contrasts.
    for source_id in family["member_ids"]:
        source_entry = entry_map[source_id]
        for contrast in source_entry.get("contrasts", []):
            target_id = contrast["other_entry_id"]
            pair_key = tuple(sorted((source_id, target_id)))
            if target_id in family_ids and pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                rows.append(
                    {
                        "pair": contrast["title"],
                        "difference": contrast["difference"],
                        "example_a_label": contrast["self_label"],
                        "example_a": contrast["example_self"],
                        "example_b_label": contrast["other_label"],
                        "example_b": contrast["example_other"],
                        "exam_handle": contrast["exam_handle"],
                    }
                )
    # Fallback to any available contrast if too few.
    if len(rows) < 3:
        for source_id in family["member_ids"]:
            source_entry = entry_map[source_id]
            for contrast in source_entry.get("contrasts", []):
                pair_key = tuple(sorted((source_id, contrast["other_entry_id"])))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                rows.append(
                    {
                        "pair": contrast["title"],
                        "difference": contrast["difference"],
                        "example_a_label": contrast["self_label"],
                        "example_a": contrast["example_self"],
                        "example_b_label": contrast["other_label"],
                        "example_b": contrast["example_other"],
                        "exam_handle": contrast["exam_handle"],
                    }
                )
                if len(rows) >= 4:
                    break
            if len(rows) >= 4:
                break
    if not rows:
        raise ValueError(f"No review rows could be built for family {family['family_id']}")
    return rows[:4]


def extract_agent_message(stdout_text: str) -> str | None:
    last_text = None
    for line in stdout_text.splitlines():
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


def parse_json_response(text_value: str) -> dict[str, Any]:
    text_value = text_value.strip()
    if not text_value:
        raise ValueError("empty response")
    try:
        return json.loads(text_value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text_value, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


async def run_codex_json(prompt_text: str, schema_path: Path, timeout_s: int, cwd: Path, log_path: Path, base_url: str) -> dict[str, Any]:
    cwd.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if not env.get(CRS_ENV_KEY):
        raise RuntimeError(f"{CRS_ENV_KEY} is empty")
    cmd = [
        CODEX_BIN,
        "-a",
        "never",
        "exec",
        "-C",
        str(cwd),
        "--ephemeral",
        "-s",
        "read-only",
        "--skip-git-repo-check",
        "--json",
        "--output-schema",
        str(schema_path),
        "-c",
        'model_provider="crs"',
        "-c",
        f'model="{DEFAULT_MODEL}"',
        "-c",
        f'model_reasoning_effort="{DEFAULT_REASONING_EFFORT}"',
        "-c",
        'preferred_auth_method="apikey"',
        "-c",
        'model_providers.crs.name="crs"',
        "-c",
        f'model_providers.crs.base_url="{base_url}"',
        "-c",
        'model_providers.crs.wire_api="responses"',
        "-c",
        'model_providers.crs.requires_openai_auth=false',
        "-c",
        f'model_providers.crs.env_key="{CRS_ENV_KEY}"',
        "-",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(prompt_text.encode("utf-8")), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        stdout_bytes, stderr_bytes = await proc.communicate()
        write_text(log_path, f"[TIMEOUT]\nSTDOUT:\n{stdout_bytes.decode(errors='replace')}\n\nSTDERR:\n{stderr_bytes.decode(errors='replace')}")
        raise TimeoutError(f"codex timeout after {timeout_s}s")
    stdout_text = stdout_bytes.decode(errors="replace")
    stderr_text = stderr_bytes.decode(errors="replace")
    write_text(log_path, f"STDOUT:\n{stdout_text}\n\nSTDERR:\n{stderr_text}")
    if proc.returncode != 0:
        raise RuntimeError(f"codex exit code {proc.returncode}: {stderr_text[-400:]}")
    agent_message = extract_agent_message(stdout_text)
    if not agent_message:
        raise ValueError("No agent_message found in codex output")
    return parse_json_response(agent_message)


async def generate_plan(entries: list[SourceEntry], level: str, plan_path: Path, prompt_path: Path, log_path: Path, timeout_s: int, base_url: str, workspace: Path, force: bool = False) -> dict[str, Any]:
    valid_ids = {entry.entry_id for entry in entries}
    if plan_path.exists() and not force:
        plan = canonicalize_plan_member_ids(load_json(plan_path), valid_ids)
        validate_plan(entries, plan)
        dump_json(plan_path, plan)
        return plan
    entries_json = json.dumps(source_entries_payload(entries), ensure_ascii=False, indent=2)
    retry_note = ""
    for attempt in range(DEFAULT_RETRIES + 1):
        prompt_text = render_template(
            "jlpt_grammar_family_plan_v1.md",
            level=level,
            entries_json=entries_json,
            retry_note=retry_note,
        )
        write_text(prompt_path, prompt_text)
        try:
            plan = await run_codex_json(prompt_text, SCHEMAS_DIR / "jlpt_grammar_family_plan_v1.schema.json", timeout_s, workspace, log_path, base_url)
            plan = canonicalize_plan_member_ids(plan, valid_ids)
            validate_plan(entries, plan)
            dump_json(plan_path, plan)
            return plan
        except Exception as exc:  # noqa: BLE001
            if attempt >= DEFAULT_RETRIES:
                raise
            retry_note = f"\n上一次输出未通过校验，错误是：{exc}\n请完整重做，并确保每个 entry_id 恰好出现一次。"
    raise AssertionError("unreachable")


async def generate_entry(entry: SourceEntry, family: dict[str, Any], entries_by_id: dict[str, SourceEntry], out_path: Path, prompt_path: Path, log_path: Path, timeout_s: int, base_url: str, workspace: Path, force: bool = False) -> dict[str, Any]:
    valid_ids = set(entries_by_id)
    if out_path.exists() and not force:
        data = canonicalize_entry_ids_in_payload(load_json(out_path), valid_ids)
        validate_entry(data)
        dump_json(out_path, data)
        return data
    family_members = [
        {
            "entry_id": member_id,
            "grammar_jp": entries_by_id[member_id].grammar_jp,
            "grammar_en": entries_by_id[member_id].grammar_en,
            "meaning": entries_by_id[member_id].meaning,
        }
        for member_id in family["member_ids"]
    ]
    retry_note = ""
    for attempt in range(DEFAULT_RETRIES + 1):
        prompt_text = render_template(
            "jlpt_grammar_entry_v1.md",
            level=entry.level,
            source_entry_json=json.dumps(
                {
                    "entry_id": entry.entry_id,
                    "idx": entry.idx,
                    "grammar_en": entry.grammar_en,
                    "grammar_jp": entry.grammar_jp,
                    "meaning": entry.meaning,
                },
                ensure_ascii=False,
                indent=2,
            ),
            family_json=json.dumps(
                {
                    "family_id": family["family_id"],
                    "family_name": family["family_name"],
                    "family_lead": family["family_lead"],
                    "family_hook": family["family_hook"],
                    "progression_line": family["progression_line"],
                    "members": family_members,
                },
                ensure_ascii=False,
                indent=2,
            ),
            retry_note=retry_note,
        )
        write_text(prompt_path, prompt_text)
        try:
            data = await run_codex_json(prompt_text, SCHEMAS_DIR / "jlpt_grammar_entry_v1.schema.json", timeout_s, workspace, log_path, base_url)
            data = canonicalize_entry_ids_in_payload(data, valid_ids)
            validate_entry(data)
            # Cross-check ids so misbinding can't slip through.
            if data["entry_id"] != entry.entry_id:
                raise ValueError(f"entry_id mismatch: expected {entry.entry_id}, got {data['entry_id']}")
            family_member_ids = set(family["member_ids"])
            for contrast in data["contrasts"]:
                if contrast["other_entry_id"] == entry.entry_id:
                    raise ValueError("contrast other_entry_id cannot equal self")
                if contrast["other_entry_id"] not in {e.entry_id for e in entries_by_id.values()}:
                    raise ValueError(f"unknown contrast target: {contrast['other_entry_id']}")
            in_family_count = sum(1 for c in data["contrasts"] if c["other_entry_id"] in family_member_ids)
            if in_family_count < 2:
                raise ValueError("need at least 2 in-family contrasts")
            dump_json(out_path, data)
            return data
        except Exception as exc:  # noqa: BLE001
            if attempt >= DEFAULT_RETRIES:
                raise
            retry_note = f"\n上一次输出未通过校验，错误是：{exc}\n请重做，尤其检查：entry_id、同家族对照数、以及 jp_ruby 的分段标注。"
    raise AssertionError("unreachable")


async def generate_all_entries(entries: list[SourceEntry], plan: dict[str, Any], out_dir: Path, prompts_dir: Path, logs_dir: Path, workers: int, timeout_s: int, base_url: str, workspace: Path, force: bool = False) -> dict[str, dict[str, Any]]:
    entries_by_id = {entry.entry_id: entry for entry in entries}
    family_by_member: dict[str, dict[str, Any]] = {}
    for family in plan["families"]:
        for member_id in family["member_ids"]:
            family_by_member[member_id] = family

    results: dict[str, dict[str, Any]] = {}
    queue: asyncio.Queue[SourceEntry] = asyncio.Queue()
    for entry in entries:
        queue.put_nowait(entry)

    lock = asyncio.Lock()
    total = len(entries)
    completed = 0

    async def worker() -> None:
        nonlocal completed
        while True:
            try:
                entry = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            family = family_by_member[entry.entry_id]
            out_path = out_dir / f"{entry.entry_id}.json"
            prompt_path = prompts_dir / f"{entry.entry_id}.prompt.txt"
            log_path = logs_dir / f"{entry.entry_id}.log"
            data = await generate_entry(entry, family, entries_by_id, out_path, prompt_path, log_path, timeout_s, base_url, workspace, force=force)
            async with lock:
                results[entry.entry_id] = data
                completed += 1
                print(f"[{completed}/{total}] completed {entry.entry_id}", file=sys.stderr)

    tasks = [asyncio.create_task(worker()) for _ in range(max(1, workers))]
    await asyncio.gather(*tasks)

    # Load skipped entries.
    for entry in entries:
        if entry.entry_id not in results:
            results[entry.entry_id] = load_json(out_dir / f"{entry.entry_id}.json")
    return results


def validate_generated_set(entries: list[SourceEntry], plan: dict[str, Any], entries_dir: Path) -> list[str]:
    issues: list[str] = []
    validate_plan(entries, plan)
    for entry in entries:
        path = entries_dir / f"{entry.entry_id}.json"
        if not path.exists():
            issues.append(f"missing file: {path.name}")
            continue
        try:
            validate_entry(load_json(path))
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{path.name}: {exc}")
    return issues


async def run_pipeline(args: argparse.Namespace) -> None:
    source_path = Path(args.source)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = parse_grammar_markdown(source_path, args.level)
    dump_json(out_dir / "source_entries.json", source_entries_payload(entries))

    plan_path = out_dir / "family_plan.json"
    prompts_dir = out_dir / "prompts"
    logs_dir = out_dir / "logs"
    generated_dir = out_dir / "generated"
    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    plan = await generate_plan(
        entries=entries,
        level=args.level,
        plan_path=plan_path,
        prompt_path=prompts_dir / f"{args.level.lower()}_family_plan.prompt.txt",
        log_path=logs_dir / f"{args.level.lower()}_family_plan.log",
        timeout_s=args.timeout,
        base_url=args.base_url,
        workspace=workspace,
        force=args.force_plan,
    )
    print(f"family plan ready: {plan_path}", file=sys.stderr)

    results = await generate_all_entries(
        entries=entries,
        plan=plan,
        out_dir=generated_dir,
        prompts_dir=prompts_dir,
        logs_dir=logs_dir,
        workers=args.workers,
        timeout_s=args.timeout,
        base_url=args.base_url,
        workspace=workspace,
        force=args.force_entries,
    )
    print(f"generated entries: {len(results)}", file=sys.stderr)

    issues = validate_generated_set(entries, plan, generated_dir)
    if issues:
        raise RuntimeError("validation failed:\n" + "\n".join(issues[:50]))

    output_name = args.output or f"jlpt_{args.level.lower()}_grammar_full_xhigh_5b41.epub"
    output_path = out_dir / output_name
    create_book(args.level, entries, plan, results, output_path)
    print(f"epub built: {output_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate JLPT grammar family EPUBs with Codex xhigh.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--level", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--workers", type=int, default=15)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output")
    parser.add_argument("--force-plan", action="store_true")
    parser.add_argument("--force-entries", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    main()
