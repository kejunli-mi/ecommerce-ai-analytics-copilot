from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetSpec:
    table: str
    filename: str
    primary_key: tuple[str, ...] = ()
    required: bool = True


DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec("customers", "olist_customers_dataset.csv", ("customer_id",)),
    DatasetSpec("orders", "olist_orders_dataset.csv", ("order_id",)),
    DatasetSpec(
        "order_items",
        "olist_order_items_dataset.csv",
        ("order_id", "order_item_id"),
    ),
    DatasetSpec(
        "order_payments",
        "olist_order_payments_dataset.csv",
        ("order_id", "payment_sequential"),
    ),
    DatasetSpec(
        "order_reviews",
        "olist_order_reviews_dataset.csv",
        ("review_id", "order_id"),
    ),
    DatasetSpec("products", "olist_products_dataset.csv", ("product_id",)),
    DatasetSpec("sellers", "olist_sellers_dataset.csv", ("seller_id",)),
    DatasetSpec("geolocation", "olist_geolocation_dataset.csv", required=False),
    DatasetSpec(
        "category_translation",
        "product_category_name_translation.csv",
        ("product_category_name",),
        required=False,
    ),
)


def discover(data_dir: Path) -> dict[DatasetSpec, Path | None]:
    """Return every expected dataset and its local path, if present."""
    return {
        spec: (path if (path := data_dir / spec.filename).is_file() else None) for spec in DATASETS
    }


def missing_required(data_dir: Path) -> list[DatasetSpec]:
    return [spec for spec, path in discover(data_dir).items() if spec.required and path is None]
