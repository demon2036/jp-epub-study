from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from make_epub_v2 import _grade_kanji_in_db_order, _grade_title, _grades_in_db_order  # noqa: E402


class MakeEpubV2OrderTest(unittest.TestCase):
    def test_grade_kanji_in_db_order_preserves_db_order(self):
        db = {
            "kanji": {
                "語": {"grade": 2, "status": "completed"},
                "見": {"grade": 1, "status": "completed"},
                "生": {"grade": 1, "status": "pending"},
                "上": {"grade": 1, "status": "completed"},
            }
        }

        self.assertEqual(
            [kanji for kanji, _ in _grade_kanji_in_db_order(db, 1)],
            ["見", "上"],
        )

    def test_grades_include_joyo_supplement_after_school_grades(self):
        db = {
            "kanji": {
                "亜": {"grade": 7, "status": "completed"},
                "一": {"grade": 1, "status": "completed"},
                "見": {"grade": 1, "status": "pending"},
            }
        }

        self.assertEqual(_grades_in_db_order(db), [1, 7])
        self.assertEqual(_grade_title(7), "常用补充")


if __name__ == "__main__":
    unittest.main()
