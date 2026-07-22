#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET


XHTML_NS = "http://www.w3.org/1999/xhtml"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NS = "http://www.idpf.org/2007/opf"

END_PUNCT = {"。"}
CLOSERS = set("」』）)]】］〕〉》”’」』")

_ONLY_KANA_RE = re.compile(r"^[\u3040-\u309f\u30a0-\u30ffー・]+$")


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

        base = "".join(base_parts)
        reading = "".join(rt_parts)
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


def _extract_segments(xhtml: str, *, furigana: bool) -> list[str]:
    root = ET.fromstring(xhtml)
    out: list[str] = []
    for p in root.findall(f".//{{{XHTML_NS}}}p"):
        text = _extract_inline_text(p, furigana=furigana)
        text = text.replace("\u00a0", " ")
        text = text.strip()
        if not text:
            continue
        if _ONLY_DIGITS_RE.fullmatch(text):
            continue
        out.append(text)
    return out


def _load_spine_paths(z: zipfile.ZipFile) -> tuple[str, list[str]]:
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
    return opf_path, out


def _split_complete_sentences(text: str) -> tuple[list[str], str]:
    completed: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        buf.append(ch)
        if ch in END_PUNCT:
            j = i + 1
            while j < len(text) and text[j] in CLOSERS:
                buf.append(text[j])
                j += 1
            sentence = "".join(buf).strip()
            if sentence:
                completed.append(sentence)
            buf = []
            i = j
            continue
        i += 1
    remainder = "".join(buf)
    return completed, remainder


def _normalize_segment(text: str) -> str:
    text = text.replace("\n", "")
    return text.strip()


def _maybe_init_tokenizer():
    try:
        from janome.tokenizer import Tokenizer  # type: ignore
    except Exception:
        return None
    return Tokenizer()


