from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> None:
    """Tiny .env loader (no extra dependency). Real environment variables win."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    brand = cfg.setdefault("brand", {})
    if not brand.get("website_url"):
        site = brand.get("website", "")
        brand["website_url"] = site if site.startswith("http") else f"https://{site}"
    return cfg


def contact_line(brand: dict) -> str:
    parts = []
    if brand.get("phone"):
        parts.append(brand["phone"])
    if brand.get("whatsapp"):
        parts.append(f"WhatsApp {brand['whatsapp']}")
    if brand.get("email"):
        parts.append(brand["email"])
    return "   |   ".join(parts)
