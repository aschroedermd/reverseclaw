import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parent.parent / "hard-reset-ai.py"
SPEC = importlib.util.spec_from_file_location("hard_reset_ai", MODULE_PATH)
hard_reset_ai = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(hard_reset_ai)


class HardResetAiTests(unittest.TestCase):
    def test_hard_reset_clears_runtime_artifacts_but_preserves_gitkeep(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            file_paths = []
            for name in hard_reset_ai.FILES_TO_REMOVE:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("artifact", encoding="utf-8")
                file_paths.append(path)

            directory_paths = []
            for dirname in hard_reset_ai.DIRECTORIES_TO_CLEAR:
                directory = root / dirname
                directory.mkdir(parents=True, exist_ok=True)
                (directory / ".gitkeep").write_text("", encoding="utf-8")
                (directory / "artifact.txt").write_text("artifact", encoding="utf-8")
                nested = directory / "nested"
                nested.mkdir()
                (nested / "artifact.txt").write_text("nested artifact", encoding="utf-8")
                directory_paths.append(directory)

            patched_files = [str(root / name) for name in hard_reset_ai.FILES_TO_REMOVE]
            patched_dirs = [str(root / name) for name in hard_reset_ai.DIRECTORIES_TO_CLEAR]

            with patch.object(hard_reset_ai, "FILES_TO_REMOVE", patched_files), patch.object(
                hard_reset_ai,
                "DIRECTORIES_TO_CLEAR",
                patched_dirs,
            ):
                hard_reset_ai.hard_reset_ai_state()

            for path in file_paths:
                self.assertFalse(path.exists(), f"{path} should be removed by a hard reset.")

            for directory in directory_paths:
                self.assertTrue((directory / ".gitkeep").exists(), f"{directory}/.gitkeep should be preserved.")
                self.assertEqual(list(directory.iterdir()), [directory / ".gitkeep"])


if __name__ == "__main__":
    unittest.main()
