from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_codex_memory_matrix import (  # noqa: E402
    DEFAULT_CONFIG_FILE,
    Variant,
    _build_codex_cmd,
    _load_jsonl_results,
    _read_config_lines,
    _result_sort_key,
    _validate_memory_payload,
    _write_jsonl_line,
    default_kanji_sample,
    default_variants,
    filter_variants,
    variant_label,
    variant_slug,
)


def _reading(kana):
    return {
        "kana": kana,
        "example_sentence": {
            "jp_ruby": "橋[はし]を渡[わた]ります。",
            "kana": "はしをわたります。",
            "mandarin_pronunciation": "hā shī wō wā tā rī mā sū",
            "zh": "过桥。",
            "note": "用例句固定读音。",
        },
    }


class CodexMemoryMatrixHelpersTest(unittest.TestCase):
    def test_default_kanji_sample(self):
        self.assertEqual(default_kanji_sample(), ["並", "橋", "見", "生"])

    def test_variant_slug(self):
        self.assertEqual(variant_slug("gpt-5.2", "xhigh"), "gpt-5.2-xhigh")
        self.assertEqual(variant_slug("gpt-5.4", "medium"), "gpt-5.4-medium")

    def test_variant_label(self):
        self.assertEqual(variant_label("gpt-5.4", "high"), "gpt-5.4 / high")

    def test_build_codex_cmd_places_global_approval_flag_before_exec(self):
        cmd = _build_codex_cmd(
            variant=Variant("gpt-5.2", "xhigh"),
            schema_path=ROOT / "scripts" / "schemas" / "codex_kanji_memory_v1.schema.json",
            config_lines=[],
            cd=Path("/tmp"),
        )
        self.assertEqual(cmd[0], "codex")
        self.assertLess(cmd.index("-a"), cmd.index("exec"))
        self.assertEqual(cmd[cmd.index("-a") + 1], "never")

    def test_default_config_file_uses_cliproxy_provider(self):
        config_lines = _read_config_lines(DEFAULT_CONFIG_FILE)
        self.assertIn('model_provider="cliproxyapi"', config_lines)
        self.assertIn('model_providers.cliproxyapi.base_url="http://127.0.0.1:8317/v1"', config_lines)
        self.assertIn('model_providers.cliproxyapi.env_key="CLI_PROXY_KEY"', config_lines)
        self.assertTrue(any(line.startswith('model_instructions_file=') for line in config_lines))

    def test_filter_variants_for_gpt54_high_and_xhigh(self):
        variants = filter_variants(default_variants(), models=["gpt-5.4"], efforts=["high", "xhigh"])
        self.assertEqual(
            [(item.model, item.effort) for item in variants],
            [("gpt-5.4", "high"), ("gpt-5.4", "xhigh")],
        )

    def test_result_sort_key_respects_input_order(self):
        kanji_order = ["並", "橋", "見"]
        variants = [Variant("gpt-5.4", "high"), Variant("gpt-5.4", "xhigh")]
        result = {
            "kanji": "橋",
            "variant": {"model": "gpt-5.4", "effort": "xhigh"},
        }
        self.assertEqual(_result_sort_key(result, kanji_order=kanji_order, variants=variants), (1, 1))

    def test_write_and_load_incremental_jsonl_results(self):
        tmp = ROOT / "data" / "logs" / "test_results.jsonl"
        if tmp.exists():
            tmp.unlink()
        _write_jsonl_line(tmp, {"kanji": "並", "variant": {"model": "gpt-5.4", "effort": "high"}, "status": "completed"})
        _write_jsonl_line(tmp, {"kanji": "橋", "variant": {"model": "gpt-5.4", "effort": "high"}, "status": "timeout"})
        loaded = _load_jsonl_results(tmp)
        self.assertEqual([item["kanji"] for item in loaded], ["並", "橋"])
        tmp.unlink()

    def test_validate_memory_payload_requires_homophone_group_for_each_reading(self):
        payload = {
            "readings": [
                _reading("なみ"),
                _reading("へい"),
            ],
            "homophone_groups": [
                {
                    "target_reading": "なみ",
                    "same_kana": "なみ",
                }
            ],
        }
        self.assertEqual(
            _validate_memory_payload(payload),
            "missing_homophone_groups_for_readings: へい",
        )

    def test_validate_memory_payload_rejects_reading_level_mandarin_pronunciation(self):
        payload = {
            "readings": [
                {
                    **_reading("はし"),
                    "mandarin_pronunciation": {
                        "pinyin": "hā shī",
                        "note": "旧版逐字读音表音。",
                    },
                },
            ],
            "homophone_groups": [
                {
                    "target_reading": "はし",
                    "same_kana": "はし",
                }
            ],
        }
        self.assertEqual(
            _validate_memory_payload(payload),
            "unexpected_reading_mandarin_pronunciation: はし",
        )

    def test_validate_memory_payload_rejects_same_kana_drifting_to_whole_word(self):
        payload = {
            "readings": [
                _reading("せい"),
            ],
            "homophone_groups": [
                {
                    "target_reading": "せい",
                    "same_kana": "せいねん",
                }
            ],
        }
        self.assertEqual(
            _validate_memory_payload(payload),
            "same_kana_must_match_target_reading: せい -> せいねん",
        )

    def test_validate_memory_payload_accepts_one_group_per_reading(self):
        payload = {
            "readings": [
                _reading("みる"),
                _reading("けん"),
            ],
            "homophone_groups": [
                {
                    "target_reading": "みる",
                    "same_kana": "みる",
                },
                {
                    "target_reading": "けん",
                    "same_kana": "けん",
                },
            ],
        }
        self.assertIsNone(_validate_memory_payload(payload))


