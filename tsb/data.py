"""Product information for the poster templates.

data/products_db.json  - built by tools/build_database.py from your information files
                         (attr/*.txt + the xlsx sheets), keyed "category/CODE".
data/products.csv      - optional manual overrides (python main.py export-data creates it);
                         anything filled in there wins over the database."""
from __future__ import annotations

import csv
import json
import re
from functools import lru_cache
from pathlib import Path

from .config import ROOT


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


@lru_cache(maxsize=1)
def load_db() -> dict[str, dict[str, str]]:
    p = ROOT / "data" / "products_db.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def record(category: str, code: str) -> dict[str, str]:
    return load_db().get(f"{category}/{norm(code)}", {})


def load(path: Path | None = None) -> dict[tuple[str, str], dict[str, str]]:
    """Manual overrides from data/products.csv."""
    path = path or ROOT / "data" / "products.csv"
    rows: dict[tuple[str, str], dict[str, str]] = {}
    if not path.exists():
        return rows
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            cat, code = (r.get("category") or "").strip().lower(), (r.get("code") or "").strip().upper()
            if cat and code:
                rows[(cat, code)] = {k: (v or "").strip() for k, v in r.items() if k}
    return rows


def fields_for(cfg: dict, category: str, code: str, table: dict | None = None) -> dict[str, str]:
    cat = cfg["categories"].get(category, {})
    defaults = cfg.get("poster", {}).get("defaults", {}) or {}
    fields = {k: v for k, v in defaults.items() if v}
    fields.update(record(category, code))
    row = (table or {}).get((category.lower(), code.upper()), {})
    fields.update({k: v for k, v in row.items() if v})
    fields["code"] = code
    if not fields.get("name_en"):
        fields["name_en"] = cat.get("title", category.title())
    if not fields.get("name_fa"):
        fields["name_fa"] = cat.get("title_fa", "")
    return fields
