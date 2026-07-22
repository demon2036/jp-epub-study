# 批量生成日语汉字记忆 JSON

你是一位资深日语教师，专门给中文母语学习者讲日本汉字。请一次生成这一批汉字的结构化内容：

{kanji_json}

目标：一口气输出整批汉字，减少调用次数；内容要生动形象、短而有用，删除百科式长篇和低价值重复。

## 总要求
1. 只输出纯 JSON，不要 Markdown 代码块，不要解释文字。
2. 顶层必须是：`{"items": [{"kanji": "字", "data": {...}}]}`。
3. `items` 必须按输入汉字顺序完整输出，不要漏字、不要多字。
4. 每个 `data` 使用下面的字段；不要新增 schema 外字段。
5. 每个常用读音必须单独展开：读音场景、带假名标注且整句带普通话表音的例句、锚点词、至少 2 个例词、小结论。
6. `jp_ruby` 只给汉字块标假名，例如 `駅[えき]まで歩[ある]きます。`；不要写成整句读音。
7. 例句整句普通话表音要像普通话教材一样使用声调符号，但声调符号不是普通话词调，而是日语音高提示；罗马字母必须跟日语罗马音一致，不要改写成中文拼音。
8. 同假名异义组要优先服务目标字核心读音；每个保留读音至少有一组 `homophone_groups`，`same_kana` 必须等于对应的 `target_reading`。
9. 场景对照、近义分工、同字扩展各至少 1 组；每组至少 3 项。天然较弱时也给最有教学价值的一组。
10. 低频旧读法不要硬塞进 `readings`；只保留真实常见、值得单独教学的读音。

## 普通话表音规则（极重要）
- `mandarin_pronunciation` 不是普通话词调，也不是中文谐音；它是“日语罗马音 + 普通话声调符号”的音高辅助线。
- 声调符号只表达日语相对音高：`ǎ = 低起/低位`，`ā = 高平/保持高位`，`á = 上扬/升到高位`，`à = 下降/重音下落`。不要把这些符号理解成日语真的有普通话四声。
- 不要机械全部一声，也不要为了“自然节奏”随机混声调；每个符号都必须服务日语音高走向。
- 普通短假名必须优先逐拍空格，方便读者看清每一拍的音高。拗音、长音、拨音可以自然合并，例如 `きょう=kyō`、`しゅう=shū`、`さん=sān`。不要合并成 `tǎbe`、`gǒhān`、`hírū`、`māshità` 这种看不出每拍音高的块。
- 不要把 ん 拆成单独的 n，要并入前一单位，如 `さん=sān`、`にん=nīn`、`ほん=hōn`、`べん=bēn`。
- 粒子必须按实际读音写：`は=wa`、`を=o`、`へ=e`。
- 罗马字母必须保持日语罗马音：`ひ=hi`，不要写 `xi`；`る=ru`，不要写 `lu`；`ご=go`，不要写 `guo`；`し=shi`，不要写 `xi/si`；`ち=chi`，不要写 `qi`。
- 最终输出前必须逐拍校验：先把 `example_sentence.kana` 切成真实发音单位，再确认 `mandarin_pronunciation` 去掉声调符号后逐拍等于日语罗马音。典型错误：`あめ` 的第二拍是 `me`，所以 あめ 应是 à mě（或同等 `a me` 音高写法），不能写成 `à mǎ`/`a ma`。
- 明确示例：`たべました` 写 `tǎ bē mā shī tà`，不要写 `tábe māshità` 或 `tá bè mā shì tá`；`ひるごはんをたべました` 可写 `hī rū gǒ hǎn o tǎ bē mā shī tà`。
- 不要用数字声调，例如不要写 `ha1 xi1`、`mi1 tsu1 tsu1`。

