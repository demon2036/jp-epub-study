from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_codex_memory_matrix import DEFAULT_CD  # noqa: E402
from codex_exec_support import DEFAULT_CODEX_CWD, expand_prompt_file_refs  # noqa: E402


class CodexExecSupportTest(unittest.TestCase):
    def test_default_cwd_is_repo_root(self):
        self.assertEqual(DEFAULT_CODEX_CWD, ROOT)
        self.assertEqual(DEFAULT_CD, ROOT)

    def test_expand_prompt_file_refs_inlines_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            (base_dir / "README.md").write_text("line one\nline two\n", encoding="utf-8")

            expanded = expand_prompt_file_refs("Write tests for @README.md", base_dir)

        self.assertIn("Write tests for", expanded)
        self.assertIn("README.md", expanded)
        self.assertIn("line one", expanded)
        self.assertNotIn("@README.md", expanded)

    def test_expand_prompt_file_refs_raises_for_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            with self.assertRaises(FileNotFoundError):
                expand_prompt_file_refs("Use @missing.txt", base_dir)


if __name__ == "__main__":
    unittest.main()
