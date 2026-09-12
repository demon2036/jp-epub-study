"""Build the learning-focused ten-kanji edition from its authored Markdown."""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import html
import json
import re

import markdown
from bs4 import BeautifulSoup
from ebooklib import epub
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
TITLE = "日语为什么这样读"
EDITION = "10字动词理解版"
EPUB_PATH = ROOT / f"{TITLE}_{EDITION}.epub"
ORDER = "下上出入起落止動開照"

STYLE = """
body {font-family:"Noto Serif CJK SC","Source Han Serif SC","Songti SC",serif;
 color:#233a38;background:#fff;line-height:1.95;margin:5%;}
p {margin:.85em 0;orphans:2;widows:2;}
h1,h2,h3 {font-family:"Noto Sans CJK SC","PingFang SC",sans-serif;
 color:#164f47;line-height:1.5;page-break-after:avoid;break-after:avoid;}
h1 {font-size:1.6em;margin:.55em 0 1.1em;}
h2 {font-size:1.28em;margin:1.8em 0 .7em;}
h3 {font-size:1.15em;margin:1.9em 0 .7em;}
strong {font-weight:700;color:#184d45;}
a {color:#1c7062;text-decoration:underline;text-underline-offset:.17em;}
li {margin:.7em 0;} ul,ol {padding-left:1.55em;}
table {border-collapse:collapse;width:100%;table-layout:fixed;font-size:.86em;
 line-height:1.75;margin:1.2em 0;}
th,td {text-align:left;vertical-align:top;padding:.6em .45em;border-bottom:1px solid #d8e2dc;
 overflow-wrap:anywhere;}
th {background:#eef3ef;color:#164f47;}
tr {page-break-inside:avoid;break-inside:avoid;}
blockquote {margin:1.1em 0;padding:.7em 1em;border-left:3px solid #80a591;
 background:#f2f6f2;page-break-inside:avoid;break-inside:avoid;}
blockquote p {margin:.35em 0;}
.example {padding:1em 1.05em;}
.example .jp {font-family:"Noto Serif CJK JP","Noto Serif CJK SC",serif;
 font-size:1.18em;line-height:1.65;font-weight:bold;color:#164f47;}
.example .reading {font-family:"Noto Sans CJK JP","Noto Sans CJK SC",sans-serif;
 font-size:.82em;line-height:1.7;color:#526a62;}
.example .translation {font-size:.95em;color:#344a44;}
.formula,.concept {margin:1.25em 0;padding:.85em 1em;border:1px solid #d9d4c4;
 background:#faf7ee;page-break-inside:avoid;break-inside:avoid;}
.formula p,.concept p {margin:.5em 0;}
.formula {font-family:"Noto Sans CJK SC",sans-serif;font-size:.95em;line-height:1.8;}
.label {font-family:sans-serif;font-size:.72em;color:#886b42;letter-spacing:.08em;}
.eyebrow {font: .75em/1.7 sans-serif;color:#667c70;letter-spacing:.1em;margin:0;}
.hero {font:700 3.7em/1.2 "Noto Serif CJK SC",serif;color:#164f47;margin:.18em 0;}
.localtoc {font-size:.83em;line-height:1.85;border-top:1px solid #d9e3dc;
 border-bottom:1px solid #d9e3dc;padding:.75em 0;margin:1.4em 0 1.8em;}
.localtoc p {margin:.25em 0;}
.readingmap {margin:1.4em 0;padding:1em;border:1px solid #d9e3dc;background:#f5f8f3;}
.readingmap h2 {margin:0 0 .25em;font-size:1em;}
.readingmap .maphint {margin:.25em 0 .7em;font-size:.78em;color:#587066;}
.readinggrid {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,7em),1fr));gap:.55em;}
.readinglink {display:block;min-width:0;padding:.55em .65em;background:white;
 border:1px solid #dce5da;text-decoration:none;line-height:1.6;}
.readinglink .kana {display:block;font-family:"Noto Sans CJK JP",sans-serif;font-size:1.05em;font-weight:700;}
.readinglink .word {display:block;font-size:.73em;color:#526a62;}
.readinglink .kind {display:block;font: .65em/1.7 sans-serif;color:#847051;}
.pager {font-family:sans-serif;font-size:.8em;border-top:1px solid #d9e3dc;
 padding-top:1em;margin-top:2.5em;line-height:2;}
.cover-page {margin:0;padding:0;text-align:center;}
.cover-page img {width:100%;height:auto;}
body,p,li {overflow-wrap:break-word;}
"""


