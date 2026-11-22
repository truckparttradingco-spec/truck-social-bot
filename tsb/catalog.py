from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

EXTS = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class Product:
    category: str      # folder name, e.g. "air"
    code: str          # display code, e.g. "4157-1"
    path: Path

    @property
    def key(self) -> str:
        return f"{self.category}/{self.path.name}"


def scan(products_dir: Path, exclude_names=(), exclude_categories=()) -> list[Product]:
    exclude_names = {n.lower() for n in exclude_names}
    exclude_categories = {c.lower() for c in exclude_categories}
    items: list[Product] = []
    if not products_dir.exists():
        return items
    for cat_dir in sorted(p for p in products_dir.iterdir() if p.is_dir()):
        if cat_dir.name.lower() in exclude_categories:
            continue
        for f in sorted(cat_dir.iterdir()):
            if f.suffix.lower() not in EXTS or f.stem.lower() in exclude_names:
                continue
            code = f.stem.upper().replace("_", "-")
            items.append(Product(cat_dir.name, code, f))
    return items
