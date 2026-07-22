#!/usr/bin/env python3
"""Reorder `kanji_db_v2.json` into a best-study sequence and write a new JSON snapshot.

Default strategy: 教育漢字 2020 grade order (1→6) from `data/kyoiku_kanji_2020_by_grade.json`.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"

DEFAULT_DB_FILE = DATA_DIR / "kanji_db_v2.json"
DEFAULT_ORDER_FILE = DATA_DIR / "kyoiku_kanji_2020_by_grade.json"
DEFAULT_OUT_FILE = DATA_DIR / "kanji_db_v2_ordered.json"

STRATEGIES = ("kyoiku_by_grade", "study_v1", "study_global_v1")

NUMBERS_ORDER = [
    "〇",
    "零",
    "一",
    "二",
    "三",
    "四",
    "五",
    "六",
    "七",
    "八",
    "九",
    "十",
    "百",
    "千",
    "万",
    "億",
    "兆",
]
DIRECTIONS_ORDER = ["上", "下", "左", "右", "中"]
WEEKDAYS_ORDER = ["日", "月", "火", "水", "木", "金", "土"]


def _load_json_with_retries(path: Path, *, retries: int = 50, delay_s: float = 0.1) -> dict:
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            last_error = exc
            time.sleep(delay_s)
        except OSError as exc:
            last_error = exc
            time.sleep(delay_s)
    raise RuntimeError(f"Failed to load JSON from {path}") from last_error


def _load_kyoiku_order(order_path: Path) -> tuple[dict[int, list[str]], list[str], dict[str, int]]:
    order_data = _load_json_with_retries(order_path, retries=5, delay_s=0.05)
    by_grade = order_data.get("by_grade")
    if not isinstance(by_grade, dict):
        raise ValueError(f"Invalid order file (missing by_grade): {order_path}")

    by_grade_clean: dict[int, list[str]] = {}
    ordered: list[str] = []
    kanji_to_grade: dict[str, int] = {}
    for grade in range(1, 7):
        lst = by_grade.get(str(grade))
        if not isinstance(lst, list):
            by_grade_clean[grade] = []
            continue
        clean = [k for k in lst if isinstance(k, str) and k]
        by_grade_clean[grade] = clean
        for k in lst:
            if not isinstance(k, str) or not k:
                continue
            ordered.append(k)
            kanji_to_grade[k] = grade
    return by_grade_clean, ordered, kanji_to_grade


def _kata_to_hira(text: str) -> str:
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            out.append(chr(code - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def _normalize_kana_reading(text: str) -> str:
    text = _kata_to_hira(text)
    return (
        text.replace("（", "(")
        .replace("）", ")")
        .replace("・", "")
        .replace(" ", "")
        .replace("\u3000", "")
        .strip()
    )


def _extract_onyomi_candidates(entry: dict) -> list[str]:
    data = entry.get("data")
    if not isinstance(data, dict):
        return []
    readings = data.get("readings")
    if not isinstance(readings, list):
        return []
    out: list[str] = []
    for r in readings:
        if not isinstance(r, dict):
            continue
        t = r.get("type", "")
        if not isinstance(t, str) or "音" not in t:
            continue
        kana = r.get("kana", "")
        if not isinstance(kana, str):
            continue
        kana = _normalize_kana_reading(kana)
        if kana:
            out.append(kana)
    return out


def _study_v1_grade_order(grade_list: list[str], entries: dict[str, dict]) -> list[str]:
    in_grade = [k for k in grade_list if k in entries]
    index = {k: i for i, k in enumerate(in_grade)}

    def take_in_order(candidates: list[str], remaining: set[str]) -> list[str]:
        out: list[str] = []
        for k in candidates:
            if k in remaining:
                out.append(k)
                remaining.remove(k)
        return out

    remaining = set(in_grade)
    out: list[str] = []
    out.extend(take_in_order(NUMBERS_ORDER, remaining))
    out.extend(take_in_order(DIRECTIONS_ORDER, remaining))
    out.extend(take_in_order(WEEKDAYS_ORDER, remaining))

    # Group the rest by most-common on-yomi to keep similar sound roots adjacent.
    candidates_map: dict[str, list[str]] = {}
    freq: dict[str, int] = {}
    for k in remaining:
        cand = _extract_onyomi_candidates(entries.get(k, {}))
        candidates_map[k] = cand
        for c in cand:
            freq[c] = freq.get(c, 0) + 1

    groups: dict[str, list[str]] = {}
    for k in sorted(remaining, key=lambda x: index.get(x, 1_000_000)):
        cand = candidates_map.get(k) or []
        if cand:
            chosen = max(cand, key=lambda c: (freq.get(c, 0), -cand.index(c)))
        else:
            chosen = ""
        groups.setdefault(chosen, []).append(k)

    def group_key_sort(key: str) -> tuple[int, int, str]:
        if not key:
            return (10**9, 10**9, "")
        items = groups.get(key, [])
        earliest = min(index.get(k, 10**9) for k in items) if items else 10**9
        return (-len(items), earliest, key)

    for key in sorted(groups.keys(), key=group_key_sort):
        if not key:
            continue
        items = groups[key]
        items.sort(key=lambda x: index.get(x, 1_000_000))
        out.extend(items)

    # Finally, append items without on-yomi (or missing reading data).
    tail = groups.get("", [])
    tail.sort(key=lambda x: index.get(x, 1_000_000))
    out.extend(tail)

    return out


def _study_global_v1_order(all_list: list[str], entries: dict[str, dict]) -> list[str]:
    in_scope = [k for k in all_list if k in entries]
    index = {k: i for i, k in enumerate(in_scope)}

    def take_in_order(candidates: list[str], remaining: set[str]) -> list[str]:
        out: list[str] = []
        for k in candidates:
            if k in remaining:
                out.append(k)
                remaining.remove(k)
        return out

    remaining = set(in_scope)
    out: list[str] = []
    out.extend(take_in_order(NUMBERS_ORDER, remaining))
    out.extend(take_in_order(DIRECTIONS_ORDER, remaining))
    out.extend(take_in_order(WEEKDAYS_ORDER, remaining))

    candidates_map: dict[str, list[str]] = {}
    freq: dict[str, int] = {}
    for k in remaining:
        cand = _extract_onyomi_candidates(entries.get(k, {}))
        candidates_map[k] = cand
        for c in cand:
            freq[c] = freq.get(c, 0) + 1

    groups: dict[str, list[str]] = {}
    for k in sorted(remaining, key=lambda x: index.get(x, 1_000_000)):
        cand = candidates_map.get(k) or []
        if cand:
            chosen = max(cand, key=lambda c: (freq.get(c, 0), -cand.index(c)))
        else:
            chosen = ""
        groups.setdefault(chosen, []).append(k)

    def entry_grade(kanji: str) -> int:
        entry = entries.get(kanji) or {}
        grade = entry.get("grade") if isinstance(entry, dict) else None
        return int(grade) if isinstance(grade, int) or (isinstance(grade, str) and str(grade).isdigit()) else 999

    def group_key_sort(key: str) -> tuple[int, int, int, str]:
        if not key:
            return (10**9, 10**9, 10**9, "")
        items = groups.get(key, [])
        min_grade = min((entry_grade(k) for k in items), default=999)
        earliest = min((index.get(k, 10**9) for k in items), default=10**9)
        return (min_grade, -len(items), earliest, key)

    for key in sorted(groups.keys(), key=group_key_sort):
        if not key:
            continue
        items = groups[key]
        items.sort(key=lambda x: (entry_grade(x), index.get(x, 1_000_000)))
        out.extend(items)

    tail = groups.get("", [])
    tail.sort(key=lambda x: (entry_grade(x), index.get(x, 1_000_000)))
    out.extend(tail)

    return out


def reorder_db(
    db_path: Path,
    order_path: Path,
    out_path: Path,
    *,
    only_completed: bool = False,
    include_unlisted: bool = True,
    strategy: str = "kyoiku_by_grade",
) -> dict:
    db = _load_json_with_retries(db_path)
    by_grade, ordered_kanji, kanji_to_grade = _load_kyoiku_order(order_path)

    src_kanji = db.get("kanji")
    if not isinstance(src_kanji, dict):
        raise ValueError(f"Invalid DB (missing kanji dict): {db_path}")

    strategy = strategy.strip().lower()
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy}")

    if strategy == "study_v1":
        rebuilt: list[str] = []
        for grade in range(1, 7):
            rebuilt.extend(_study_v1_grade_order(by_grade.get(grade, []), src_kanji))
        ordered_kanji = rebuilt
    elif strategy == "study_global_v1":
        ordered_kanji = _study_global_v1_order(ordered_kanji, src_kanji)

    new_kanji: dict[str, dict] = {}
    seen: set[str] = set()
    for k in ordered_kanji:
        entry = src_kanji.get(k)
        if not isinstance(entry, dict):
            entry = {"grade": kanji_to_grade.get(k, 0), "status": "pending", "data": None}
        if only_completed and entry.get("status") != "completed":
            continue
        new_kanji[k] = entry
        seen.add(k)

    if include_unlisted:
        leftovers = [k for k in src_kanji.keys() if k not in seen]
        leftovers.sort(key=lambda k: (src_kanji.get(k, {}).get("grade", 999), k))
        for k in leftovers:
            entry = src_kanji.get(k)
            if not isinstance(entry, dict):
                continue
            if only_completed and entry.get("status") != "completed":
                continue
            new_kanji[k] = entry

    meta_in = db.get("meta")
    meta = dict(meta_in) if isinstance(meta_in, dict) else {}
    meta["last_updated"] = datetime.now().isoformat()
    meta["total"] = int(meta.get("total") or len(src_kanji))
    meta["completed"] = sum(1 for v in new_kanji.values() if isinstance(v, dict) and v.get("status") == "completed")
    meta["ordered"] = True
    meta["order_source"] = order_path.name
    meta["order_strategy"] = strategy
    if only_completed:
        meta["filtered"] = "only_completed"

    out = {"meta": meta, "kanji": new_kanji}
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_DB_FILE)
    parser.add_argument("--order", type=Path, default=DEFAULT_ORDER_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT_FILE)
    parser.add_argument("--strategy", choices=STRATEGIES, default="kyoiku_by_grade")
    parser.add_argument("--only-completed", action="store_true")
    parser.add_argument("--no-unlisted", action="store_true", help="Drop kanji not present in the order file")
    args = parser.parse_args()

    out = reorder_db(
        args.input,
        args.order,
        args.output,
        only_completed=args.only_completed,
        include_unlisted=not args.no_unlisted,
        strategy=args.strategy,
    )
    meta = out.get("meta") if isinstance(out.get("meta"), dict) else {}
    print(f"Wrote: {args.output}")
    print(f"Completed in snapshot: {meta.get('completed')}/{meta.get('total')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
