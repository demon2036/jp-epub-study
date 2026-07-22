"""Render kanji explanation JSON as Markdown."""

from __future__ import annotations

import html
import re


KANJI_RUBY_RE = re.compile(r"([一-龯々〆ヵヶ]+)\[([ぁ-ゖァ-ヺー]+)\]")
NUMBERED_PINYIN_RE = re.compile(r"([A-Za-züÜvV:]+)([1-5])")
PINYIN_TONES = {
    "a": "āáǎà",
    "e": "ēéěè",
    "i": "īíǐì",
    "o": "ōóǒò",
    "u": "ūúǔù",
    "ü": "ǖǘǚǜ",
}


def _escape(text: object) -> str:
    return html.escape(str(text or ""), quote=False)


def _ruby_text_to_html(text: object) -> str:
    escaped = _escape(text)
    return KANJI_RUBY_RE.sub(r"<ruby>\1<rt>\2</rt></ruby>", escaped)


def _normalize_pinyin_vowel_spelling(syllable: str) -> str:
    return syllable.replace("u:", "ü").replace("U:", "Ü").replace("v", "ü").replace("V", "Ü")


def _tone_vowel_index(syllable: str) -> int | None:
    lower = syllable.lower()
    for vowel in ("a", "e"):
        idx = lower.find(vowel)
        if idx != -1:
            return idx
    idx = lower.find("ou")
    if idx != -1:
        return idx
    for idx in range(len(syllable) - 1, -1, -1):
        if lower[idx] in "iouü":
            return idx
    return None


def _mark_pinyin_syllable(syllable: str, tone: str) -> str:
    normalized = _normalize_pinyin_vowel_spelling(syllable)
    if tone == "5":
        return normalized
    idx = _tone_vowel_index(normalized)
    if idx is None:
        return normalized
    vowel = normalized[idx]
    marked = PINYIN_TONES[vowel.lower()][int(tone) - 1]
    if vowel.isupper():
        marked = marked.upper()
    return normalized[:idx] + marked + normalized[idx + 1 :]


def _numbered_pinyin_to_tone_marks(text: object) -> str:
    value = re.sub(
        r"\b([A-Za-züÜvV:]+)([1-5])\s+n\2\b",
        r"\1n\2",
        str(text or ""),
    )
    value = NUMBERED_PINYIN_RE.sub(
        lambda match: _mark_pinyin_syllable(match.group(1), match.group(2)),
        value,
    )
    return re.sub(
        r"\b([A-Za-z]*[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ])\s+n\b",
        r"\1n",
        value,
    )


def _sentence_pronunciation(sentence: dict) -> str:
    return _numbered_pinyin_to_tone_marks(
        sentence.get("mandarin_pronunciation")
        or sentence.get("pinyin")
        or sentence.get("pinyin_tone")
        or ""
    ).strip()


def _append_example_sentence(lines: list[str], reading: dict) -> None:
    sentence = reading.get("example_sentence") or reading.get("sentence")
    if not isinstance(sentence, dict):
        return

    jp_ruby = str(sentence.get("jp_ruby") or sentence.get("ruby") or "").strip()
    kana = str(sentence.get("kana") or "").strip()
    pronunciation = _sentence_pronunciation(sentence)
    zh = str(sentence.get("zh") or sentence.get("meaning") or "").strip()
    note = str(sentence.get("note") or "").strip()
    if not (jp_ruby or kana or pronunciation or zh or note):
        return

    lines.append("#### 例句与发音\n")
    lines.append('<div class="reading-example">')
    if jp_ruby:
        lines.append(f'<div class="jp-example">{_ruby_text_to_html(jp_ruby)}</div>')
    if kana:
        lines.append(f'<div class="kana-line">假名：{_escape(kana)}</div>')
    if pronunciation:
        lines.append(f'<div class="mandarin-line">普通话表音：{_escape(pronunciation)}</div>')
    if zh:
        lines.append(f'<div class="zh-line">中文：{_escape(zh)}</div>')
    if note:
        lines.append(f'<div class="mini-note">{_escape(note)}</div>')
    lines.append("</div>\n")


def _is_memory_schema(data: dict) -> bool:
    return "semantic_core" in data


