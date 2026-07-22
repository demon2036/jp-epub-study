from __future__ import annotations

import re


JP_RUBY_PATTERN = re.compile(
    "^(?:[^\\[\\]]|[\u3400-\u9fff\uf900-\ufaff\U00020000-\U0002EBEF々〆ヵヶ]+\\[[ぁ-ゖァ-ヺー]+\\])+$"
)
PINYIN_TONE_MARKS = set("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜĀÁǍÀĒÉĚÈĪÍǏÌŌÓǑÒŪÚǓÙǕǗǙǛńňǹḿŃŇǸḾ")


def _kata_to_hira(text: str) -> str:
    chars: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            chars.append(chr(code - 0x60))
        else:
            chars.append(ch)
    return "".join(chars)


def normalize_kana(text: str) -> str:
    return _kata_to_hira(str(text or "").strip()).replace(" ", "")


def _has_textbook_tone_marks(value: str) -> bool:
    return any(ch in PINYIN_TONE_MARKS for ch in value) and not any(ch.isdigit() for ch in value)


def _validate_reading_learning_aids(reading: dict, raw_kana: str) -> str | None:
    if "mandarin_pronunciation" in reading:
        return f"unexpected_reading_mandarin_pronunciation: {raw_kana}"

    sentence = reading.get("example_sentence")
    if not isinstance(sentence, dict):
        return f"missing_example_sentence: {raw_kana}"
    jp_ruby = str(sentence.get("jp_ruby") or "").strip()
    if not jp_ruby or not JP_RUBY_PATTERN.fullmatch(jp_ruby):
        return f"invalid_example_sentence_jp_ruby: {raw_kana}"
    sentence_pronunciation = str(sentence.get("mandarin_pronunciation") or "").strip()
    if not sentence_pronunciation or not _has_textbook_tone_marks(sentence_pronunciation):
        return f"invalid_example_sentence_mandarin_pronunciation: {raw_kana}"
    for key in ("kana", "zh", "note"):
        if not str(sentence.get(key) or "").strip():
            return f"missing_example_sentence_{key}: {raw_kana}"
    return None


def validate_memory_payload(payload: dict) -> str | None:
    readings = payload.get("readings")
    homophone_groups = payload.get("homophone_groups")
    if not isinstance(readings, list) or not isinstance(homophone_groups, list):
        return None

    reading_lookup: dict[str, str] = {}
    reading_order: list[str] = []
    for reading in readings:
        if not isinstance(reading, dict):
            continue
        raw_kana = str(reading.get("kana") or "").strip()
        normalized = normalize_kana(raw_kana)
        if not raw_kana or not normalized:
            continue
        learning_aid_error = _validate_reading_learning_aids(reading, raw_kana)
        if learning_aid_error:
            return learning_aid_error
        if normalized not in reading_lookup:
            reading_lookup[normalized] = raw_kana
            reading_order.append(normalized)

    covered: set[str] = set()
    for group in homophone_groups:
        if not isinstance(group, dict):
            continue
        raw_target = str(group.get("target_reading") or "").strip()
        raw_same = str(group.get("same_kana") or "").strip()
        normalized_target = normalize_kana(raw_target)
        normalized_same = normalize_kana(raw_same)

        if raw_target and normalized_target not in reading_lookup:
            return f"unknown_homophone_target_reading: {raw_target}"
        if raw_target and normalized_same != normalized_target:
            return f"same_kana_must_match_target_reading: {raw_target} -> {raw_same}"
        if normalized_target:
            covered.add(normalized_target)

    missing = [reading_lookup[item] for item in reading_order if item not in covered]
    if missing:
        return "missing_homophone_groups_for_readings: " + ", ".join(missing)
    return None
