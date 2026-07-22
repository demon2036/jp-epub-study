from pathlib import Path
import json
import os
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import batch_generate_v3 as batch_generate_v3  # noqa: E402


class BatchGenerateV3CodexConfigTest(unittest.TestCase):
    def test_build_codex_cmd_uses_default_cliproxy_config(self):
        with mock.patch.dict(
            os.environ,
            {"CODEX_ARGS": "", "CODEX_ARGS_JSON": "", "CODEX_MODEL": ""},
            clear=False,
        ):
            cmd = batch_generate_v3._build_codex_cmd("-")

        self.assertIn("-c", cmd)
        self.assertIn('model_provider="cliproxyapi"', cmd)
        self.assertIn('model_providers.cliproxyapi.base_url="http://127.0.0.1:8317/v1"', cmd)
        self.assertIn('model_instructions_file="scripts/prompts/codex_matrix_exec_instructions.md"', cmd)

    def test_load_codex_runtime_configs_from_env_json(self):
        with mock.patch.dict(
            os.environ,
            {
                "CODEX_MULTI_CONFIGS_JSON": json.dumps(
                    [
                        {
                            "name": "local",
                            "base_url": "http://127.0.0.1:8317/v1",
                            "api_key_env": "LOCAL_KEY",
                        },
                        {
                            "name": "vip1",
                            "base_url": "https://api-vip.codex-for.me/v1",
                            "api_key_env": "VIP_KEY_1",
                        },
                    ]
                ),
                "LOCAL_KEY": "local-secret",
                "VIP_KEY_1": "vip-secret-1",
            },
            clear=False,
        ):
            configs = batch_generate_v3._load_codex_runtime_configs()

        self.assertEqual(
            [(item.name, item.base_url, item.api_key) for item in configs],
            [
                ("local", "http://127.0.0.1:8317/v1", "local-secret"),
                ("vip1", "https://api-vip.codex-for.me/v1", "vip-secret-1"),
            ],
        )

    def test_build_codex_cmd_for_runtime_config_uses_minimal_crs_overrides(self):
        runtime_config = batch_generate_v3.CodexRuntimeConfig(
            name="vip1",
            base_url="https://api-vip.codex-for.me/v1",
            api_key="vip-secret-1",
        )

        cmd = batch_generate_v3._build_codex_cmd("-", runtime_config=runtime_config)

        self.assertEqual(Path(cmd[0]).name, "codex")
        self.assertIn("--yolo", cmd)
        self.assertIn("exec", cmd)
        self.assertIn('model_provider="crs"', cmd)
        self.assertIn('model="gpt-5.5"', cmd)
        self.assertIn('model_reasoning_effort="xhigh"', cmd)
        self.assertIn('model_reasoning_summary="auto"', cmd)
        self.assertIn("show_raw_agent_reasoning=true", cmd)
        self.assertIn("disable_response_storage=true", cmd)
        self.assertIn('model_providers.crs.base_url="https://api-vip.codex-for.me/v1"', cmd)
        self.assertIn('model_providers.crs.env_key="CRS_OAI_KEY"', cmd)
        self.assertIn('model_providers.crs.supports_websockets=true', cmd)
        self.assertIn("model_providers.crs.websocket_connect_timeout_ms=15000", cmd)
        self.assertIn(
            'model_instructions_file="scripts/prompts/codex_kanji_batch_instructions.md"',
            cmd,
        )
        self.assertNotIn('model_instructions_file="scripts/prompts/codex_matrix_exec_instructions.md"', cmd)

    def test_default_codex_timeout_is_one_hour(self):
        self.assertEqual(batch_generate_v3._default_timeout_for_backend("codex"), 3600)

    def test_allocate_codex_worker_counts_spreads_remainder_to_front(self):
        self.assertEqual(batch_generate_v3._allocate_codex_worker_counts(30, 3), [10, 10, 10])
        self.assertEqual(batch_generate_v3._allocate_codex_worker_counts(2, 3), [1, 1, 0])
        self.assertEqual(batch_generate_v3._allocate_codex_worker_counts(5, 3), [2, 2, 1])

    def test_default_runtime_config_uses_crs_env_when_no_multi_config_is_set(self):
        with mock.patch.dict(
            os.environ,
            {
                "CODEX_MULTI_CONFIGS_JSON": "",
                "CRS_OAI_KEY": "local-secret",
                "CODEX_CRS_BASE_URL": "http://127.0.0.1:18325/v1",
            },
            clear=False,
        ):
            config = batch_generate_v3._default_codex_runtime_config()

        self.assertEqual(
            (config.name, config.base_url, config.api_key),
            ("crs", "http://127.0.0.1:18325/v1", "local-secret"),
        )

    def test_load_batch_prompt_requests_ten_kanji_as_one_json_collection(self):
        prompt = batch_generate_v3.load_batch_prompt(["三", "五"])

        self.assertIn('"kanji": ["三", "五"]', prompt)
        self.assertIn('"items"', prompt)
        self.assertIn("example_sentence", prompt)
        self.assertIn("mandarin_pronunciation", prompt)
        self.assertIn("音高辅助线", prompt)
        self.assertIn("tǎ bē mā shī tà", prompt)
        self.assertIn("不要写 `xi`", prompt)
        self.assertNotIn('"mandarin_pronunciation": {\n        "pinyin"', prompt)

    def test_parse_batch_payload_returns_requested_kanji_map(self):
        payload = {
            "summary": "核心义足够长，用来通过测试。",
            "semantic_core": {
                "core": "核心义",
                "extension": "扩展说明足够长",
                "root_hint": "来源提示足够长",
            },
            "readings": [
                {
                    "kana": "さん",
                    "romaji": "san",
                    "type": "音读",
                    "usage": "复合词和数量表达",
                    "origin_hint": "音读线索即可",
                    "example_sentence": {
                        "jp_ruby": "三[さん]人[にん]で行[い]きます。",
                        "kana": "さんにんでいきます。",
                        "mandarin_pronunciation": "sān nīn dē ī kī mā sū",
                        "zh": "三个人一起去。",
                        "note": "三人体现 さん 接人数词。",
                    },
                    "anchor": {
                        "word": "三人",
                        "reading": "さんにん",
                        "meaning": "三个人",
                        "hint": "人数词入口",
                    },
                    "examples": [
                        {"word": "三回", "reading": "さんかい", "meaning": "三次", "link": "数量词场景"},
                        {"word": "三月", "reading": "さんがつ", "meaning": "三月", "link": "月份场景"},
                    ],
                    "takeaway": "复合词里先想 さん。",
                }
            ],
            "scenario_contrast_groups": [
                {
                    "target_reading": "さん",
                    "title": "人数场景",
                    "why_it_works": "同一人数场景里好记",
                    "items": [
                        {"word": "一人", "reading": "ひとり", "meaning": "一个人", "relation": "对照", "note": "特殊读法"},
                        {"word": "二人", "reading": "ふたり", "meaning": "两个人", "relation": "对照", "note": "特殊读法"},
                        {"word": "三人", "reading": "さんにん", "meaning": "三个人", "relation": "目标词", "note": "回到さん"},
                    ],
                    "takeaway": "三人开始走さん。",
                }
            ],
            "homophone_groups": [
                {
                    "target_reading": "さん",
                    "same_kana": "さん",
                    "title": "さん同音",
                    "origin_pattern": "音读汇合",
                    "same_kana_reason": "多个汉字音读汇到さん，靠字和场景区分。",
                    "teaching_point": "先看汉字书写和搭配。",
                    "why_it_works": "同音容易混，需要放一起。",
                    "items": [
                        {
                            "word": "三",
                            "reading": "さん",
                            "meaning": "三",
                            "relation": "目标词",
                            "note": "数量三",
                            "source_note": "目标汉字的音读。",
                            "memory_hook": "数字场景想到三。",
                        },
                        {
                            "word": "山",
                            "reading": "さん",
                            "meaning": "山",
                            "relation": "同音异义",
                            "note": "自然物",
                            "source_note": "不同汉字的音读汇合。",
                            "memory_hook": "山地自然场景想到山。",
                        },
                        {
                            "word": "酸",
                            "reading": "さん",
                            "meaning": "酸",
                            "relation": "同音异义",
                            "note": "味道或化学",
                            "source_note": "不同汉字的音读汇合。",
                            "memory_hook": "味道化学想到酸。",
                        },
                    ],
                    "takeaway": "さん先看字，数字就是三。",
                }
            ],
            "near_synonym_groups": [
                {
                    "title": "数量表达",
                    "why_it_works": "中文都像三但日语用法不同",
                    "items": [
                        {"word": "三", "reading": "さん", "meaning": "三", "relation": "目标词", "note": "复合词"},
                        {"word": "三つ", "reading": "みっつ", "meaning": "三个", "relation": "近义", "note": "泛数量"},
                        {"word": "第三", "reading": "だいさん", "meaning": "第三", "relation": "序数", "note": "顺序"},
                    ],
                    "takeaway": "数量、泛数、序数分开。",
                }
            ],
            "same_kanji_expansion_groups": [
                {
                    "target_reading": "さん",
                    "title": "三的扩展",
                    "why_it_works": "从数量三扩展到形状和倍数",
                    "items": [
                        {"word": "三人", "reading": "さんにん", "meaning": "三人", "relation": "核心义", "note": "数量"},
                        {"word": "三角", "reading": "さんかく", "meaning": "三角", "relation": "形状", "note": "三条边"},
                        {"word": "三倍", "reading": "さんばい", "meaning": "三倍", "relation": "倍率", "note": "三倍数量"},
                    ],
                    "takeaway": "三能扩到形状和倍数。",
                }
            ],
            "pitfalls": ["不要混さん和みっつ。", "三人从さんにん开始。"],
            "memory_chain": "先记三是数量三，再用三人抓さん。",
        }
        response = json.dumps(
            {
                "items": [
                    {"kanji": "三", "data": payload},
                    {"kanji": "五", "data": {**payload, "summary": "五也用同样结构通过测试。"}},
                ]
            },
            ensure_ascii=False,
        )

        parsed, error = batch_generate_v3.parse_batch_response(response, ["三", "五"])

        self.assertEqual(error, "")
        self.assertEqual(sorted(parsed), ["三", "五"])
        self.assertEqual(parsed["三"]["readings"][0]["example_sentence"]["jp_ruby"], "三[さん]人[にん]で行[い]きます。")

    def test_parse_batch_payload_repairs_sentence_pronunciation_romaji(self):
        payload = {
            "summary": "雨は天気の雨を中心に覚える字で、あめが入口です。",
            "semantic_core": {
                "core": "空から降る雨",
                "extension": "雨天や雨具など天気関連に広がる",
                "root_hint": "雨粒の形を思い出すと覚えやすい",
            },
            "readings": [
                {
                    "kana": "あめ",
                    "romaji": "ame",
                    "type": "訓読",
                    "usage": "日常の天気表現",
                    "origin_hint": "和語として日常語で使う",
                    "example_sentence": {
                        "jp_ruby": "雨[あめ]が降[ふ]ります。",
                        "kana": "あめがふります。",
                        "mandarin_pronunciation": "à mǎ gǎ fǔ rī mā sù",
                        "zh": "下雨。",
                        "note": "雨が降るであめを覚える。",
                    },
                    "anchor": {
                        "word": "雨",
                        "reading": "あめ",
                        "meaning": "雨",
                        "hint": "天气里最直接的入口",
                    },
                    "examples": [
                        {"word": "大雨", "reading": "おおあめ", "meaning": "大雨", "link": "雨量が多い"},
                        {"word": "雨上がり", "reading": "あめあがり", "meaning": "雨后", "link": "雨が止んだ後"},
                    ],
                    "takeaway": "天气里的雨先读あめ。",
                }
            ],
            "scenario_contrast_groups": [
                {
                    "target_reading": "あめ",
                    "title": "天气场景",
                    "why_it_works": "天气词放在一起好记",
                    "items": [
                        {"word": "雨", "reading": "あめ", "meaning": "雨", "relation": "目标词", "note": "天气"},
                        {"word": "雪", "reading": "ゆき", "meaning": "雪", "relation": "对照", "note": "天气"},
                        {"word": "風", "reading": "かぜ", "meaning": "风", "relation": "对照", "note": "天气"},
                    ],
                    "takeaway": "天气名词一起记。",
                }
            ],
            "homophone_groups": [
                {
                    "target_reading": "あめ",
                    "same_kana": "あめ",
                    "title": "あめ同音",
                    "origin_pattern": "純同音碰撞",
                    "same_kana_reason": "雨和飴来源不同但同音。",
                    "teaching_point": "先看天气还是食物。",
                    "why_it_works": "同音高频，必须区分。",
                    "items": [
                        {
                            "word": "雨",
                            "reading": "あめ",
                            "meaning": "雨",
                            "relation": "目标词",
                            "note": "天气",
                            "source_note": "目标和语词",
                            "memory_hook": "天气就写雨",
                        },
                        {
                            "word": "飴",
                            "reading": "あめ",
                            "meaning": "糖",
                            "relation": "同音异义",
                            "note": "食物",
                            "source_note": "不同词",
                            "memory_hook": "吃的糖写飴",
                        },
                        {
                            "word": "あめ",
                            "reading": "あめ",
                            "meaning": "假名写法",
                            "relation": "同读异表记",
                            "note": "儿童书常见",
                            "source_note": "表记差异",
                            "memory_hook": "无汉字靠语境",
                        },
                    ],
                    "takeaway": "あめ先看天气还是糖。",
                }
            ],
            "near_synonym_groups": [
                {
                    "title": "雨量表达",
                    "why_it_works": "中文都像雨，日语按强度分",
                    "items": [
                        {"word": "雨", "reading": "あめ", "meaning": "雨", "relation": "目标词", "note": "一般雨"},
                        {"word": "大雨", "reading": "おおあめ", "meaning": "大雨", "relation": "强度", "note": "雨量大"},
                        {"word": "小雨", "reading": "こさめ", "meaning": "小雨", "relation": "强度", "note": "雨量小"},
                    ],
                    "takeaway": "强弱看前缀。",
                }
            ],
            "same_kanji_expansion_groups": [
                {
                    "target_reading": "あめ",
                    "title": "雨的扩展",
                    "why_it_works": "从雨扩展到用品和天气",
                    "items": [
                        {"word": "雨", "reading": "あめ", "meaning": "雨", "relation": "核心义", "note": "天气"},
                        {"word": "雨具", "reading": "あまぐ", "meaning": "雨具", "relation": "用品", "note": "挡雨"},
                        {"word": "雨天", "reading": "うてん", "meaning": "雨天", "relation": "天气", "note": "正式词"},
                    ],
                    "takeaway": "雨从天气扩到相关用品。",
                }
            ],
            "pitfalls": ["雨あめ和飴あめ不要混。", "雨具读あまぐ。"],
            "memory_chain": "先记雨あめ，再用雨が降ります固定天气表达。",
        }

        parsed, error = batch_generate_v3.parse_batch_response(
            json.dumps({"items": [{"kanji": "雨", "data": payload}]}, ensure_ascii=False),
            ["雨"],
        )

        self.assertEqual(error, "")
        self.assertEqual(
            parsed["雨"]["readings"][0]["example_sentence"]["mandarin_pronunciation"],
            "à mě gǎ fǔ rī mā sù",
        )

    def test_build_initial_db_from_joyo_list_uses_kyoiku_grades_and_common_supplement_grade(self):
        db = batch_generate_v3._build_initial_db_from_kanji_list(
            ["一", "亜", "雨"],
            source="joyo_2010",
            grade_lookup={"一": 1, "雨": 1},
            source_limit=2,
        )

        self.assertEqual(db["meta"]["total"], 2)
        self.assertEqual(list(db["kanji"]), ["一", "亜"])
        self.assertEqual(db["kanji"]["一"]["grade"], 1)
        self.assertEqual(db["kanji"]["亜"]["grade"], 7)


class BatchGenerateV3QueueSelectionTest(unittest.TestCase):
    def setUp(self):
        self.db = {
            "kanji": {
                "生": {"grade": 1, "status": "failed"},
                "見": {"grade": 1, "status": "pending"},
                "上": {"grade": 1, "status": "completed"},
                "並": {"grade": 2, "status": "pending"},
            }
        }

    def test_select_kanji_queue_default_excludes_failed(self):
        self.assertEqual(
            batch_generate_v3._select_kanji_queue(self.db, include_failed=False),
            ["見", "並"],
        )

    def test_select_kanji_queue_retry_failed_includes_failed(self):
        self.assertEqual(
            batch_generate_v3._select_kanji_queue(self.db, include_failed=True),
            ["生", "見", "並"],
        )


if __name__ == "__main__":
    unittest.main()
