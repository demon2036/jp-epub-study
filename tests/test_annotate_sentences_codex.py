from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import annotate_sentences_codex as annotate_sentences_codex  # noqa: E402


class AnnotateSentencesCodexArgsTest(unittest.TestCase):
    def test_build_arg_parser_defaults_cd_to_repo_root(self):
        parser = annotate_sentences_codex.build_arg_parser()
        args = parser.parse_args(["input.json"])
        self.assertEqual(args.cd, ROOT)


if __name__ == "__main__":
    unittest.main()
