#!/usr/bin/env python3
"""生成按年级/常用补充分组的EPUB - 支持锚点跳转"""
import argparse
import json
from pathlib import Path
import markdown
from ebooklib import epub

from render_kanji import render

DATA_DIR = Path(__file__).parent.parent / "data"
DB_FILE = DATA_DIR / "kanji_db_v2.json"

CSS = '''
body { font-family: -apple-system, "PingFang SC", "Hiragino Sans", sans-serif; line-height: 1.9; color: #333; padding: 1em; }
h1 { font-size: 2em; color: #1a365d; border-bottom: 2px solid #cbd5e0; padding-bottom: 0.5em; margin-top: 2em; }
h2 { font-size: 1.3em; color: #2c5282; margin-top: 1.5em; }
h3 { font-size: 1.1em; color: #4a5568; margin-top: 1em; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #a0aec0; padding: 8px 10px; text-align: left; }
th { background-color: #edf2f7; font-weight: 600; }
blockquote { background: #f0f4f8; border-left: 3px solid #4299e1; padding: 0.8em 1em; margin: 1em 0; }
pre { background: #f0f4f8; padding: 1em; border-radius: 6px; overflow-x: auto; }
code { background: #e2e8f0; padding: 2px 5px; border-radius: 3px; }
section { margin-bottom: 3em; padding-bottom: 2em; border-bottom: 1px dashed #cbd5e0; }
.grade-header { font-size: 1.5em; color: #2d3748; text-align: center; margin: 1em 0 2em; }
ruby { ruby-align: center; ruby-position: over; }
rt { font-size: 0.52em; color: #64748b; font-weight: 500; }
.reading-example { background: #f8fbff; border-left: 4px solid #4299e1; border-radius: 0 10px 10px 0; padding: 0.75em 0.9em; margin: 0.75em 0 1em; }
.jp-example { font-size: 1.14em; font-weight: 800; color: #173f79; }
.kana-line, .mandarin-line, .zh-line, .mini-note { color: #475569; margin-top: 0.2em; }
.mandarin-line { color: #173f79; font-weight: 700; }
'''


def _grade_kanji_in_db_order(db: dict, grade: int) -> list[tuple[str, dict]]:
    return [
        (kanji, entry)
        for kanji, entry in db["kanji"].items()
        if entry["grade"] == grade and entry["status"] == "completed"
    ]


def _grades_in_db_order(db: dict) -> list[int]:
    grades: list[int] = []
    seen: set[int] = set()
    for entry in db["kanji"].values():
        if entry.get("status") != "completed":
            continue
        grade = int(entry.get("grade", 7))
        if grade not in seen:
            seen.add(grade)
            grades.append(grade)
    return sorted(grades, key=lambda grade: (grade > 6, grade))


def _grade_title(grade: int) -> str:
    if 1 <= grade <= 6:
        return f"第{grade}学年"
    if grade == 7:
        return "常用补充"
    return f"分组{grade}"


def create_epub(db_path: Path, output: Path):
    db = json.loads(db_path.read_text(encoding="utf-8"))

    book = epub.EpubBook()
    book.set_identifier('kyoiku-kanji-guide')
    book.set_title('教育汉字详解')
    book.set_language('ja')
    book.add_author('AI 日语教师')

    style = epub.EpubItem(uid="style", file_name="style.css", media_type="text/css", content=CSS)
    book.add_item(style)

    md = markdown.Markdown(extensions=['tables', 'fenced_code'])
    chapters = []
    toc = []

    # 按年级/常用补充分组
    for grade in _grades_in_db_order(db):
        grade_kanji = _grade_kanji_in_db_order(db, grade)
        if not grade_kanji:
            continue
        grade_title = _grade_title(grade)

        # 每年级一个xhtml，每个汉字用section+id做锚点
        html_parts = [f'<h1 class="grade-header">{grade_title}</h1>']
        nav_items = []

        for kanji, entry in grade_kanji:
            # 从结构化数据渲染 Markdown，再转 HTML
            md_content = render(kanji, entry["data"])
            html_body = md.convert(md_content)
            md.reset()
            html_parts.append(f'<section id="{kanji}">\n{html_body}\n</section>')
            nav_items.append(epub.Link(f"grade{grade}.xhtml#{kanji}", kanji, f"kanji-{kanji}"))

        ch = epub.EpubHtml(title=grade_title, file_name=f"grade{grade}.xhtml", lang="ja")
        ch.set_content(f'<html><head><link rel="stylesheet" href="style.css"/></head><body>{"".join(html_parts)}</body></html>')
        ch.add_item(style)
        book.add_item(ch)
        chapters.append(ch)

        # 嵌套TOC: (章节, [子项列表])
        toc.append((epub.Section(f"{grade_title} ({len(grade_kanji)}字)"), nav_items))

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav'] + chapters

    epub.write_epub(str(output), book, {})
    print(f"已生成: {output}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_FILE, help="Input kanji DB JSON")
    parser.add_argument("--output", type=Path, default=DATA_DIR / "教育汉字详解.epub")
    args = parser.parse_args()
    create_epub(args.db, args.output)
