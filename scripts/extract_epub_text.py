#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET


XHTML_NS = "http://www.w3.org/1999/xhtml"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NS = "http://www.idpf.org/2007/opf"


def _local_name(tag: str) -> str:
    if "}" not in tag:
        return tag
    return tag.rsplit("}", 1)[-1]


def _extract_inline_text(elem: ET.Element, *, furigana: bool) -> str:
    name = _local_name(elem.tag)
    if name == "rt":
        return ""
    if name == "br":
        return "\n"
    if name == "ruby":
        base_parts: list[str] = []
        rt_parts: list[str] = []

        if elem.text:
            base_parts.append(elem.text)

        for child in list(elem):
            child_name = _local_name(child.tag)
            if child_name == "rt":
                if child.text:
                    rt_parts.append(child.text)
            else:
                base_parts.append(_extract_inline_text(child, furigana=furigana))
            if child.tail:
                base_parts.append(child.tail)

        base = "".join(base_parts).strip()
        reading = "".join(rt_parts).strip()
        if furigana and reading and base:
            return f"{base}（{reading}）"
        return base

    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)

    for child in list(elem):
        parts.append(_extract_inline_text(child, furigana=furigana))
        if child.tail:
            parts.append(child.tail)

    return "".join(parts)


_ONLY_DIGITS_RE = re.compile(r"^[0-9０-９]+$")


def _extract_paragraphs(xhtml: str, *, furigana: bool) -> list[str]:
    try:
        root = ET.fromstring(xhtml)
    except ET.ParseError:
        # Conservative fallback: strip DOCTYPE and try again.
        xhtml_2 = re.sub(r"<!DOCTYPE[^>]*>", "", xhtml, flags=re.IGNORECASE)
        root = ET.fromstring(xhtml_2)

    paragraphs = []
    for p in root.findall(f".//{{{XHTML_NS}}}p"):
        text = _extract_inline_text(p, furigana=furigana)
        text = text.replace("\u00a0", " ").strip()
        if not text:
            continue
        if _ONLY_DIGITS_RE.fullmatch(text):
            continue
        paragraphs.append(text)
    return paragraphs


def _load_spine_paths(z: zipfile.ZipFile) -> list[str]:
    container_xml = z.read("META-INF/container.xml")
    container_root = ET.fromstring(container_xml)
    rootfile = container_root.find(f".//{{{CONTAINER_NS}}}rootfile")
    if rootfile is None:
        raise RuntimeError("Invalid EPUB: missing rootfile in container.xml")
    opf_path = rootfile.attrib.get("full-path")
    if not opf_path:
        raise RuntimeError("Invalid EPUB: rootfile missing full-path")

    opf_dir = str(PurePosixPath(opf_path).parent)
    opf_xml = z.read(opf_path)
    opf_root = ET.fromstring(opf_xml)

    manifest: dict[str, str] = {}
    for item in opf_root.findall(f".//{{{OPF_NS}}}manifest/{{{OPF_NS}}}item"):
        item_id = item.attrib.get("id")
        href = item.attrib.get("href")
        if item_id and href:
            manifest[item_id] = href

    spine: list[str] = []
    for itemref in opf_root.findall(f".//{{{OPF_NS}}}spine/{{{OPF_NS}}}itemref"):
        idref = itemref.attrib.get("idref")
        if idref:
            spine.append(idref)

    out: list[str] = []
    for idref in spine:
        href = manifest.get(idref)
        if not href:
            continue
        full = str(PurePosixPath(opf_dir, href)) if opf_dir not in {"", "."} else href
        out.append(full)
    return out


def extract_epub_to_txt(
    epub_path: Path,
    out_path: Path,
    *,
    pages: int = 50,
    furigana: bool = False,
    markers: bool = True,
    include_empty_pages: bool = False,
) -> tuple[int, int]:
    if pages <= 0:
        raise ValueError("--pages must be > 0")

    with zipfile.ZipFile(epub_path) as z:
        spine_paths = _load_spine_paths(z)
        limited = spine_paths[:pages]

        out_lines: list[str] = []
        extracted_pages = 0

        for i, spine_item in enumerate(limited, start=1):
            if not (spine_item.lower().endswith(".xhtml") or spine_item.lower().endswith(".html")):
                continue
            if spine_item not in z.namelist():
                continue

            raw = z.read(spine_item).decode("utf-8", errors="replace")
            paragraphs = _extract_paragraphs(raw, furigana=furigana)
            if not paragraphs and not include_empty_pages:
                continue

            extracted_pages += 1
            if markers:
                out_lines.append(f"=== Page {i}: {spine_item} ===")
            out_lines.extend(paragraphs or ["[no text]"])
            out_lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out_lines).rstrip() + "\n", encoding="utf-8")
    return extracted_pages, min(pages, len(spine_paths))


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract Japanese text from an EPUB into a TXT file.")
    parser.add_argument("epub", type=Path, help="Input .epub path")
    parser.add_argument("--pages", type=int, default=50, help="How many spine pages to process (default: 50)")
    parser.add_argument("--out", type=Path, default=None, help="Output .txt path")
    parser.add_argument("--furigana", action="store_true", help="Include ruby readings as （ふりがな）")
    parser.add_argument("--no-markers", action="store_true", help="Do not add page header markers")
    parser.add_argument(
        "--include-empty-pages",
        action="store_true",
        help="Include pages that have no extractable text",
    )
    args = parser.parse_args()

    epub_path: Path = args.epub
    if not epub_path.exists():
        raise SystemExit(f"Not found: {epub_path}")

    if args.out is None:
        safe_stem = re.sub(r"\\s+", "_", epub_path.stem)
        out_path = Path("data/extracted_text") / f"{safe_stem}_first{args.pages}pages.txt"
    else:
        out_path = args.out

    extracted_pages, processed_pages = extract_epub_to_txt(
        epub_path,
        out_path,
        pages=args.pages,
        furigana=bool(args.furigana),
        markers=not bool(args.no_markers),
        include_empty_pages=bool(args.include_empty_pages),
    )
    print(f"Wrote: {out_path} (processed {processed_pages} spine pages, extracted {extracted_pages} text pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