def _append_group_table(lines: list[str], groups: list[dict], empty_text: str) -> None:
    if not groups:
        lines.append(f"{empty_text}\n")
        return

    for idx, group in enumerate(groups, start=1):
        title = str(group.get("title") or f"组 {idx}")
        lines.append(f"### {title}\n")
        why = str(group.get("why_it_works") or "")
        if why:
            lines.append(f"**为什么这样记**：{why}\n")
        same_kana = group.get("same_kana")
        if same_kana:
            lines.append(f"**共同假名**：{same_kana}\n")
        target_reading = group.get("target_reading")
        if target_reading:
            lines.append(f"**对应读音**：{target_reading}\n")

        lines.append("| 词 | 读音 | 含义 | 关系 | 说明 |")
        lines.append("|----|------|------|------|------|")
        for item in group.get("items", []):
            lines.append(
                f"| {item.get('word', '')} | {item.get('reading', '')} | {item.get('meaning', '')} | "
                f"{item.get('relation', '')} | {item.get('note', '')} |"
            )
        takeaway = str(group.get("takeaway") or "")
        if takeaway:
            lines.append(f"\n**记忆结论**：{takeaway}\n")


def _append_homophone_groups(lines: list[str], groups: list[dict], empty_text: str) -> None:
    if not groups:
        lines.append(f"{empty_text}\n")
        return

    for idx, group in enumerate(groups, start=1):
        title = str(group.get("title") or f"组 {idx}")
        lines.append(f"### {title}\n")
        same_kana = str(group.get("same_kana") or "")
        if same_kana:
            lines.append(f"**共同假名**：{same_kana}\n")
        origin_pattern = str(group.get("origin_pattern") or "")
        if origin_pattern:
            lines.append(f"**同音类型**：{origin_pattern}\n")
        same_kana_reason = str(group.get("same_kana_reason") or "")
        if same_kana_reason:
            lines.append(f"**为什么会同音**：{same_kana_reason}\n")
        teaching_point = str(group.get("teaching_point") or "")
        if teaching_point:
            lines.append(f"**教学重点**：{teaching_point}\n")
        why = str(group.get("why_it_works") or "")
        if why:
            lines.append(f"**为什么这样记**：{why}\n")

        lines.append("| 词 | 读音 | 含义 | 关系 | 关键区别 | 来源关系 | 记忆钩子 |")
        lines.append("|----|------|------|------|----------|----------|----------|")
        for item in group.get("items", []):
            lines.append(
                f"| {item.get('word', '')} | {item.get('reading', '')} | {item.get('meaning', '')} | "
                f"{item.get('relation', '')} | {item.get('note', '')} | {item.get('source_note', '')} | "
                f"{item.get('memory_hook', '')} |"
            )
        takeaway = str(group.get("takeaway") or "")
        if takeaway:
            lines.append(f"\n**记忆结论**：{takeaway}\n")


