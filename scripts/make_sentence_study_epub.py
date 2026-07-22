#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ebooklib import epub


CSS = """
body { font-family: -apple-system, "PingFang SC", "Hiragino Sans", sans-serif; line-height: 1.9; color: #1f2937; padding: 1em; }
h1 { font-size: 1.8em; margin: 0.6em 0 0.8em; color: #1a365d; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.4em; }
h2 { font-size: 1.2em; margin: 1.1em 0 0.3em; color: #2c5282; }
.meta { color: #6b7280; font-size: 0.92em; margin: 0.2em 0 0.7em; }
.sentence { margin: 1.2em 0; padding-bottom: 1.2em; border-bottom: 1px dashed #e5e7eb; }
.jp { font-size: 1.12em; margin: 0.2em 0 0.3em; }
.zh { margin: 0.2em 0 0.6em; color: #111827; }
table { border-collapse: collapse; width: 100%; margin: 0.6em 0; }
th, td { border: 1px solid #d1d5db; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #f3f4f6; font-weight: 600; }
.empty { color: #9ca3af; }
"""


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _render_words(words: list[dict]) -> str:
    if not words:
        return ""
    rows = [
        "<table><thead><tr><th>词/短语</th><th>读音</th><th>词性</th><th>中文</th><th>备注</th></tr></thead><tbody>"
    ]
    for w in words:
        rows.append(
            "<tr>"
            f"<td>{_html_escape(str(w.get('jp','')))}</td>"
            f"<td>{_html_escape(str(w.get('reading','')))}</td>"
            f"<td>{_html_escape(str(w.get('pos','')))}</td>"
            f"<td>{_html_escape(str(w.get('meaning_zh','')))}</td>"
            f"<td>{_html_escape(str(w.get('note') or ''))}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _render_tokens(tokens: list[dict]) -> str:
    if not tokens:
        return ""

    filtered: list[dict] = []
    for t in tokens:
        if not isinstance(t, dict):
            continue
        if t.get("pos_major") == "記号":
            continue
        filtered.append(t)

    if not filtered:
        return ""

    rows = [
        "<table><thead><tr>"
        "<th>单词</th><th>读音</th><th>原形</th><th>词性</th><th>活用</th><th>中文</th><th>语法作用</th>"
        "</tr></thead><tbody>"
    ]
    for t in filtered:
        pos_major = str(t.get("pos_major") or "")
        pos_sub = str(t.get("pos_sub") or "")
        pos = pos_major if not pos_sub else f"{pos_major}/{pos_sub}"
        infl_type = str(t.get("infl_type") or "")
        infl_form = str(t.get("infl_form") or "")
        infl = ""
        if infl_type or infl_form:
            infl = f"{infl_type} {infl_form}".strip()

        rows.append(
            "<tr>"
            f"<td>{_html_escape(str(t.get('surface','')))}</td>"
            f"<td>{_html_escape(str(t.get('reading_kana','')))}</td>"
            f"<td>{_html_escape(str(t.get('base','')))}</td>"
            f"<td>{_html_escape(pos)}</td>"
            f"<td>{_html_escape(infl)}</td>"
            f"<td>{_html_escape(str(t.get('meaning_zh') or ''))}</td>"
            f"<td>{_html_escape(str(t.get('grammar_note') or ''))}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _render_grammar(grammar: list[dict]) -> str:
    if not grammar:
        return ""
    rows = [
        "<table><thead><tr><th>语法</th><th>中文</th><th>说明</th><th>级别</th></tr></thead><tbody>"
    ]
    for g in grammar:
        rows.append(
            "<tr>"
            f"<td>{_html_escape(str(g.get('pattern','')))}</td>"
            f"<td>{_html_escape(str(g.get('meaning_zh','')))}</td>"
            f"<td>{_html_escape(str(g.get('usage_note','')))}</td>"
            f"<td>{_html_escape(str(g.get('level') or ''))}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def make_epub(
    in_json: Path,
    out_epub: Path,
    *,
    title: str | None = None,
    author: str = "AI 日语教师",
    chunk_size: int = 50,
    max_sentences: int | None = None,
    only_annotated: bool = False,
) -> Path:
    data = _load(in_json)
    sentences = data.get("sentences")
    if not isinstance(sentences, list):
        raise ValueError("Invalid input JSON: missing sentences[]")

    if only_annotated:
        sentences = [s for s in sentences if isinstance(s, dict) and s.get("zh")]

    if max_sentences is not None and max_sentences > 0:
        sentences = sentences[:max_sentences]

    resolved_title = title or f"句子精读：{in_json.stem}"

    book = epub.EpubBook()
    book.set_identifier(f"sentence-study:{in_json.stem}")
    book.set_title(resolved_title)
    book.set_language("ja")
    book.add_author(author)

    style = epub.EpubItem(uid="style", file_name="style.css", media_type="text/css", content=CSS)
    book.add_item(style)

    chapters: list[epub.EpubHtml] = []
    toc = []

    total = len(sentences)
    if chunk_size <= 0:
        chunk_size = total or 1

    part = 0
    for start in range(0, total, chunk_size):
        part += 1
        chunk = sentences[start : start + chunk_size]
        html_parts = [f"<h1>第 {part} 部分</h1>", f'<p class="meta">句子：{start+1}–{start+len(chunk)} / {total}</p>']

        for s in chunk:
            if not isinstance(s, dict):
                continue
            sid = s.get("id")
            jp = _html_escape(str(s.get("jp", "")))
            zh = s.get("zh")
            zh_html = _html_escape(str(zh)) if zh else '<span class="empty">（未标注）</span>'
            meta = f"ID {sid} · spine {s.get('spine_index')} · {s.get('spine_path')}"

            html_parts.append(
                f'<div class="sentence" id="s{sid}">'
                f'<div class="meta">{_html_escape(meta)}</div>'
                f'<div class="jp">{jp}</div>'
                f'<div class="zh">{zh_html}</div>'
                f"{_render_tokens(s.get('tokens') if isinstance(s.get('tokens'), list) else [])}"
                f"{_render_words(s.get('words') if isinstance(s.get('words'), list) else [])}"
                f"{_render_grammar(s.get('grammar') if isinstance(s.get('grammar'), list) else [])}"
                "</div>"
            )

        ch = epub.EpubHtml(title=f"Part {part}", file_name=f"part{part}.xhtml", lang="ja")
        ch.set_content(
            f'<html><head><meta charset="utf-8"/><link rel="stylesheet" href="style.css"/></head>'
            f'<body>{"".join(html_parts)}</body></html>'
        )
        ch.add_item(style)
        book.add_item(ch)
        chapters.append(ch)
        toc.append(epub.Link(ch.file_name, f"第 {part} 部分", f"part-{part}"))

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapters

    out_epub.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(out_epub), book, {})
    return out_epub


def main() -> int:
    parser = argparse.ArgumentParser(description="Make a study EPUB from annotated sentence JSON.")
    parser.add_argument("in_json", type=Path, help="Input sentence JSON")
    parser.add_argument("--out", type=Path, default=None, help="Output .epub path")
    parser.add_argument("--title", type=str, default=None, help="EPUB title override")
    parser.add_argument("--author", type=str, default="AI 日语教师")
    parser.add_argument("--chunk-size", type=int, default=50, help="Sentences per chapter (default: 50)")
    parser.add_argument("--max-sentences", type=int, default=200, help="Limit total sentences (default: 200)")
    parser.add_argument("--only-annotated", action="store_true", help="Include only sentences with zh filled")
    args = parser.parse_args()

    in_json: Path = args.in_json
    if not in_json.exists():
        raise SystemExit(f"Not found: {in_json}")

    out_path = args.out or (Path("data/extracted_text") / f"{in_json.stem}_study.epub")

    out_epub = make_epub(
        in_json,
        out_path,
        title=args.title,
        author=args.author,
        chunk_size=int(args.chunk_size),
        max_sentences=int(args.max_sentences) if args.max_sentences else None,
        only_annotated=bool(args.only_annotated),
    )
    print(f"Wrote: {out_epub}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
