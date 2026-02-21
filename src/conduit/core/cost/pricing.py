"""Model pricing table loader."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def _load_pricing_table() -> dict[str, Any]:
    """Load pricing data from JSON file."""
    search_paths = [
        Path("config/pricing/models.json"),
        Path("/app/config/pricing/models.json"),
    ]
    for path in search_paths:
        if path.is_file():
            with open(path) as f:
                data = json.load(f)
                return data.get("models", {})
    return {}


def get_model_pricing(model: str) -> dict[str, Any] | None:
    """
    Get pricing info for a model.

    Returns dict with 'input_cost_per_1m' and 'output_cost_per_1m', or None.
    """
    table = _load_pricing_table()
    return table.get(model)


def list_all_pricing() -> dict[str, Any]:
    """Return the entire pricing table."""
    return _load_pricing_table()