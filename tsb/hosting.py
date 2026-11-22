"""Instagram's API downloads the image from a public URL, so the generated
JPEG must be reachable on the internet at publish time."""
from __future__ import annotations

import os
from pathlib import Path

import requests

from .config import ROOT


class HostingError(RuntimeError):
    pass


def public_url(path: Path, cfg: dict) -> str:
    h = cfg.get("hosting", {})
    mode = h.get("mode", "none")
    if mode == "cloudinary":
        cloud = os.environ.get("CLOUDINARY_CLOUD_NAME")
        preset = os.environ.get("CLOUDINARY_UPLOAD_PRESET")
        if not cloud or not preset:
            raise HostingError("CLOUDINARY_CLOUD_NAME / CLOUDINARY_UPLOAD_PRESET missing in .env")
        with open(path, "rb") as f:
            r = requests.post(
                f"https://api.cloudinary.com/v1_1/{cloud}/image/upload",
                data={"upload_preset": preset, "folder": "truck-part-trading"},
                files={"file": (path.name, f, "image/jpeg")}, timeout=120)
        j = r.json()
        if r.status_code >= 400 or "secure_url" not in j:
            raise HostingError(f"Cloudinary upload failed: {j}")
        return j["secure_url"]
    if mode == "static":
        base = h.get("public_base_url", "").rstrip("/")
        if not base:
            raise HostingError("hosting.public_base_url is empty")
        rel = path.resolve().relative_to((ROOT / "output").resolve()).as_posix()
        return f"{base}/{rel}"
    raise HostingError("Instagram needs a public image URL: set hosting.mode to cloudinary or static in config.yaml")
