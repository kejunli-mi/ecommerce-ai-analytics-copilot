from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ecommerce_copilot.catalog import DATASETS, discover, missing_required


class CatalogTest(TestCase):
    def test_empty_directory_reports_all_required_datasets(self) -> None:
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            missing = missing_required(data_dir)
            self.assertTrue(missing)
            self.assertTrue(all(spec.required for spec in missing))

    def test_discover_finds_expected_file(self) -> None:
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            target = data_dir / DATASETS[0].filename
            target.write_text("customer_id\ncustomer-1\n", encoding="utf-8")
            found = discover(data_dir)
            self.assertEqual(found[DATASETS[0]], target)