def _kata_to_hira(text: str) -> str:
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            out.append(chr(code - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def _best_reading_kana(*, surface: str, reading_kata: str) -> str:
    if reading_kata and reading_kata != "*":
        return _kata_to_hira(reading_kata)
    if _ONLY_KANA_RE.fullmatch(surface or ""):
        return _kata_to_hira(surface)
    return ""


def _tokenize_sentence(tokenizer, sentence: str) -> list[dict]:
    if tokenizer is None:
        return []
    tokens = []
    for token in tokenizer.tokenize(sentence):
        reading = getattr(token, "reading", "") or ""
        base = getattr(token, "base_form", "") or ""
        pos = getattr(token, "part_of_speech", "") or ""
        infl_type = getattr(token, "infl_type", "") or ""
        infl_form = getattr(token, "infl_form", "") or ""
        surface = token.surface
        pos_parts = [p for p in (pos.split(",") if pos else []) if p]
        tokens.append(
            {
                "surface": surface,
                "base": base,
                "pos": pos,
                "reading": "" if reading == "*" else reading,
                "reading_kana": _best_reading_kana(surface=surface, reading_kata=reading),
                "pos_major": pos_parts[0] if pos_parts else "",
                "pos_sub": pos_parts[1] if len(pos_parts) > 1 else "",
                "infl_type": "" if infl_type == "*" else infl_type,
                "infl_form": "" if infl_form == "*" else infl_form,
                "meaning_zh": None,
                "grammar_note": None,
            }
        )
    return tokens


def extract_epub_sentences(
    epub_path: Path,
    out_path: Path,
    *,
    pages: int = 50,
    furigana: bool = False,
    tokenize: bool = True,
    merge_segments: bool = False,
    include_spine: str | None = None,
    exclude_spine: str | None = None,
) -> dict:
    if pages <= 0:
        raise ValueError("--pages must be > 0")

    tokenizer = _maybe_init_tokenizer() if tokenize else None
    tokenize = bool(tokenize and tokenizer is not None)

    with zipfile.ZipFile(epub_path) as z:
        opf_path, spine_paths = _load_spine_paths(z)
        limited = spine_paths[:pages]

        sentences: list[dict] = []
        sentence_id = 0
        carry = ""

        include_re = re.compile(include_spine) if include_spine else None
        exclude_re = re.compile(exclude_spine) if exclude_spine else None

        for spine_index, spine_item in enumerate(limited, start=1):
            if not (spine_item.lower().endswith(".xhtml") or spine_item.lower().endswith(".html")):
                continue
            if spine_item not in z.namelist():
                continue
            if include_re and not include_re.search(spine_item):
                continue
            if exclude_re and exclude_re.search(spine_item):
                continue

            raw = z.read(spine_item).decode("utf-8", errors="replace")
            segments = _extract_segments(raw, furigana=furigana)

            for segment_index, segment in enumerate(segments, start=1):
                segment = _normalize_segment(segment)
                if not segment:
                    continue

                if merge_segments:
                    carry += segment
                    completed, carry = _split_complete_sentences(carry)
                    if not completed and carry and segment and segment[-1] in CLOSERS:
                        completed, carry = [carry], ""
                else:
                    completed, remainder = _split_complete_sentences(segment)
                    completed = [s for s in completed if s.strip()]
                    tail = remainder.strip()
                    if tail:
                        completed.append(tail)
                    carry = ""

                if not completed:
                    continue

                for sentence_index, jp in enumerate(completed, start=1):
                    jp = jp.strip()
                    if not jp:
                        continue
                    sentence_id += 1
                    entry = {
                        "id": sentence_id,
                        "spine_index": spine_index,
                        "spine_path": spine_item,
                        "segment_index": segment_index,
                        "sentence_index": sentence_index,
                        "jp": jp,
                        "zh": None,
                        "words": [],
                        "grammar": [],
                    }
                    if tokenize:
                        entry["tokens"] = _tokenize_sentence(tokenizer, jp)
                    sentences.append(entry)

        if merge_segments:
            tail = carry.strip()
            if tail:
                sentence_id += 1
                entry = {
                    "id": sentence_id,
                    "spine_index": min(pages, len(spine_paths)),
                    "spine_path": limited[-1] if limited else "",
                    "segment_index": 0,
                    "sentence_index": 1,
                    "jp": tail,
                    "zh": None,
                    "words": [],
                    "grammar": [],
                }
                if tokenize:
                    entry["tokens"] = _tokenize_sentence(tokenizer, tail)
                sentences.append(entry)

    payload = {
        "meta": {
            "source_epub": str(epub_path),
            "source_opf": opf_path,
            "spine_pages_total": len(spine_paths),
            "spine_pages_requested": pages,
            "spine_pages_processed": min(pages, len(spine_paths)),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "language": "ja",
            "furigana_inlined": bool(furigana),
            "tokenizer": "janome" if tokenize else None,
            "merge_segments": bool(merge_segments),
            "include_spine_regex": include_spine,
            "exclude_spine_regex": exclude_spine,
            "note": "Sentences are split by 。 (and optionally end-of-segment).",
        },
        "sentences": sentences,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract sentences from an EPUB into a JSON file.")
    parser.add_argument("epub", type=Path, help="Input .epub path")
    parser.add_argument("--pages", type=int, default=50, help="How many spine pages to process (default: 50)")
    parser.add_argument("--out", type=Path, default=None, help="Output .json path")
    parser.add_argument("--furigana", action="store_true", help="Inline ruby readings as （ふりがな） in jp")
    parser.add_argument("--no-tokenize", action="store_true", help="Do not run Janome tokenization")
    parser.add_argument("--include-spine-regex", type=str, default=None, help="Only process matching spine_path")
    parser.add_argument("--exclude-spine-regex", type=str, default=None, help="Skip matching spine_path")
    parser.add_argument(
        "--merge-segments",
        action="store_true",
        help="Merge consecutive <p> segments until a terminator (use with caution)",
    )
    args = parser.parse_args()

    epub_path: Path = args.epub
    if not epub_path.exists():
        raise SystemExit(f"Not found: {epub_path}")

    if args.out is None:
        safe_stem = re.sub(r"\\s+", "_", epub_path.stem)
        out_path = Path("data/extracted_text") / f"{safe_stem}_first{args.pages}pages_sentences.json"
    else:
        out_path = args.out

    payload = extract_epub_sentences(
        epub_path,
        out_path,
        pages=args.pages,
        furigana=bool(args.furigana),
        tokenize=not bool(args.no_tokenize),
        merge_segments=bool(args.merge_segments),
        include_spine=args.include_spine_regex,
        exclude_spine=args.exclude_spine_regex,
    )
    print(f"Wrote: {out_path} (sentences: {len(payload['sentences'])})")
    if not bool(args.no_tokenize) and payload.get("meta", {}).get("tokenizer") is None:
        print("Note: Janome not installed; tokens omitted. Install with: pip install -r requirements.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