def make_cover(reading_count, exercise_count):
    image = Image.new("RGB", (1200, 1800), "#f4f1e7")
    draw = ImageDraw.Draw(image)
    regular = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    bold = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

    def put(x, y, text, size, color="#164f47", heavy=False):
        font = ImageFont.truetype(bold if heavy else regular, size)
        draw.text((x, y), text, font=font, fill=color)

    draw.rectangle((70, 75, 1130, 1725), outline="#c5d0c4", width=2)
    put(132, 130, "日语为什么这样读", 83, heavy=True)
    put(137, 266, "10字 · 动词理解版", 47, "#9b613d")
    draw.line((138, 388, 1062, 388), fill="#9b613d", width=3)
    put(138, 448, "把声音接到场景", 57, heavy=True)
    put(138, 533, "让一个词带出一组词", 57, heavy=True)
    for i, char in enumerate(ORDER):
        x = 146 + (i % 5) * 185
        y = 760 + (i // 5) * 216
        put(x, y, char, 138)
    draw.line((138, 1275, 1062, 1275), fill="#c5d0c4", width=2)
    put(138, 1340, "同一场景 · 声音拆解 · 换词练习", 33, "#546b5d")
    put(138, 1407, f"{reading_count} 项读音  /  {exercise_count} 道练习与答案", 33, "#546b5d")
    put(138, 1615, "日语学习读本  ·  第二版 · 读音补全", 27, "#718075")
    image.save(ROOT / "cover.jpg", quality=94)


def render(body, docid, char=None, reading_items=None):
    rendered = markdown.markdown(body, extensions=["tables", "sane_lists"], output_format="xhtml")
    soup = BeautifulSoup(rendered, "html.parser")
    for i, heading in enumerate(soup.find_all(["h2", "h3"]), 1):
        if not heading.get("id"):
            heading["id"] = f"{docid}-s{i}"
        if char and "遮住上文" in heading.get_text():
            heading["id"] = f"practice-{ord(char):x}"
    examples = 0
    for block in list(soup.find_all("blockquote")):
        paragraphs = block.find_all("p", recursive=False)
        if not paragraphs or len(paragraphs) % 3:
            continue
        groups = [paragraphs[i:i + 3] for i in range(0, len(paragraphs), 3)]
        if not all(re.fullmatch(r"[ぁ-ゖァ-ヺーa-zA-Z0-9\s、。！？・（）「」『』…／：＋ー]+", group[1].get_text()) for group in groups):
            continue
        for group in groups:
            card = soup.new_tag("blockquote", attrs={"class": "example"})
            for p, cls in zip(group, ["jp", "reading", "translation"]):
                p["class"] = cls
                card.append(p.extract())
            group[0]["lang"] = "ja"
            group[1]["lang"] = "ja"
            block.insert_before(card)
            examples += 1
        block.decompose()
    headings = [(h["id"], h.get_text()) for h in soup.find_all(["h2", "h3"])]
    coverage = []
    for item in reading_items or []:
        targets = [h for h in soup.find_all(["h2", "h3"]) if h.get_text().startswith(item["section"])]
        assert len(targets) == 1, (char, item, "Reading must have one section")
        target = targets[0]
        section_parts = [str(target)]
        for sibling in target.next_siblings:
            if getattr(sibling, "name", None) in {"h2", "h3"}:
                break
            section_parts.append(str(sibling))
        section = BeautifulSoup("".join(section_parts), "html.parser")
        section_text = section.get_text()
        assert item["kana"] in section_text, (char, item["kana"], "Reading absent from explanation")
        assert len(section_text) >= 160, (char, item["kana"], "Explanation too short")
        assert section.select(".example"), (char, item["kana"], "No example in explanation")
        coverage.append({"character": char, **item, "anchor": target["id"],
                         "explanation_characters": len(section_text),
                         "example_cards": len(section.select(".example"))})
    return str(soup), headings, examples, coverage


def reading_navigation(rows):
    parts = ['<nav class="readingmap" aria-label="本章读音导航">',
             f'<h2>本章读音 · {len(rows)} 项</h2>',
             '<p class="maphint">点读音，直接到例句和讲解。整词项读完整个词。</p><div class="readinggrid">']
    for row in rows:
        parts.append(f'<a class="readinglink" href="#{row["anchor"]}">'
                     f'<span class="kana" lang="ja">{html.escape(row["kana"])}</span>'
                     f'<span class="word" lang="ja">{html.escape(row["word"])}</span>'
                     f'<span class="kind">{html.escape(row["kind"])}</span></a>')
    parts.append('</div></nav>')
    return "".join(parts)


def main():
    chapters = re.findall(r"^## ([^\n]+)\n(.*?)(?=^## |\Z)", (ROOT / "chapters.md").read_text(), re.M | re.S)
    assert "".join(h[0] for h, _ in chapters) == ORDER
    reading_manifest = json.loads((ROOT / "readings.json").read_text())
    assert "".join(reading_manifest["chapters"]) == ORDER
    for char, rows in reading_manifest["chapters"].items():
        actual = [row["kana"] for row in rows]
        assert len(actual) == len(set(actual)), (char, "Duplicate reading")
        assert set(reading_manifest["baseline_readings"][char]) <= set(actual), (char, "Missing baseline reading")
    reading_count = sum(map(len, reading_manifest["chapters"].values()))
    chapter_exercise_counts = {h[0]: len(re.findall(r"^\d+\. ", b.split("### 遮住上文", 1)[1], re.M)) for h, b in chapters}
    assert all(n == 4 for n in chapter_exercise_counts.values())
    chapter_exercises = sum(chapter_exercise_counts.values())
    mixed_exercises = 8
    exercise_count = chapter_exercises + mixed_exercises
    docs = [("intro.xhtml", "导读｜把动词读成一件事", (ROOT / "intro.md").read_text(), None)]
    docs.extend((f"char-{ord(h[0]):x}.xhtml", h, b, h[0]) for h, b in chapters)
    docs.extend([
        ("practice.xhtml", "八个混合场景与回想路线", (ROOT / "practice.md").read_text(), None),
        ("answers.xhtml", "练习答案与理由", (ROOT / "answers.md").read_text(), None),
    ])

    make_cover(reading_count, exercise_count)
    book = epub.EpubBook()
    book.set_identifier("urn:uuid:6d3c4fc7-dfe5-46d2-bb49-71869f30b216")
    book.set_title(f"{TITLE}：{EDITION}")
    book.set_language("zh-CN")
    book.add_author("个人日语学习读本")
    book.add_metadata("DC", "description", f"把声音接到场景，让一个词带出一组词。10章讲解，{reading_count}项读音，{exercise_count}道练习与答案。")
    css = epub.EpubItem(uid="style", file_name="style.css", media_type="text/css", content=STYLE.encode())
    book.add_item(css)
    book.set_cover("cover.jpg", (ROOT / "cover.jpg").read_bytes(), create_page=False)
    cover = epub.EpubHtml(title="封面", file_name="cover.xhtml", lang="zh-CN")
    cover.content = f'<body class="cover-page"><img src="cover.jpg" alt="{TITLE}：{EDITION}"/></body>'
    cover.add_item(css)
    book.add_item(cover)
    spine = [cover, "nav"]
    toc = []
    preview = []
    chapter_counts = {}
    example_count = 0
    coverage_rows = []

    for index, (path, title, body, char) in enumerate(docs):
        docid = path.removesuffix(".xhtml")
        fragment, headings, examples, coverage = render(body, docid, char,
            reading_manifest["chapters"].get(char))
        coverage_rows.extend(coverage)
        example_count += examples
        if char:
            reading_anchors = {row["anchor"] for row in coverage}
            local = '<div class="localtoc"><p class="label">接着看构词、用法与练习</p>'
            local += "".join(f'<p><a href="#{anchor}">{html.escape(label)}</a></p>' for anchor, label in headings if anchor not in reading_anchors)
            local += "</div>"
            fragment = (f'<p class="eyebrow">动词理解 · {index:02d} / 10</p>'
                        f'<div class="hero">{char}</div><h1>{html.escape(title.split("｜", 1)[1])}</h1>'
                        + reading_navigation(coverage) + local + fragment)
            chapter_counts[char] = len(BeautifulSoup(fragment, "html.parser").get_text())
        nav = ['<a href="nav.xhtml">目录</a>']
        if index:
            nav.append(f'<a href="{docs[index - 1][0]}">上一节</a>')
        if index + 1 < len(docs):
            nav.append(f'<a href="{docs[index + 1][0]}">下一节</a>')
        fragment += '<nav class="pager">' + "　·　".join(nav) + "</nav>"
        page = epub.EpubHtml(title=title, file_name=path, lang="zh-CN")
        page.content = "<body>" + fragment + "</body>"
        page.add_item(css)
        book.add_item(page)
        spine.append(page)
        if path == "intro.xhtml":
            toc.append((page, (epub.Link("intro.xhtml#why-r-s", "为什么る与す会成对", "why-r-s"),)))
        elif path == "answers.xhtml":
            toc.append((page, tuple(epub.Link(f"{path}#{anchor}", label, anchor) for anchor, label in headings if anchor.startswith("answer-") or anchor == "mixed-answers")))
        else:
            toc.append(page)
        preview.append((docid, title, fragment))

    book.toc = tuple(toc)
    book.spine = spine
    book.add_item(epub.EpubNcx())
    epubnav = epub.EpubNav()
    epubnav.add_item(css)
    book.add_item(epubnav)
    epub.write_epub(str(EPUB_PATH), book)

    webstyle = """
    :root{--reading-size:19px}
    body{margin:0;font-size:var(--reading-size);background:#f2f1e9;}
    .topbar{position:sticky;top:0;z-index:3;padding:12px 20px;background:#164f47;
     color:#fff;font:14px/1.8 sans-serif;display:flex;flex-wrap:wrap;gap:6px 18px;align-items:center;}
    .topbar a{color:white;text-decoration:none}.topbar .tools{margin-left:auto;display:flex;gap:7px;}
    button{border:1px solid #a7c1b4;background:transparent;color:white;padding:5px 10px;
     border-radius:3px;font:14px/1.5 sans-serif;cursor:pointer;}
    button:focus-visible,a:focus-visible{outline:3px solid #bd843e;outline-offset:3px;}
    .shell{max-width:1140px;margin:auto;display:grid;grid-template-columns:220px minmax(0,1fr);}
    .side{position:sticky;top:90px;align-self:start;padding:28px 20px;max-height:78vh;overflow-y:auto;
     font:14px/1.8 "Noto Sans CJK SC",sans-serif;}
    .side ol{padding-left:1.4em}.side li{margin:.65em 0}.side a{text-decoration:none;color:#476352;}
    main{background:white;min-width:0;padding:36px 52px 72px;}
    section{margin:0 0 5em;scroll-margin-top:110px;}
    h2,h3{scroll-margin-top:110px;}
    .webcover{width:260px;max-width:75%;display:block;margin:0 auto 28px;box-shadow:0 7px 24px #213f3722;}
    .bookhead{text-align:center;padding:0 0 36px;border-bottom:1px solid #d9e3dc;margin-bottom:38px;}
    .bookhead p{font:14px/1.8 sans-serif;color:#687b6b;}
    .download{display:inline-block;background:#164f47;color:white;padding:10px 20px;text-decoration:none;
     border-radius:3px;font:15px/1.8 sans-serif;}
    .hide-kana .reading{visibility:hidden;}
    @media(max-width:820px){.shell{display:block}.side{display:none}main{padding:28px 6% 60px;}
     body{font-size:18px;font-size:var(--reading-size)}.topbar{padding:10px 5%;gap:6px 12px;}
     .topbar .tools{margin-left:0}.topbar .charlinks{width:100%;letter-spacing:.3em;font-size:16px;}
     section,h2,h3{scroll-margin-top:140px;}
     .hero{font-size:3.4em}.webcover{width:220px;}.example{padding:.75em .85em;}}
    @media(max-width:360px){.readinggrid{grid-template-columns:minmax(0,1fr);}}
    @media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
    @media print{.topbar,.side,.tools,.download{display:none}.shell{display:block}main{padding:0}.pager{display:none}}
    """
    sidebar = '<aside class="side" aria-label="章节"><p class="label">10字 · 动词理解版</p><ol>'
    sidebar += "".join(f'<li><a href="#{docid}">{html.escape(title)}</a></li>' for docid, title, _ in preview)
    sidebar += "</ol></aside>"
    web = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/>',
           '<meta name="viewport" content="width=device-width,initial-scale=1"/>',
           f'<title>{TITLE} · {EDITION}</title><style>{STYLE}{webstyle}</style></head><body>',
           '<header class="topbar"><a href="#contents">目录</a><nav class="charlinks" aria-label="十字章节">',
           " ".join(f'<a href="#char-{ord(c):x}">{c}</a>' for c in ORDER),
           '</nav><div class="tools"><button type="button" id="smaller" aria-label="减小字号">A−</button>',
           '<button type="button" id="larger" aria-label="增大字号">A＋</button>',
           '<button type="button" id="kana-toggle" aria-pressed="false">隐藏假名</button></div></header>',
           '<div class="shell">', sidebar, '<main><div class="bookhead">',
           '<img class="webcover" src="cover.jpg" alt="日语为什么这样读：10字动词理解版封面"/>',
           f'<p>10章讲解 · {reading_count}项读音 · {exercise_count}道练习与答案</p>',
           f'<a class="download" href="{html.escape(EPUB_PATH.name)}" download>下载 EPUB</a></div>',
           '<section id="contents"><h1>从一个词，认出一组关系</h1><ol>']
    web += [f'<li><a href="#{docid}">{html.escape(title)}</a></li>' for docid, title, _ in preview]
    web.append("</ol></section>")
    for docid, _, fragment in preview:
        fragment = re.sub(
            r'href="([^"#]+)\.xhtml(?:#([^\"]+))?"',
            lambda m: 'href="#' + (m[2] or ("contents" if m[1] == "nav" else m[1])) + '"', fragment)
        web.append(f'<section id="{docid}">{fragment}</section>')
    web += ['</main></div><script>',
            'let readingSize=19;function changeSize(delta){readingSize=Math.max(16,Math.min(26,readingSize+delta));',
            'document.documentElement.style.setProperty("--reading-size",readingSize+"px");}',
            'document.getElementById("smaller").addEventListener("click",()=>changeSize(-1));',
            'document.getElementById("larger").addEventListener("click",()=>changeSize(1));',
            'document.getElementById("kana-toggle").addEventListener("click",function(){',
            'const hidden=document.body.classList.toggle("hide-kana");this.setAttribute("aria-pressed",String(hidden));',
            'this.textContent=hidden?"显示假名":"隐藏假名";});', '</script></body></html>']
    (ROOT / "阅读预览.html").write_text("".join(web))
    report = {"title": TITLE, "edition": EDITION, "chapters": 10,
              "chapter_reading_characters": chapter_counts,
              "total_chapter_reading_characters": sum(chapter_counts.values()),
              "example_cards_with_kana": example_count, "chapter_exercises": chapter_exercises, "mixed_exercises": mixed_exercises,
              "reading_entries": reading_count,
              "readings_by_character": {c: len(rows) for c, rows in reading_manifest["chapters"].items()},
              "epub_bytes": EPUB_PATH.stat().st_size,
              "sha256": hashlib.sha256(EPUB_PATH.read_bytes()).hexdigest()}
    (ROOT / "build-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    baseline_count = sum(map(len, reading_manifest["baseline_readings"].values()))
    coverage_report = {"baseline_entries": baseline_count, "baseline_covered": baseline_count,
                       "additional_entries": reading_count - baseline_count,
                       "total_entries": reading_count, "missing": [], "entries": coverage_rows}
    (ROOT / "reading-coverage.json").write_text(json.dumps(coverage_report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
