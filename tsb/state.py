from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path

from .catalog import Product


class State:
    """Remembers which products were used so the feed never repeats until every
    product has been shown once, and which daily slots were already published."""

    def __init__(self, path: Path):
        self.path = path
        self.data = {"used": {}, "cat_last": {}, "done": {}, "attempts": {}, "cycle": 1, "posts_total": 0}
        if path.exists():
            try:
                self.data.update(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    # ---- product rotation -------------------------------------------------
    def pick(self, products: list[Product], rng: random.Random) -> Product:
        if not products:
            raise RuntimeError("No product images found in products/ folder.")
        used = self.data["used"]
        pool = [p for p in products if p.key not in used]
        if not pool:                       # everything shown once -> new cycle
            self.data["used"] = used = {}
            self.data["cycle"] += 1
            pool = list(products)
        by_cat: dict[str, list[Product]] = {}
        for p in pool:
            by_cat.setdefault(p.category, []).append(p)
        last = self.data["cat_last"]
        # category that was shown longest ago (never shown = first)
        cat = min(by_cat, key=lambda c: (last.get(c, ""), rng.random()))
        return rng.choice(by_cat[cat])

    def mark_used(self, product: Product) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.data["used"][product.key] = now
        self.data["cat_last"][product.category] = now
        self.data["posts_total"] += 1

    # ---- slot bookkeeping -------------------------------------------------
    def is_done(self, key: str) -> bool:
        return key in self.data["done"]

    def attempts(self, key: str) -> int:
        return self.data["attempts"].get(key, 0)

    def add_attempt(self, key: str) -> None:
        self.data["attempts"][key] = self.attempts(key) + 1

    def mark_done(self, key: str) -> None:
        self.data["done"][key] = datetime.now().isoformat(timespec="seconds")
        for bucket in ("done", "attempts"):        # keep file small
            keys = sorted(self.data[bucket])
            for old in keys[:-60]:
                self.data[bucket].pop(old, None)