class PromptAndSchemaContractTest(unittest.TestCase):
    def test_prompt_forbids_tool_usage(self):
        prompt = (ROOT / "scripts" / "prompts" / "kanji_explain_json.md").read_text(encoding="utf-8")
        self.assertIn("不要调用任何工具", prompt)
        self.assertIn("不要进行 web search", prompt)
        self.assertIn("同源分化", prompt)
        self.assertIn("纯同音碰撞", prompt)
        self.assertIn("为什么会同音", prompt)
        self.assertIn("优先围绕目标字最值得记的那个读音", prompt)
        self.assertIn("只有前两者完全做不出高价值组时", prompt)
        self.assertIn("每个常用读音都必须单独展开", prompt)
        self.assertIn("至少 2 个例词", prompt)
        self.assertIn("四类组块不能替代每个读音自己的例词讲解", prompt)
        self.assertIn("每个读音都要给出一句自己的小记忆结论", prompt)
        self.assertIn("不要为了显得全面", prompt)
        self.assertIn("优先保留最常用、最有生成力、最值得教学展开的读音", prompt)
        self.assertIn("每个保留的读音都必须至少对应 1 组同假名异义组", prompt)
        self.assertIn("`same_kana` 必须只写这一组共同的假名读法本身", prompt)
        self.assertIn("如果某个保留读音很难找到“不同汉字、不同词义”的强同音组，也不能省略", prompt)
        self.assertIn("`うむ` 可以用 `生む / 産む / うむ`", prompt)
        self.assertIn("`なま` 可以用 `生 / ナマ / なま`", prompt)
        self.assertIn("example_sentence", prompt)
        self.assertIn("mandarin_pronunciation", prompt)
        self.assertIn("声调符号不是普通话词调", prompt)
        self.assertIn("tǎ bē mā shī tà", prompt)
        self.assertIn("罗马字母必须和日语罗马音一致", prompt)
        self.assertIn("不要写 `xi`", prompt)
        self.assertIn("不要写 `guo`", prompt)
        self.assertIn("每个 `example_sentence` 都必须给整句 `mandarin_pronunciation`", prompt)
        self.assertNotIn("每个常用读音都必须给出 `mandarin_pronunciation`", prompt)
        self.assertNotIn('"mandarin_pronunciation": {\n        "pinyin"', prompt)

    def test_batch_instruction_file_is_repo_local_and_concise(self):
        prompt = (ROOT / "scripts" / "prompts" / "codex_kanji_batch_instructions.md").read_text(encoding="utf-8")
        self.assertIn("生动、形象、好背", prompt)
        self.assertIn("节省 token", prompt)
        self.assertIn("声调符号不是普通话词调", prompt)
        self.assertIn("声调符号", prompt)
        self.assertIn("不要写 `ha1 xi1`", prompt)
        self.assertIn("例句整句都必须有普通话表音", prompt)
        self.assertIn("罗马字母必须和日语罗马音一致", prompt)
        self.assertNotIn("每个读音和每个例句都必须有普通话表音", prompt)

    def test_schema_rejects_empty_summary_and_empty_group_arrays(self):
        schema = json.loads((ROOT / "scripts" / "schemas" / "codex_kanji_memory_v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["summary"]["minLength"], 20)
        self.assertEqual(schema["properties"]["memory_chain"]["minLength"], 30)
        self.assertEqual(schema["properties"]["scenario_contrast_groups"]["minItems"], 1)
        self.assertEqual(schema["properties"]["homophone_groups"]["minItems"], 1)
        self.assertEqual(schema["properties"]["near_synonym_groups"]["minItems"], 1)
        self.assertEqual(schema["properties"]["same_kanji_expansion_groups"]["minItems"], 1)
        reading_schema = schema["properties"]["readings"]["items"]
        self.assertIn("examples", reading_schema["required"])
        self.assertIn("takeaway", reading_schema["required"])
        self.assertNotIn("mandarin_pronunciation", reading_schema["required"])
        self.assertNotIn("mandarin_pronunciation", reading_schema["properties"])
        self.assertIn("example_sentence", reading_schema["required"])
        self.assertIn("jp_ruby", reading_schema["properties"]["example_sentence"]["required"])
        self.assertIn("mandarin_pronunciation", reading_schema["properties"]["example_sentence"]["required"])
        self.assertEqual(reading_schema["properties"]["examples"]["minItems"], 2)
        self.assertGreaterEqual(reading_schema["properties"]["takeaway"]["minLength"], 8)
        homophone_group = schema["$defs"]["homophoneGroup"]
        self.assertIn("origin_pattern", homophone_group["required"])
        self.assertIn("same_kana_reason", homophone_group["required"])
        self.assertIn("teaching_point", homophone_group["required"])
        self.assertIn("target_reading", homophone_group["required"])
        homophone_item = schema["$defs"]["homophoneItem"]
        self.assertIn("source_note", homophone_item["required"])
        self.assertIn("memory_hook", homophone_item["required"])


if __name__ == "__main__":
    unittest.main()