## 每个 data 的 JSON 形状
```json
{
  "summary": "3-5句，概括核心义、主要读音场景、最值得记的组块。",
  "semantic_core": {
    "core": "一句话核心义",
    "extension": "核心义如何扩展到常见义项",
    "root_hint": "有助于记忆的来源/构词线索；不确定就写资料不足/帮助有限"
  },
  "readings": [
    {
      "kana": "假名",
      "romaji": "romaji",
      "type": "音读/训读",
      "usage": "主要使用场景",
      "origin_hint": "来源提示；不确定就写资料不足/不关键",
      "example_sentence": {
        "jp_ruby": "带假名标注的日语例句，如 橋[はし]を渡[わた]ります。",
        "kana": "整句假名读法",
        "mandarin_pronunciation": "整句日语罗马音加普通话声调符号的音高辅助线，如 たべました 写 tǎ bē mā shī tà",
        "zh": "自然中文翻译",
        "note": "这个例句如何帮助记住该读音"
      },
      "anchor": {
        "word": "锚点词",
        "reading": "假名",
        "meaning": "中文含义",
        "hint": "为什么它适合作入口"
      },
      "examples": [
        {"word": "高频例词", "reading": "假名", "meaning": "中文", "link": "和锚点词/读音场景的关系"},
        {"word": "高频例词", "reading": "假名", "meaning": "中文", "link": "和锚点词/读音场景的关系"}
      ],
      "takeaway": "一句可背的小结论"
    }
  ],
  "scenario_contrast_groups": [
    {
      "target_reading": "对应 readings[].kana 或 null",
      "title": "场景标题",
      "why_it_works": "为什么适合放在同一场景记",
      "items": [
        {"word": "词", "reading": "假名", "meaning": "中文", "relation": "关系", "note": "说明"},
        {"word": "词", "reading": "假名", "meaning": "中文", "relation": "关系", "note": "说明"},
        {"word": "词", "reading": "假名", "meaning": "中文", "relation": "关系", "note": "说明"}
      ],
      "takeaway": "一句场景结论"
    }
  ],
  "homophone_groups": [
    {
      "target_reading": "必须等于 readings[].kana",
      "same_kana": "必须等于 target_reading",
      "title": "同假名异义标题",
      "origin_pattern": "同源分化/纯同音碰撞/混合型/音读汇合/汉字借写/不确定",
      "same_kana_reason": "为什么会同音；不确定就明确说不确定",
      "teaching_point": "先看场景/书写/搭配/对象/语域中的哪个轴",
      "why_it_works": "为什么要一起辨析",
      "items": [
        {"word": "词", "reading": "假名", "meaning": "中文", "relation": "关系", "note": "关键区别", "source_note": "来源关系", "memory_hook": "区分钩子"},
        {"word": "词", "reading": "假名", "meaning": "中文", "relation": "关系", "note": "关键区别", "source_note": "来源关系", "memory_hook": "区分钩子"},
        {"word": "词", "reading": "假名", "meaning": "中文", "relation": "关系", "note": "关键区别", "source_note": "来源关系", "memory_hook": "区分钩子"}
      ],
      "takeaway": "一句辨析口诀"
    }
  ],
  "near_synonym_groups": [
    {
      "title": "近义分工标题",
      "why_it_works": "中文像近义，但日语怎样分工",
      "items": [
        {"word": "词", "reading": "假名", "meaning": "中文", "relation": "关系", "note": "边界"},
        {"word": "词", "reading": "假名", "meaning": "中文", "relation": "关系", "note": "边界"},
        {"word": "词", "reading": "假名", "meaning": "中文", "relation": "关系", "note": "边界"}
      ],
      "takeaway": "一句使用边界"
    }
  ],
  "same_kanji_expansion_groups": [
    {
      "target_reading": "对应 readings[].kana 或 null",
      "title": "同字扩展标题",
      "why_it_works": "这个汉字如何从核心义扩展到这组词",
      "items": [
        {"word": "含目标汉字的词", "reading": "假名", "meaning": "中文", "relation": "关系", "note": "扩展说明"},
        {"word": "含目标汉字的词", "reading": "假名", "meaning": "中文", "relation": "关系", "note": "扩展说明"},
        {"word": "含目标汉字的词", "reading": "假名", "meaning": "中文", "relation": "关系", "note": "扩展说明"}
      ],
      "takeaway": "一句扩展规律"
    }
  ],
  "pitfalls": ["易混点1", "易混点2"],
  "memory_chain": "把核心义、锚点词、例句和组块串成一段自然可背的记忆链。"
}
```

现在输出整批 JSON。
