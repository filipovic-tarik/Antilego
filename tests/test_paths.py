import unittest
from datetime import date

from antilego.paths import live_snapshot_path, weekly_archive_dir


class WeeklyArchivePathTests(unittest.TestCase):
    def test_week_uses_monday_through_sunday(self):
        path = weekly_archive_dir(date(2026, 8, 7))
        self.assertEqual(path.parts[-3:], ("2026", "08", "03"))

    def test_week_crossing_month_uses_monday_date(self):
        path = weekly_archive_dir(date(2026, 9, 1))
        self.assertEqual(path.parts[-3:], ("2026", "08", "31"))

    def test_live_data_is_inside_week_folder(self):
        path = live_snapshot_path(date(2026, 8, 7))
        self.assertEqual(path.parts[-5:], ("2026", "08", "03", "market_data", "snapshots.jsonl"))


if __name__ == "__main__":
    unittest.main()
