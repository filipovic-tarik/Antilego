import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ACTIVE_PACKAGE = PROJECT_ROOT / "antilego"
FOUNDATION_CODEX = ACTIVE_PACKAGE / "foundation_codex"


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_active_runtime_does_not_import_foundation_codex(self):
        active_files = [
            path
            for path in ACTIVE_PACKAGE.rglob("*.py")
            if FOUNDATION_CODEX not in path.parents
        ]
        for path in active_files:
            source = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("foundation_codex.", source, path)
            self.assertNotIn("from .foundation_codex", source, path)

    def test_foundation_codex_preserves_required_sections(self):
        required = {
            "original_collector",
            "experiments",
            "historical_data",
            "research",
            "published_outputs",
            "records",
        }
        present = {path.name for path in FOUNDATION_CODEX.iterdir() if path.is_dir()}
        self.assertTrue(required.issubset(present))


if __name__ == "__main__":
    unittest.main()
