#!/usr/bin/env python3
"""生成按年级分组的EPUB - 支持锚点跳转"""
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
'''

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

    # 按年级分组
    for grade in range(1, 7):
        grade_kanji = [(k, v) for k, v in db["kanji"].items()
                       if v["grade"] == grade and v["status"] == "completed"]
        if not grade_kanji:
            continue

        # 按原始顺序排序（从年级数据中获取）
        grade_kanji.sort(key=lambda x: x[0])

        # 每年级一个xhtml，每个汉字用section+id做锚点
        html_parts = [f'<h1 class="grade-header">第{grade}学年</h1>']
        nav_items = []

        for kanji, entry in grade_kanji:
            # 从结构化数据渲染 Markdown，再转 HTML
            md_content = render(kanji, entry["data"])
            html_body = md.convert(md_content)
            md.reset()
            html_parts.append(f'<section id="{kanji}">\n{html_body}\n</section>')
            nav_items.append(epub.Link(f"grade{grade}.xhtml#{kanji}", kanji, f"kanji-{kanji}"))

        ch = epub.EpubHtml(title=f"第{grade}学年", file_name=f"grade{grade}.xhtml", lang="ja")
        ch.set_content(f'<html><head><link rel="stylesheet" href="style.css"/></head><body>{"".join(html_parts)}</body></html>')
        ch.add_item(style)
        book.add_item(ch)
        chapters.append(ch)

        # 嵌套TOC: (章节, [子项列表])
        toc.append((epub.Section(f"第{grade}学年 ({len(grade_kanji)}字)"), nav_items))

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav'] + chapters

    epub.write_epub(str(output), book, {})
    print(f"已生成: {output}")

if __name__ == "__main__":
    output = DATA_DIR / "教育汉字详解.epub"
    create_epub(DB_FILE, output)
