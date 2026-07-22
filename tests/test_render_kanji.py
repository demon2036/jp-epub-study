from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_kanji import _numbered_pinyin_to_tone_marks, render  # noqa: E402


class RenderKanjiTest(unittest.TestCase):
    def test_prompts_define_mandarin_tone_marks_as_japanese_pitch_guides(self):
        prompt_paths = [
            ROOT / "scripts" / "prompts" / "kanji_explain_json.md",
            ROOT / "scripts" / "prompts" / "kanji_explain_batch_json.md",
            ROOT / "scripts" / "prompts" / "codex_kanji_batch_instructions.md",
        ]
        for path in prompt_paths:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("声调符号不是普通话词调", text)
                self.assertIn("ǎ = 低起/低位", text)
                self.assertIn("à = 下降/重音下落", text)
                self.assertIn("不要把 ん 拆成单独的 n", text)
                self.assertIn("たべました", text)
                self.assertIn("tǎ bē mā shī tà", text)
                self.assertIn("不要合并成 `tǎbe`、`gǒhān`、`hírū`、`māshità`", text)
                self.assertIn("普通短假名必须优先逐拍空格", text)
                self.assertIn("最终输出前必须逐拍校验", text)
                self.assertIn("あめ 应是 à mě", text)
                self.assertNotIn("让中文母语者读起来有自然节奏", text)

    def test_numbered_pinyin_is_converted_to_textbook_tone_marks(self):
        self.assertEqual(
            _numbered_pinyin_to_tone_marks("san1 nin1 dei1 yi1 ji1 ma1 si1"),
            "sān nīn dēi yī jī mā sī",
        )
        self.assertEqual(_numbered_pinyin_to_tone_marks("sa1 n1 ni1 n1"), "sān nīn")
        self.assertEqual(_numbered_pinyin_to_tone_marks("sā n nī n"), "sān nīn")
        self.assertEqual(_numbered_pinyin_to_tone_marks("na1 mi2 mo3 li4"), "nā mí mǒ lì")

    def test_sentence_pronunciation_uses_curated_text_not_mechanical_fallback(self):
        output = render(
            "三",
            {
                "summary": "三就是数量三，先用三人记住さん。",
                "semantic_core": {
                    "core": "数量三",
                    "extension": "扩展到人数、日期、形状等三的组合。",
                    "root_hint": "三条横线直接表示数量三。",
                },
                "readings": [
                    {
                        "kana": "さん",
                        "romaji": "san",
                        "type": "音读",
                        "usage": "人数、月份、形状等汉语词。",
                        "origin_hint": "汉语音读，直接按数字音记。",
                        "example_sentence": {
                            "jp_ruby": "三[さん]人[にん]で昼[ひる]ご飯[はん]を食[た]べました。",
                            "kana": "さんにんでひるごはんをたべました。",
                            "mandarin_pronunciation": "sān nín de hī rū gǒ hǎn o tǎ bē mā shī tà。",
                            "zh": "三个人一起吃了午饭。",
                            "note": "三人固定读さんにん。",
                        },
                        "anchor": {
                            "word": "三人",
                            "reading": "さんにん",
                            "meaning": "三个人",
                            "hint": "人数入口词。",
                        },
                        "examples": [
                            {"word": "三月", "reading": "さんがつ", "meaning": "三月", "link": "月份直接用さん。"},
                            {"word": "三角", "reading": "さんかく", "meaning": "三角", "link": "汉语词里读さん。"},
                        ],
                        "takeaway": "看到三加汉语词，先试さん。",
                    }
                ],
                "scenario_contrast_groups": [],
                "homophone_groups": [],
                "near_synonym_groups": [],
                "same_kanji_expansion_groups": [],
                "pitfalls": [],
                "memory_chain": "先记三人さんにん，再扩展到三月和三角。",
            },
        )

        self.assertIn("普通话表音：sān nín de hī rū gǒ hǎn o tǎ bē mā shī tà。", output)
        self.assertNotIn("xī lū guō", output)

    def test_render_legacy_schema(self):
        output = render(
            "日",
            {
                "summary": "核心含义是太阳与日期。",
                "readings": [
                    {
                        "kana": "にち",
                        "romaji": "nichi",
                        "type": "音读",
                        "origin": "汉音来源",
                        "usage": "日期和抽象时间词",
                        "anchor": {
                            "word": "毎日",
                            "reading": "まいにち",
                            "meaning": "每天",
                            "hint": "高频到几乎天天都能见到",
                        },
                        "examples": [
                            {
                                "word": "日曜日",
                                "reading": "にちようび",
                                "meaning": "星期日",
                                "link": "和日期、时间场景相连",
                            }
                        ],
                    }
                ],
                "culture": "和太阳历法密切相关",
                "memory_chain": "太阳升起就是一天，所以毎日最容易带出にち。",
            },
        )

        self.assertIn("## 读音详解", output)
        self.assertIn("毎日", output)
        self.assertIn("## 总结记忆", output)

    def test_render_memory_schema(self):
        output = render(
            "並",
            {
                "summary": "核心是排成一列、放在同一层级，所以常引申为普通等级。",
                "semantic_core": {
                    "core": "排在一起、处于同一排或同一等级",
                    "extension": "从并列扩展到普通、标准、不突出",
                    "root_hint": "和记忆有关的是“排在普通那一档”的感觉，不必强求古语考据",
                },
                "readings": [
                    {
                        "kana": "なみ",
                        "romaji": "nami",
                        "type": "训读",
                        "usage": "表示普通、标准档位",
                        "origin_hint": "与并排、同列的语感相关",
                        "example_sentence": {
                            "jp_ruby": "並[なみ]盛[も]りをください。",
                            "kana": "なみもりをください。",
                            "mandarin_pronunciation": "námi móri o kudasai。",
                            "zh": "请给我普通份。",
                            "note": "菜单场景里直接把 なみ 记成普通档。",
                        },
                        "anchor": {
                            "word": "並盛り",
                            "reading": "なみもり",
                            "meaning": "普通份",
                            "hint": "菜单里最常见的标准档位",
                        },
                        "examples": [
                            {
                                "word": "人並み",
                                "reading": "ひとなみ",
                                "meaning": "一般水平，和别人差不多",
                                "link": "把“同一档位”的感觉扩展到能力、生活水准。",
                            },
                            {
                                "word": "並の",
                                "reading": "なみの",
                                "meaning": "普通的，一般的",
                                "link": "保留“并列后落在标准档”的语感。",
                            },
                        ],
                        "takeaway": "看到菜单、等级、程度时，先把 なみ 记成“标准档、一般水平”。",
                    },
                    {
                        "kana": "ならぶ",
                        "romaji": "narabu",
                        "type": "训读",
                        "usage": "表示自己排起来、并排存在",
                        "origin_hint": "最贴近这个字“并排成列”的本义。",
                        "example_sentence": {
                            "jp_ruby": "店[みせ]の前[まえ]に人[ひと]が並[なら]んでいます。",
                            "kana": "みせのまえにひとがならんでいます。",
                            "mandarin_pronunciation": "míse no máe ni híto ga narán de imasu。",
                            "zh": "店门前有人在排队。",
                            "note": "排队画面最容易带出 ならぶ。",
                        },
                        "anchor": {
                            "word": "並ぶ",
                            "reading": "ならぶ",
                            "meaning": "排列，排队",
                            "hint": "它直接把“自己进入同一排”的感觉露出来。",
                        },
                        "examples": [
                            {
                                "word": "横に並ぶ",
                                "reading": "よこにならぶ",
                                "meaning": "并排站着",
                                "link": "保留空间上的并列感。",
                            },
                            {
                                "word": "店が並ぶ",
                                "reading": "みせがならぶ",
                                "meaning": "店铺排成一排",
                                "link": "从人排队扩展到事物并列出现。",
                            },
                        ],
                        "takeaway": "ならぶ 先记“自己进入同一排”，再扩展到并列出现。",
                    }
                ],
                "scenario_contrast_groups": [
                    {
                        "target_reading": "なみ",
                        "title": "菜单份量对照",
                        "why_it_works": "在同一菜单里直接形成选择关系",
                        "items": [
                            {
                                "word": "並盛り",
                                "reading": "なみもり",
                                "meaning": "普通份",
                                "relation": "目标词",
                                "note": "标准档位",
                            },
                            {
                                "word": "大盛り",
                                "reading": "おおもり",
                                "meaning": "大份",
                                "relation": "场景对照",
                                "note": "和普通份直接对比",
                            },
                            {
                                "word": "特盛り",
                                "reading": "とくもり",
                                "meaning": "特大份",
                                "relation": "等级对照",
                                "note": "比大份更高一档",
                            },
                        ],
                        "takeaway": "并不是复杂词源，而是菜单里“普通那一档”的位置感。",
                    }
                ],
                "homophone_groups": [
                    {
                        "same_kana": "なみ",
                        "title": "同音不同字",
                        "origin_pattern": "混合型",
                        "same_kana_reason": "並和並み属于同一语义家族，波则是另一条词，只是同读为なみ。",
                        "teaching_point": "先看场景是在档位评价还是自然界波浪，再决定是哪一个なみ。",
                        "why_it_works": "把声音相同但字义不同的词放在一起避免误认",
                        "items": [
                            {
                                "word": "並",
                                "reading": "なみ",
                                "meaning": "普通",
                                "relation": "目标词",
                                "note": "强调档位和并列",
                                "source_note": "和並み共享“同列、同档”的语义核。",
                                "memory_hook": "菜单、等级、一般水准时优先想到这一组。",
                            },
                            {
                                "word": "波",
                                "reading": "なみ",
                                "meaning": "波浪",
                                "relation": "同音异义",
                                "note": "是波形，不是普通等级",
                                "source_note": "不是“普通档位”这条语义线，只是同音碰撞。",
                                "memory_hook": "一旦出现海、水面、起伏画面，就切到波浪的なみ。",
                            },
                            {
                                "word": "並み",
                                "reading": "なみ",
                                "meaning": "一般水平",
                                "relation": "同音扩展",
                                "note": "保留普通水准的语感",
                                "source_note": "和並同源，保留“同一档位”的感觉。",
                                "memory_hook": "评价水平、程度时常是这一项。",
                            },
                        ],
                        "takeaway": "听到なみ先看场景：菜单等级还是波浪形象。",
                    }
                ],
                "near_synonym_groups": [
                    {
                        "title": "普通等级词的边界",
                        "why_it_works": "中文都像普通，但语感和使用位置不同",
                        "items": [
                            {
                                "word": "並",
                                "reading": "なみ",
                                "meaning": "普通档",
                                "relation": "目标词",
                                "note": "常放在等级或档位里",
                            },
                            {
                                "word": "普通",
                                "reading": "ふつう",
                                "meaning": "普通",
                                "relation": "近义词",
                                "note": "更中性、更通用",
                            },
                            {
                                "word": "一般",
                                "reading": "いっぱん",
                                "meaning": "一般",
                                "relation": "近义词",
                                "note": "更像分类或范围",
                            },
                        ],
                        "takeaway": "並更像档位标签，普通更通用，一般更像类别说明。",
                    }
                ],
                "same_kanji_expansion_groups": [
                    {
                        "target_reading": "なみ",
                        "title": "从并列到普通",
                        "why_it_works": "同一个字先有并排感，再扩展出普通档位感",
                        "items": [
                            {
                                "word": "並ぶ",
                                "reading": "ならぶ",
                                "meaning": "排列",
                                "relation": "核心义",
                                "note": "最直接体现并排",
                            },
                            {
                                "word": "並行",
                                "reading": "へいこう",
                                "meaning": "并行",
                                "relation": "引申义",
                                "note": "保持并列前进",
                            },
                            {
                                "word": "並盛り",
                                "reading": "なみもり",
                                "meaning": "普通份",
                                "relation": "档位扩展",
                                "note": "从同列扩展到标准档位",
                            },
                        ],
                        "takeaway": "先记并排，再记标准档位，就能把並的主要感觉串起来。",
                    }
                ],
                "pitfalls": [
                    "不要把並一律理解成普通，它本来有并列感。",
                    "なみ在不同字里可能完全不是同一意思。",
                ],
                "memory_chain": "並先是并排，再变成同一档位，所以菜单里的並盛り最适合做入口。",
            },
        )

        self.assertIn("## 核心义", output)
        self.assertIn("## 场景对照组", output)
        self.assertIn("## 同假名异义组", output)
        self.assertIn("## 近义分工组", output)
        self.assertIn("## 同字扩展组", output)
        self.assertIn("並盛り", output)
        self.assertIn("## 读音详解", output)
        self.assertIn("人並み", output)
        self.assertIn("横に並ぶ", output)
        self.assertIn("读音记忆", output)
        self.assertIn("为什么会同音", output)
        self.assertIn("同音类型", output)
        self.assertIn("教学重点", output)
        self.assertIn("来源关系", output)
        self.assertIn("记忆钩子", output)
        self.assertNotIn("普通话近似", output)
        self.assertNotIn("普通话近似发音", output)
        self.assertNotIn("| 读法 | 罗马字 | 普通话近似 | 类型 | 使用场景 |", output)
        self.assertIn("| 读法 | 罗马字 | 类型 | 使用场景 |", output)
        self.assertIn("## 例句与发音", output)
        self.assertIn("普通话表音：námi móri o kudasai。", output)
        self.assertIn("普通话表音：míse no máe ni híto ga narán de imasu。", output)
        self.assertIn("<ruby>並<rt>なみ</rt></ruby>", output)
        self.assertIn("请给我普通份。", output)
        self.assertNotIn("na1 mi1", output)


if __name__ == "__main__":
    unittest.main()
