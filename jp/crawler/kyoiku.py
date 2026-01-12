#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


WIKI_API = "https://ja.wikipedia.org/w/api.php"
WIKI_PAGE = "学年別漢字配当表"
USER_AGENT = "Mozilla/5.0 (jp.crawler.kyoiku)"

EXPECTED_TOTAL = 1026
EXPECTED_PER_GRADE = {1: 80, 2: 160, 3: 200, 4: 202, 5: 193, 6: 191}

# CJK Unified Ideographs + extensions + compatibility ideographs.
KANJI_RANGES = (
    r"\u3400-\u4DBF"  # Ext A
    r"\u4E00-\u9FFF"  # Unified
    r"\uF900-\uFAFF"  # Compatibility
    r"\U00020000-\U0002EBEF"  # Ext B..F (covers beyond; fine for matching)
)
KANJI_CHAR_RE = re.compile(rf"^[{KANJI_RANGES}]$")


def wiki_get(params: dict[str, str | int]) -> dict:
    query = urllib.parse.urlencode({k: str(v) for k, v in params.items()})
    req = urllib.request.Request(
        f"{WIKI_API}?{query}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


@dataclass(frozen=True)
class GradeSection:
    grade: int
    index: str
    title: str


def fetch_grade_sections() -> list[GradeSection]:
    obj = wiki_get(
        {
            "action": "parse",
            "page": WIKI_PAGE,
            "prop": "sections",
            "format": "json",
            "formatversion": 2,
        }
    )
    sections = obj["parse"]["sections"]

    grade_sections: list[GradeSection] = []
    grade_title_re = re.compile(r"^第([1-6])学年（(\d+)字）$")

    for section in sections:
        title = section.get("line", "")
        m = grade_title_re.match(title)
        if not m:
            continue
        grade = int(m.group(1))
        expected = int(m.group(2))
        if EXPECTED_PER_GRADE.get(grade) != expected:
            raise RuntimeError(f"Unexpected count in title: {title}")
        grade_sections.append(
            GradeSection(grade=grade, index=str(section["index"]), title=title)
        )

    grade_sections.sort(key=lambda s: s.grade)
    if [s.grade for s in grade_sections] != [1, 2, 3, 4, 5, 6]:
        raise RuntimeError(f"Failed to locate all grade sections: {grade_sections}")
    return grade_sections


class ExtiwKanjiParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_target_link = False
        self.kanji: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr = {k: (v or "") for k, v in attrs}
        if attr.get("class") != "extiw":
            return
        if not attr.get("title", "").startswith("wikt:"):
            return
        self._in_target_link = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._in_target_link = False

    def handle_data(self, data: str) -> None:
        if not self._in_target_link:
            return
        s = data.strip()
        if KANJI_CHAR_RE.match(s):
            self.kanji.append(s)


def fetch_grade_kanji(section_index: str) -> list[str]:
    obj = wiki_get(
        {
            "action": "parse",
            "page": WIKI_PAGE,
            "prop": "text",
            "section": section_index,
            "format": "json",
            "formatversion": 2,
        }
    )
    html = obj["parse"]["text"]
    parser = ExtiwKanjiParser()
    parser.feed(html)
    return parser.kanji


def fetch_kyoiku_kanji_by_grade() -> dict[int, list[str]]:
    grade_sections = fetch_grade_sections()
    by_grade: dict[int, list[str]] = {}
    seen: set[str] = set()

    for sec in grade_sections:
        items = fetch_grade_kanji(sec.index)
        expected = EXPECTED_PER_GRADE[sec.grade]
        if len(items) != expected:
            raise RuntimeError(
                f"{sec.title}: extracted {len(items)} kanji, expected {expected}"
            )
        dup = [k for k in items if k in seen]
        if dup:
            raise RuntimeError(f"{sec.title}: duplicate kanji across grades: {dup[:10]}")
        seen.update(items)
        by_grade[sec.grade] = items

    if sum(len(v) for v in by_grade.values()) != EXPECTED_TOTAL:
        raise RuntimeError(
            f"Extracted {sum(len(v) for v in by_grade.values())} kanji, expected {EXPECTED_TOTAL}."
        )
    return by_grade


def flatten_by_grade(by_grade: dict[int, list[str]]) -> list[str]:
    all_kanji: list[str] = []
    for grade in range(1, 7):
        all_kanji.extend(by_grade.get(grade, []))
    return all_kanji


def write_kyoiku_output(kanji: list[str], out_path: Path, fmt: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "lines":
        out_path.write_text("\n".join(kanji) + "\n", encoding="utf-8")
        return
    if fmt == "string":
        out_path.write_text("".join(kanji) + "\n", encoding="utf-8")
        return
    raise ValueError(f"Unknown format: {fmt}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Kyoiku Kanji (教育漢字 / 学年別漢字配当表 1026字) via Wikipedia API."
    )
    parser.add_argument(
        "--out",
        default="data/kyoiku_kanji_2020.txt",
        help="Output file path (default: %(default)s).",
    )
    parser.add_argument(
        "--format",
        choices=("lines", "string"),
        default="lines",
        help="Output format (default: %(default)s).",
    )
    parser.add_argument(
        "--out-by-grade-json",
        default="data/kyoiku_kanji_2020_by_grade.json",
        help="Write per-grade JSON (default: %(default)s).",
    )
    args = parser.parse_args(argv)

    by_grade = fetch_kyoiku_kanji_by_grade()
    all_kanji = flatten_by_grade(by_grade)

    out_path = Path(args.out)
    write_kyoiku_output(all_kanji, out_path, args.format)

    out_json_path = Path(args.out_by_grade_json)
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": {"wiki_api": WIKI_API, "page": WIKI_PAGE},
        "total": len(all_kanji),
        "per_grade": {str(g): len(v) for g, v in by_grade.items()},
        "by_grade": {str(g): v for g, v in by_grade.items()},
    }
    out_json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Extracted {len(all_kanji)} kanji -> {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

