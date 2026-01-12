"""将结构化 JSON 数据渲染为 Markdown"""

def render(kanji: str, data: dict) -> str:
    """将单个汉字的结构化数据渲染为 Markdown"""
    lines = [f"# {kanji}\n"]

    # 读音总览
    lines.append("## 读音总览\n")
    lines.append("| 读法 | 假名 | 罗马字 | 类型 |")
    lines.append("|------|------|--------|------|")
    for r in data["readings"]:
        lines.append(f"| {r['kana']} | {r['kana']} | {r['romaji']} | {r['type']} |")

    # 释义
    lines.append(f"\n## 释义\n\n{data['summary']}\n")

    # 读音详解
    lines.append("## 读音详解\n")
    for i, r in enumerate(data["readings"], 1):
        lines.append(f"### 读法{i}：{r['kana']}（{r['romaji']}）\n")
        lines.append(f"**类型**：{r['type']}\n")
        lines.append(f"**来源**：{r['origin']}\n")
        lines.append(f"**使用场景**：{r['usage']}\n")

        # 锚点词
        a = r["anchor"]
        lines.append("**核心词汇记忆**：")
        lines.append(f"记住「{a['word']}（{a['reading']}）」= {a['meaning']}，{a['hint']}\n")

        # 例词表格
        lines.append("| 词汇 | 读音 | 含义 | 记忆关联 |")
        lines.append("|------|------|------|----------|")
        lines.append(f"| {a['word']} | {a['reading']} | {a['meaning']} | 锚点词 |")
        for ex in r["examples"]:
            lines.append(f"| {ex['word']} | {ex['reading']} | {ex['meaning']} | {ex['link']} |")
        lines.append("")

    # 字源
    ety = data["etymology"]
    lines.append(f"## 字源\n\n「{kanji}」是{ety['type']}。{ety['explanation']}\n")

    # 构件拆解
    lines.append("## 构件拆解\n")
    for c in data["components"]:
        lines.append(f"**{c['part']}**：{c['meaning']} → {c['extension']}\n")

    # 组合逻辑
    parts = " + ".join(c["part"] for c in data["components"])
    lines.append("## 组合逻辑\n")
    lines.append("```")
    lines.append(parts)
    lines.append("    ↓")
    lines.append(data["composition"])
    lines.append("```\n")

    # 文化背景
    lines.append(f"## 文化背景\n\n{data['culture']}\n")

    # 总结记忆
    lines.append(f"## 总结记忆\n\n> {data['memory_chain']}")

    return "\n".join(lines)
