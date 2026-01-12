#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


DEFAULT_PDF_URL = (
    "https://www.bunka.go.jp/kokugo_nihongo/sisaku/joho/joho/kijun/naikaku/"
    "pdf/joyokanjihyo_20101130.pdf"
)
EXPECTED_KANJI_COUNT = 2136

# CJK Unified Ideographs + extensions + compatibility ideographs.
KANJI_RANGES = (
    r"\u3400-\u4DBF"  # Ext A
    r"\u4E00-\u9FFF"  # Unified
    r"\uF900-\uFAFF"  # Compatibility
    r"\U00020000-\U0002EBEF"  # Ext B..F (covers beyond; fine for matching)
)
KANJI_CHAR_RE = re.compile(rf"^[{KANJI_RANGES}]$")
KANJI_START_RE = re.compile(rf"^[{KANJI_RANGES}]")


def download_pdf(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (jp.crawler.joyo)",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as f:
        f.write(resp.read())


def run_pdftotext(pdf_path: Path, txt_path: Path) -> None:
    try:
        subprocess.run(
            ["pdftotext", "-enc", "UTF-8", "-nopgbrk", str(pdf_path), str(txt_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError("Missing 'pdftotext' (Poppler). Install it first.") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"pdftotext failed: {e.stderr.strip()}") from e


def extract_joyo_kanji(pdftotext_output: str) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    started = False
    for raw in pdftotext_output.splitlines():
        # Keep leading whitespace: in this PDF, some variant-form lines are indented.
        raw = raw.replace("\x0c", "")

        if not started:
            if raw.strip().startswith("亜"):
                started = True
            else:
                continue

        # Variant-form blocks sometimes appear as indented single-kanji lines (e.g. 辯, 瓣).
        # Skipping indented lines avoids accidentally counting those as separate entries.
        if raw.startswith((" ", "\t")):
            continue

        line = raw.strip()
        if not line:
            continue

        # Skip example lines and other non-header lines that often contain punctuation.
        if any(ch in line for ch in ("，", "、", "。", "・", ":", "：")):
            continue

        if not KANJI_START_RE.match(line):
            continue

        first = line[0]

        is_header = False
        if KANJI_CHAR_RE.match(line):
            is_header = True
        elif "（" in line or "）" in line or " " in line or "\t" in line:
            is_header = True

        if not is_header:
            continue

        if first in seen:
            continue

        seen.add(first)
        ordered.append(first)

        # End of 常用漢字表 in gojūon order.
        if first == "腕":
            break

    return ordered


def extract_joyo_kanji_from_pdf(pdf_path: Path) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="joyo-kanji-") as tmpdir:
        txt_path = Path(tmpdir) / "joyo.txt"
        run_pdftotext(pdf_path, txt_path)
        pdf_text = txt_path.read_text(encoding="utf-8", errors="replace")
    return extract_joyo_kanji(pdf_text)


def write_joyo_output(kanji: list[str], out_path: Path, fmt: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "lines":
        out_path.write_text("\n".join(kanji) + "\n", encoding="utf-8")
        return
    if fmt == "string":
        out_path.write_text("".join(kanji) + "\n", encoding="utf-8")
        return
    if fmt == "json":
        payload = {
            "source_pdf": DEFAULT_PDF_URL,
            "count": len(kanji),
            "kanji": kanji,
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return
    raise ValueError(f"Unknown format: {fmt}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download & extract Jōyō Kanji (常用漢字表 2136字) from the Agency for Cultural Affairs PDF."
    )
    parser.add_argument("--pdf-url", default=DEFAULT_PDF_URL, help="PDF URL to download.")
    parser.add_argument(
        "--pdf",
        default="data/joyokanjihyo_20101130.pdf",
        help="Where to save the PDF (default: %(default)s).",
    )
    parser.add_argument(
        "--out",
        default="data/joyo_kanji_2010.txt",
        help="Output file path (default: %(default)s).",
    )
    parser.add_argument(
        "--format",
        choices=("lines", "string", "json"),
        default="lines",
        help="Output format (default: %(default)s).",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download the PDF even if it already exists.",
    )
    args = parser.parse_args(argv)

    pdf_path = Path(args.pdf)
    out_path = Path(args.out)

    if args.force_download or not pdf_path.exists():
        print(f"Downloading PDF -> {pdf_path}", file=sys.stderr)
        download_pdf(args.pdf_url, pdf_path)

    kanji = extract_joyo_kanji_from_pdf(pdf_path)
    if len(kanji) != EXPECTED_KANJI_COUNT:
        raise RuntimeError(
            f"Extracted {len(kanji)} kanji, expected {EXPECTED_KANJI_COUNT}. "
            "The PDF layout or extraction rules may have changed."
        )

    write_joyo_output(kanji, out_path, args.format)

    print(f"Extracted {len(kanji)} kanji -> {out_path}", file=sys.stderr)
    print(f"First 20: {''.join(kanji[:20])}", file=sys.stderr)
    print(f"Last  20: {''.join(kanji[-20:])}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

