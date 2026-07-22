from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from kanji_pronunciation_audit import (  # noqa: E402
    audit_sentence_pronunciation,
    correct_sentence_pronunciation,
    repair_memory_payload_pronunciations,
)


class KanjiPronunciationAuditTest(unittest.TestCase):
    def test_corrects_kana_romaji_mismatch_preserving_tone_shape(self):
        result = correct_sentence_pronunciation(
            "あめがふります。",
            "à mǎ gǎ fǔ rī mā sù",
        )

        self.assertEqual(result.corrected, "à mě gǎ fǔ rī mā sù")
        self.assertEqual(len(result.issues), 1)
        self.assertIn("expected=me actual=ma", result.issues[0])

    def test_keeps_particles_by_actual_sentence_pronunciation(self):
        result = audit_sentence_pronunciation(
            "はしをわたってへやへいきます。",
            "hǎ shī o wǎ tā ttē hě yā e ǐ kī mā sù",
        )

        self.assertEqual(result.issues, [])

    def test_splits_combined_token_without_shifting_particle_pronunciation(self):
        result = correct_sentence_pronunciation(
            "せっしょうはよくないといわれます。",
            "sèsshō wa yǒ kū nā ì tō ī wā rē mà sū",
        )

        self.assertEqual(
            result.corrected,
            "sè sshō wa yǒ kū nā ì tō ī wā rē mà sū",
        )
        self.assertTrue(result.issues)
        self.assertNotIn(" h", result.corrected)

    def test_repair_memory_payload_updates_nested_example_sentences(self):
        payload = {
            "readings": [
                {
                    "kana": "あめ",
                    "example_sentence": {
                        "kana": "あめがふります。",
                        "mandarin_pronunciation": "à mǎ gǎ fǔ rī mā sù",
                    },
                }
            ]
        }

        changes = repair_memory_payload_pronunciations(payload, kanji="雨")

        self.assertEqual(
            payload["readings"][0]["example_sentence"]["mandarin_pronunciation"],
            "à mě gǎ fǔ rī mā sù",
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["kanji"], "雨")
        self.assertEqual(changes[0]["reading"], "あめ")
        self.assertTrue(changes[0]["changed"])

    def test_repair_memory_payload_splits_merged_short_kana_tokens(self):
        payload = {
            "readings": [
                {
                    "kana": "た",
                    "example_sentence": {
                        "kana": "たべました。",
                        "mandarin_pronunciation": "tábe māshità",
                    },
                }
            ]
        }

        issues = repair_memory_payload_pronunciations(payload, kanji="食")

        self.assertEqual(
            payload["readings"][0]["example_sentence"]["mandarin_pronunciation"],
            "tá be mā shi tà",
        )
        self.assertEqual(len(issues), 1)
        self.assertTrue(issues[0]["changed"])
        self.assertIn("combined_token", issues[0]["issues"][0])

    def test_inserts_missing_particle_pronunciation(self):
        result = correct_sentence_pronunciation(
            "このくらではさけをつくります",
            "kǒ nō kǔ rā dē sǎ kē o tsǔ kú rǐ mā sù",
        )

        self.assertEqual(
            result.corrected,
            "kǒ nō kǔ rā dē wa sǎ kē o tsǔ kú rǐ mā sù",
        )
        self.assertTrue(any("missing_token" in issue for issue in result.issues))

    def test_removes_extra_duplicate_pronunciation_token(self):
        result = correct_sentence_pronunciation(
            "さとうをすこしいれます",
            "sǎ tō ù ǒ sǔ kō shī ī ǐ rē mā sù",
        )

        self.assertEqual(
            result.corrected,
            "sǎ tō ù ǒ sǔ kō shī ī rē mā sù",
        )
        self.assertTrue(any("extra_token" in issue for issue in result.issues))

    def test_does_not_treat_arbitrary_following_a_as_optional_long_vowel(self):
        result = correct_sentence_pronunciation(
            "があります",
            "gā rī mā sù",
        )

        self.assertEqual(result.corrected, "gā a rī mā sù")
        self.assertTrue(any("missing_token" in issue for issue in result.issues))


if __name__ == "__main__":
    unittest.main()