def _render_memory_schema(kanji: str, data: dict) -> str:
    lines = [f"# {kanji}\n"]

    lines.append("## 释义总览\n")
    lines.append(f"{data.get('summary', '')}\n")

    core = data.get("semantic_core") or {}
    lines.append("## 核心义\n")
    lines.append(f"**核心**：{core.get('core', '')}\n")
    lines.append(f"**扩展**：{core.get('extension', '')}\n")
    lines.append(f"**词根/来源提示**：{core.get('root_hint', '')}\n")

    readings = data.get("readings", [])
    lines.append("## 读音总览\n")
    lines.append("| 读法 | 罗马字 | 类型 | 使用场景 |")
    lines.append("|------|--------|------|----------|")
    for reading in readings:
        lines.append(
            f"| {reading.get('kana', '')} | {reading.get('romaji', '')} | {reading.get('type', '')} | "
            f"{reading.get('usage', '')} |"
        )

    lines.append("\n## 读音详解\n")
    for idx, reading in enumerate(readings, start=1):
        anchor = reading.get("anchor") or {}
        lines.append(f"### 读法{idx}：{reading.get('kana', '')}（{reading.get('romaji', '')}）\n")
        lines.append(f"**类型**：{reading.get('type', '')}\n")
        lines.append(f"**使用场景**：{reading.get('usage', '')}\n")
        lines.append(f"**来源提示**：{reading.get('origin_hint', '')}\n")
        lines.append(
            f"**锚点词**：{anchor.get('word', '')}（{anchor.get('reading', '')}）= "
            f"{anchor.get('meaning', '')}；{anchor.get('hint', '')}\n"
        )
        _append_example_sentence(lines, reading)
        lines.append("| 词汇 | 读音 | 含义 | 记忆关联 |")
        lines.append("|------|------|------|----------|")
        lines.append(
            f"| {anchor.get('word', '')} | {anchor.get('reading', '')} | {anchor.get('meaning', '')} | 锚点词 |"
        )
        for example in reading.get("examples", []):
            lines.append(
                f"| {example.get('word', '')} | {example.get('reading', '')} | {example.get('meaning', '')} | "
                f"{example.get('link', '')} |"
            )
        takeaway = str(reading.get("takeaway") or "")
        if takeaway:
            lines.append(f"\n**读音记忆**：{takeaway}\n")

    lines.append("## 场景对照组\n")
    _append_group_table(lines, data.get("scenario_contrast_groups", []), "（没有特别高价值的场景对照组）")

    lines.append("## 同假名异义组\n")
    _append_homophone_groups(lines, data.get("homophone_groups", []), "（没有特别高价值的同假名异义组）")

    lines.append("## 近义分工组\n")
    _append_group_table(lines, data.get("near_synonym_groups", []), "（没有特别高价值的近义分工组）")

    lines.append("## 同字扩展组\n")
    _append_group_table(lines, data.get("same_kanji_expansion_groups", []), "（没有特别高价值的同字扩展组）")

    pitfalls = data.get("pitfalls") or []
    lines.append("## 易混点\n")
    if pitfalls:
        for item in pitfalls:
            lines.append(f"- {item}")
        lines.append("")
    else:
        lines.append("（暂无）\n")

    lines.append(f"## 总结记忆\n\n> {data.get('memory_chain', '')}")
    return "\n".join(lines)


def _render_legacy_schema(kanji: str, data: dict) -> str:
    lines = [f"# {kanji}\n"]

    lines.append("## 读音总览\n")
    lines.append("| 读法 | 假名 | 罗马字 | 类型 |")
    lines.append("|------|------|--------|------|")
    for reading in data["readings"]:
        lines.append(
            f"| {reading.get('kana', '')} | {reading.get('kana', '')} | {reading.get('romaji', '')} | "
            f"{reading.get('type', '')} |"
        )

    lines.append(f"\n## 释义\n\n{data.get('summary', '')}\n")
    lines.append("## 读音详解\n")

    for idx, reading in enumerate(data["readings"], start=1):
        lines.append(f"### 读法{idx}：{reading.get('kana', '')}（{reading.get('romaji', '')}）\n")
        lines.append(f"**类型**：{reading.get('type', '')}\n")
        lines.append(f"**来源**：{reading.get('origin', '')}\n")
        lines.append(f"**使用场景**：{reading.get('usage', '')}\n")

        anchor = reading.get("anchor") or {}
        lines.append("**核心词汇记忆**：")
        lines.append(
            f"记住「{anchor.get('word', '')}（{anchor.get('reading', '')}）」= {anchor.get('meaning', '')}，"
            f"{anchor.get('hint', '')}\n"
        )

        lines.append("| 词汇 | 读音 | 含义 | 记忆关联 |")
        lines.append("|------|------|------|----------|")
        lines.append(
            f"| {anchor.get('word', '')} | {anchor.get('reading', '')} | {anchor.get('meaning', '')} | 锚点词 |"
        )
        for example in reading.get("examples", []):
            lines.append(
                f"| {example.get('word', '')} | {example.get('reading', '')} | {example.get('meaning', '')} | "
                f"{example.get('link', '')} |"
            )
        lines.append("")

    lines.append(f"## 文化背景\n\n{data.get('culture', '')}\n")
    lines.append(f"## 总结记忆\n\n> {data.get('memory_chain', '')}")
    return "\n".join(lines)


def render(kanji: str, data: dict) -> str:
    """Render structured data for one kanji as Markdown."""
    if _is_memory_schema(data):
        return _render_memory_schema(kanji, data)
    return _render_legacy_schema(kanji, data)
