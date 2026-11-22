"""Builds platform-specific captions. Several templates rotate so that posts
don't look copy-pasted (which platforms treat as spam)."""
from __future__ import annotations

import html
import random

from . import data
from .config import contact_line

TEMPLATES = [
    "{title} | Part No. {code}\n\nBuilt for heavy-duty trucks and trailers. Send us the part number and we'll reply with availability and pricing.",
    "Looking for {title_l}? Part No. {code} is available to inquire today.\n\nTell us your truck model or part number and our team will help you find the right fit.",
    "Keep your fleet on the road. {title} - Part No. {code}.\n\nMessage us your requirements for a quick quote.",
    "In focus: {title}, Part No. {code}.\n\nQuality spare parts for trucks and trailers. Ask us about quantities, availability and delivery.",
    "Part No. {code} - {title}.\n\nDowntime costs money. Contact us with your part number and we'll get back to you fast.",
    "Spare parts you can count on: {title} (Part No. {code}).\n\nSend your inquiry and we'll take care of the rest.",
]


def _tags(cfg: dict, category: str, limit: int) -> str:
    cat = cfg["categories"].get(category, {})
    tags = list(cat.get("tags", [])) + list(cfg["captions"].get("base_hashtags", []))
    brand_tag = "".join(ch for ch in cfg["brand"]["name"].lower() if ch.isalnum())
    tags.insert(0, brand_tag)
    seen, out = set(), []
    for t in tags:
        t = t.lstrip("#").lower()
        if t and t not in seen:
            seen.add(t)
            out.append("#" + t)
    return " ".join(out[:limit])


def build(cfg: dict, category: str, code: str, rng: random.Random) -> dict[str, str]:
    brand = cfg["brand"]
    rec = data.record(category, code)
    title = rec.get("name_en") or cfg["categories"].get(category, {}).get("title", category.title())
    body = rng.choice(TEMPLATES).format(title=title, title_l=title.lower(), code=code)
    details = []
    if rec.get("brand"):
        details.append(f"Brand: {rec['brand'].title() if rec['brand'].isupper() and len(rec['brand']) > 4 else rec['brand']}")
    if rec.get("oe"):
        details.append(f"OE No.: {rec['oe'][:60]}")
    if rec.get("vehicles"):
        details.append(f"Fits: {rec['vehicles'][:80]}")
    if details:
        body += "\n\n" + "\n".join(details)
    contact = contact_line(brand)
    ig_tags = _tags(cfg, category, cfg["captions"].get("max_hashtags_instagram", 15))
    short_tags = _tags(cfg, category, 4)

    # Instagram: links in captions are not clickable
    ig = f"{body}\n\n🌐 {brand['website']} (link in bio)"
    if contact:
        ig += f"\n📩 {contact}"
    ig += f"\n\n{ig_tags}"

    # Facebook: link is clickable
    fb = f"{body}\n\n🌐 {brand['website_url']}"
    if contact:
        fb += f"\n📩 {contact}"
    fb += f"\n\n{short_tags}"

    # Telegram: HTML parse mode, 1024-char caption limit for photos
    tg = (f"{html.escape(body, quote=False)}\n\n"
          f"🌐 <a href=\"{html.escape(brand['website_url'])}\">{html.escape(brand['website'])}</a>")
    if contact:
        tg += f"\n📩 {html.escape(contact, quote=False)}"
    if len(tg) + len(short_tags) + 2 <= 1024:      # never cut inside an HTML tag
        tg += f"\n\n{short_tags}"
    return {"instagram": ig, "facebook": fb, "telegram": tg}
