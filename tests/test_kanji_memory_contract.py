from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from kanji_memory_contract import validate_memory_payload  # noqa: E402


class KanjiMemoryContractTest(unittest.TestCase):
    def test_accepts_cjk_extension_kanji_in_jp_ruby(self):
        payload = {
            "readings": [
                {
                    "kana": "しかる",
                    "example_sentence": {
                        "jp_ruby": "先生[せんせい]が𠮟[しか]ります。",
                        "kana": "せんせいがしかります。",
                        "mandarin_pronunciation": "sēn sē gā shī kā rī mā sù",
                        "zh": "老师训斥。",
                        "note": "用𠮟ります固定しかる。",
                    },
                }
            ],
            "homophone_groups": [
                {
                    "target_reading": "しかる",
                    "same_kana": "しかる",
                }
            ],
        }

        self.assertIsNone(validate_memory_payload(payload))


if __name__ == "__main__":
    unittest.main()
