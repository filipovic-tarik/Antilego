import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ACTIVE_PACKAGE = PROJECT_ROOT / "antilego"
FOUNDATIONAL_ARTIFACT = PROJECT_ROOT / "foundational_artifact"


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_active_runtime_does_not_import_foundational_artifact(self):
        active_files = list(ACTIVE_PACKAGE.rglob("*.py"))
        for path in active_files:
            source = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("foundational_artifact.", source, path)
            self.assertNotIn("from foundational_artifact", source, path)

    def test_foundational_artifact_preserves_required_sections(self):
        required = {
            "original_collector",
            "experiments",
            "historical_data",
            "research",
            "published_outputs",
            "records",
        }
        present = {path.name for path in FOUNDATIONAL_ARTIFACT.iterdir() if path.is_dir()}
        self.assertTrue(required.issubset(present))


if __name__ == "__main__":
    unittest.main()
