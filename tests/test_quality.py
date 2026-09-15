from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ecommerce_copilot.catalog import DatasetSpec
from ecommerce_copilot.quality import profile_csv


class QualityProfileTest(TestCase):
    def test_profile_counts_rows_empty_values_and_duplicate_keys(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "orders.csv"
            path.write_text(
                "order_id,status\norder-1,delivered\norder-1,\norder-2,canceled\n",
                encoding="utf-8",
            )
            spec = DatasetSpec("orders", "orders.csv", ("order_id",))

            profile = profile_csv(spec, path)

            self.assertEqual(profile["row_count"], 3)
            self.assertEqual(profile["empty_counts"]["status"], 1)
            self.assertEqual(profile["duplicate_primary_keys"], 1)
