#!/usr/bin/env python3
"""Audit and repair Japanese-romaji pronunciation aids in kanji memory JSON."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import re
from pathlib import Path


TONE_TO_MARK = {
    "a": "āáǎà",
    "e": "ēéěè",
    "i": "īíǐì",
    "o": "ōóǒò",
    "u": "ūúǔù",
    "ü": "ǖǘǚǜ",
}
MARK_TO_BASE_TONE = {
    mark: (base, tone)
    for base, marks in TONE_TO_MARK.items()
    for tone, mark in enumerate(marks, start=1)
}

PUNCT_RE = re.compile(r"^[\s。、，,.!?！？「」『』（）()]+|[\s。、，,.!?！？「」『』（）()]+$")
HIRAGANA_RE = re.compile(r"[ぁ-ゖー]+")

BASE_ROMAJI = {
    "あ": "a",
    "い": "i",
    "う": "u",
    "え": "e",
    "お": "o",
    "か": "ka",
    "き": "ki",
    "く": "ku",
    "け": "ke",
    "こ": "ko",
    "さ": "sa",
    "し": "shi",
    "す": "su",
    "せ": "se",
    "そ": "so",
    "た": "ta",
    "ち": "chi",
    "つ": "tsu",
    "て": "te",
    "と": "to",
    "な": "na",
    "に": "ni",
    "ぬ": "nu",
    "ね": "ne",
    "の": "no",
    "は": "ha",
    "ひ": "hi",
    "ふ": "fu",
    "へ": "he",
    "ほ": "ho",
    "ま": "ma",
    "み": "mi",
    "む": "mu",
    "め": "me",
    "も": "mo",
    "や": "ya",
    "ゆ": "yu",
    "よ": "yo",
    "ら": "ra",
    "り": "ri",
    "る": "ru",
    "れ": "re",
    "ろ": "ro",
    "わ": "wa",
    "ゐ": "i",
    "ゑ": "e",
    "を": "o",
    "が": "ga",
    "ぎ": "gi",
    "ぐ": "gu",
    "げ": "ge",
    "ご": "go",
    "ざ": "za",
    "じ": "ji",
    "ず": "zu",
    "ぜ": "ze",
    "ぞ": "zo",
    "だ": "da",
    "ぢ": "ji",
    "づ": "zu",
    "で": "de",
    "ど": "do",
    "ば": "ba",
    "び": "bi",
    "ぶ": "bu",
    "べ": "be",
    "ぼ": "bo",
    "ぱ": "pa",
    "ぴ": "pi",
    "ぷ": "pu",
    "ぺ": "pe",
    "ぽ": "po",
    "ぁ": "a",
    "ぃ": "i",
    "ぅ": "u",
    "ぇ": "e",
    "ぉ": "o",
    "ゔ": "vu",
}

DIGRAPH_PREFIX = {
    "き": "ky",
    "ぎ": "gy",
    "し": "sh",
    "じ": "j",
    "ち": "ch",
    "に": "ny",
    "ひ": "hy",
    "び": "by",
    "ぴ": "py",
    "み": "my",
    "り": "ry",
}
DIGRAPH_SUFFIX = {"ゃ": "a", "ゅ": "u", "ょ": "o"}


@dataclass(frozen=True)
class PronunciationAuditResult:
    corrected: str
    issues: list[str]


@dataclass(frozen=True)
class RomajiUnit:
    preferred: str
    allowed: set[str]
    optional: bool = False


def _kata_to_hira(text: str) -> str:
    chars: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            chars.append(chr(code - 0x60))
        else:
            chars.append(ch)
    return "".join(chars)


def _strip_token_punctuation(token: str) -> str:
    return PUNCT_RE.sub("", token)


def _plain_romaji(token: str) -> str:
    out: list[str] = []
    for ch in token.lower().replace("’", "'"):
        if ch in MARK_TO_BASE_TONE:
            out.append(MARK_TO_BASE_TONE[ch][0])
        elif ch in {"ā", "á", "ǎ", "à"}:
            out.append("a")
        elif ch in {"ē", "é", "ě", "è"}:
            out.append("e")
        elif ch in {"ī", "í", "ǐ", "ì"}:
            out.append("i")
        elif ch in {"ō", "ó", "ǒ", "ò"}:
            out.append("o")
        elif ch in {"ū", "ú", "ǔ", "ù"}:
            out.append("u")
        elif "a" <= ch <= "z" or ch == "ü":
            out.append(ch)
    return "".join(out)


def _first_tone(token: str) -> int | None:
    for ch in token.lower():
        if ch in MARK_TO_BASE_TONE:
            return MARK_TO_BASE_TONE[ch][1]
    return None


def _tone_vowel_index(token: str) -> int | None:
    lower = token.lower()
    for vowel in ("a", "e"):
        idx = lower.find(vowel)
        if idx != -1:
            return idx
    idx = lower.find("ou")
    if idx != -1:
        return idx
    for idx in range(len(token) - 1, -1, -1):
        if lower[idx] in "iouü":
            return idx
    return None


def _apply_tone(token: str, tone: int | None) -> str:
    if tone is None or tone < 1 or tone > 4:
        return token
    idx = _tone_vowel_index(token)
    if idx is None:
        return token
    vowel = token[idx]
    marked = TONE_TO_MARK[vowel.lower()][tone - 1]
    if vowel.isupper():
        marked = marked.upper()
    return token[:idx] + marked + token[idx + 1 :]


def _split_marked_token_by_plain_parts(token: str, parts: list[str]) -> list[str] | None:
    if not parts or _plain_romaji(token) != "".join(parts):
        return None

    segments: list[str] = []
    char_idx = 0
    for part in parts:
        plain = ""
        chars: list[str] = []
        while char_idx < len(token) and len(plain) < len(part):
            ch = token[char_idx]
            char_idx += 1
            ch_plain = _plain_romaji(ch)
            if ch_plain and not part.startswith(plain + ch_plain):
                return None
            plain += ch_plain
            chars.append(ch)
        if plain != part:
            return None
        segments.append("".join(chars))

    rest = token[char_idx:]
    if _plain_romaji(rest):
        return None
    if rest and segments:
        segments[-1] += rest
    return segments


def _token_options(token: str, source_kana: str = "") -> set[str]:
    options = {token}
    if source_kana == "は":
        options.add("wa")
    elif source_kana == "へ":
        options.add("e")
    return options


def _insertion_token(unit: RomajiUnit) -> str:
    if unit.preferred == "ha" and "wa" in unit.allowed:
        return "wa"
    if unit.preferred == "he" and "e" in unit.allowed:
        return "e"
    return unit.preferred


def kana_to_romaji_units(kana: str) -> list[RomajiUnit]:
    """Return preferred romaji token plus acceptable alternatives for each kana unit."""
    text = _kata_to_hira(str(kana or ""))
    units: list[RomajiUnit] = []
    geminate = False
    i = 0
    while i < len(text):
        ch = text[i]
        if not HIRAGANA_RE.fullmatch(ch):
            i += 1
            continue
        if ch == "っ":
            geminate = True
            i += 1
            continue
        if ch == "ー":
            i += 1
            continue
        if ch == "ん":
            if units:
                previous = units[-1]
                units[-1] = RomajiUnit(
                    previous.preferred + "n",
                    {option + "n" for option in previous.allowed},
                    previous.optional,
                )
            else:
                units.append(RomajiUnit("n", {"n"}))
            i += 1
            continue

        if i + 1 < len(text) and text[i + 1] in DIGRAPH_SUFFIX and ch in DIGRAPH_PREFIX:
            token = DIGRAPH_PREFIX[ch] + DIGRAPH_SUFFIX[text[i + 1]]
            source = ch + text[i + 1]
            i += 2
        else:
            token = BASE_ROMAJI.get(ch)
            source = ch
            i += 1
        if not token:
            continue

        if geminate:
            token = (token[0] if token[0] not in "aeiou" else "") + token
            geminate = False

        optional = False
        allowed = _token_options(token, source)
        if units and source in {"い", "う"}:
            previous = units[-1]
            can_merge = False
            if source == "う" and any(option.endswith(("o", "u")) for option in previous.allowed):
                can_merge = True
                if any(option.endswith("o") for option in previous.allowed):
                    allowed.add("o")
            elif source == "い" and any(option.endswith("e") for option in previous.allowed):
                can_merge = True
                allowed.add("e")
            if can_merge:
                optional = True
                units[-1] = RomajiUnit(
                    previous.preferred,
                    previous.allowed | {option + token for option in previous.allowed},
                    previous.optional,
                )

        units.append(RomajiUnit(token, allowed, optional))
    return units


def kana_to_romaji_options(kana: str) -> list[tuple[str, set[str]]]:
    return [
        (unit.preferred, unit.allowed)
        for unit in kana_to_romaji_units(kana)
        if not unit.optional
    ]


def _pronunciation_tokens(pronunciation: str) -> tuple[list[str], str]:
    raw_tokens = str(pronunciation or "").split()
    cleaned = [_strip_token_punctuation(token) for token in raw_tokens]
    cleaned = [token for token in cleaned if token]
    trailing = ""
    stripped = str(pronunciation or "").rstrip()
    if stripped and stripped[-1] in "。、，,.!?！？":
        trailing = stripped[-1]
    return cleaned, trailing


def correct_sentence_pronunciation(kana: str, pronunciation: str) -> PronunciationAuditResult:
    expected = kana_to_romaji_units(kana)
    actual_tokens, trailing = _pronunciation_tokens(pronunciation)

    aligned = _align_pronunciation_tokens(expected, actual_tokens)
    if aligned is None:
        return PronunciationAuditResult(
            corrected=pronunciation,
            issues=[
                f"token_count_mismatch expected={_unit_count_range(expected)} actual={len(actual_tokens)}"
            ],
        )

    corrected_tokens, issues = aligned
    corrected = " ".join(corrected_tokens)
    if trailing and not corrected.endswith(trailing):
        corrected += trailing
    return PronunciationAuditResult(corrected=corrected, issues=issues)


def _unit_count_range(units: list[RomajiUnit]) -> str:
    required = sum(1 for unit in units if not unit.optional)
    return str(required) if required == len(units) else f"{required}-{len(units)}"


def _align_pronunciation_tokens(
    expected: list[RomajiUnit],
    actual_tokens: list[str],
) -> tuple[list[str], list[str]] | None:
    from functools import lru_cache

    def combined_candidates(start: int, actual_plain: str) -> list[tuple[int, list[str]]]:
        if not actual_plain:
            return []
        candidates: list[tuple[int, list[str]]] = []
        max_parts = 6

        def visit_candidate(i: int, parts: list[str], plain: str) -> None:
            if len(parts) >= 2 and plain == actual_plain:
                candidates.append((i, list(parts)))
                return
            if i >= len(expected) or len(parts) >= max_parts or len(plain) >= len(actual_plain):
                return

            unit = expected[i]
            if unit.optional:
                visit_candidate(i + 1, parts, plain)

            options = [unit.preferred] + sorted(unit.allowed - {unit.preferred})
            for option in options:
                next_plain = plain + option
                if actual_plain.startswith(next_plain):
                    parts.append(option)
                    visit_candidate(i + 1, parts, next_plain)
                    parts.pop()

        visit_candidate(start, [], "")
        return candidates

    @lru_cache(maxsize=None)
    def visit(i: int, j: int) -> tuple[int, tuple[str, ...], tuple[str, ...]] | None:
        if i == len(expected) and j == len(actual_tokens):
            return 0, (), ()
        if i == len(expected):
            actual = actual_tokens[j]
            tail = visit(i, j + 1)
            if tail is None:
                return None
            tail_cost, tail_tokens, tail_issues = tail
            issue = f"extra_token_{j + 1}_removed actual={_plain_romaji(actual) or actual}"
            return 1 + tail_cost, tail_tokens, (issue,) + tail_issues

        unit = expected[i]
        best: tuple[int, tuple[str, ...], tuple[str, ...]] | None = None
        if unit.optional:
            best = visit(i + 1, j)
        elif j <= len(actual_tokens):
            tail = visit(i + 1, j)
            if tail is not None:
                tail_cost, tail_tokens, tail_issues = tail
                inserted = _insertion_token(unit)
                issue = f"missing_token_{j + 1}_inserted expected={inserted}"
                best = (
                    1 + tail_cost,
                    (inserted,) + tail_tokens,
                    (issue,) + tail_issues,
                )

        if j < len(actual_tokens):
            actual = actual_tokens[j]
            actual_plain = _plain_romaji(actual)
            if actual_plain in unit.allowed:
                candidate_head = actual
                issue = None
                cost = 0
            elif not unit.optional:
                candidate_head = _apply_tone(unit.preferred, _first_tone(actual))
                issue = (
                    f"token_{j + 1}_romaji_mismatch "
                    f"expected={unit.preferred} actual={actual_plain or actual}"
                )
                cost = 1
            else:
                candidate_head = ""
                issue = None
                cost = 1000

            if cost < 1000:
                tail = visit(i + 1, j + 1)
                if tail is not None:
                    tail_cost, tail_tokens, tail_issues = tail
                    candidate = (
                        cost + tail_cost,
                        (candidate_head,) + tail_tokens,
                        ((issue,) if issue else ()) + tail_issues,
                    )
                    if best is None or candidate[0] < best[0]:
                        best = candidate

            for next_i, parts in combined_candidates(i, actual_plain):
                split_tokens = _split_marked_token_by_plain_parts(actual, parts)
                if not split_tokens:
                    continue
                tail = visit(next_i, j + 1)
                if tail is None:
                    continue
                tail_cost, tail_tokens, tail_issues = tail
                issue = (
                    f"combined_token_{j + 1}_split "
                    f"expected={'/'.join(parts)} actual={actual_plain or actual}"
                )
                candidate = (
                    1 + tail_cost,
                    tuple(split_tokens) + tail_tokens,
                    (issue,) + tail_issues,
                )
                if best is None or candidate[0] < best[0]:
                    best = candidate

            tail = visit(i, j + 1)
            if tail is not None:
                tail_cost, tail_tokens, tail_issues = tail
                issue = f"extra_token_{j + 1}_removed actual={actual_plain or actual}"
                candidate = (
                    1 + tail_cost,
                    tail_tokens,
                    (issue,) + tail_issues,
                )
                if best is None or candidate[0] < best[0]:
                    best = candidate
        return best

    result = visit(0, 0)
    if result is None:
        return None
    _, tokens, issues = result
    return list(tokens), list(issues)


def audit_sentence_pronunciation(kana: str, pronunciation: str) -> PronunciationAuditResult:
    return correct_sentence_pronunciation(kana, pronunciation)


def repair_memory_payload_pronunciations(payload: dict, *, kanji: str = "") -> list[dict]:
    changes: list[dict] = []
    for reading in payload.get("readings", []) or []:
        if not isinstance(reading, dict):
            continue
        sentence = reading.get("example_sentence")
        if not isinstance(sentence, dict):
            continue
        kana = str(sentence.get("kana") or "").strip()
        pronunciation = str(sentence.get("mandarin_pronunciation") or "").strip()
        if not kana or not pronunciation:
            continue
        result = correct_sentence_pronunciation(kana, pronunciation)
        changed = result.corrected != pronunciation
        if changed:
            sentence["mandarin_pronunciation"] = result.corrected
        if result.issues:
            changes.append(
                {
                    "kanji": kanji,
                    "reading": str(reading.get("kana") or ""),
                    "kana": kana,
                    "before": pronunciation,
                    "after": result.corrected,
                    "changed": changed,
                    "issues": result.issues,
                }
            )
    return changes


def _iter_payloads(document: dict):
    if isinstance(document.get("items"), list):
        for item in document["items"]:
            if isinstance(item, dict) and isinstance(item.get("data"), dict):
                yield str(item.get("kanji") or ""), item["data"]
        return
    kanji_map = document.get("kanji")
    if isinstance(kanji_map, dict):
        for kanji, entry in kanji_map.items():
            if isinstance(entry, dict) and isinstance(entry.get("data"), dict):
                yield str(kanji), entry["data"]


def repair_file(path: Path, *, fix: bool = False) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    changes: list[dict] = []
    for kanji, payload in _iter_payloads(document):
        changes.extend(repair_memory_payload_pronunciations(payload, kanji=kanji))
    if fix and changes:
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    changed = [item for item in changes if item.get("changed")]
    unresolved = [item for item in changes if not item.get("changed")]
    return {
        "path": str(path),
        "issues": changes,
        "changes": changed,
        "change_count": len(changed),
        "issue_count": len(changes),
        "unresolved_count": len(unresolved),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--fix", action="store_true", help="Write repairs back to each file")
    parser.add_argument("--report", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    reports = [repair_file(path, fix=args.fix) for path in args.paths]
    output = {
        "files": reports,
        "total_changes": sum(item["change_count"] for item in reports),
        "total_issues": sum(item["issue_count"] for item in reports),
        "total_unresolved": sum(item["unresolved_count"] for item in reports),
    }
    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text)
    return 1 if output["total_issues"] and not args.fix else 0


if __name__ == "__main__":
    raise SystemExit(main())
