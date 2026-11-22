"""Persian captions (used by the weekly planner). Built from the product database."""
from __future__ import annotations

import html
import random

from . import data
from .config import contact_line

# --------------------------------------------------------------------------
# Persian captions
# --------------------------------------------------------------------------
FA_TEMPLATES = [
    "برای استعلام قیمت و موجودی، کد فنی را برای ما ارسال کنید.",
    "قطعه مناسب ناوگان خود را با کد فنی پیدا کنید؛ همین حالا پیام بدهید.",
    "توقف ناوگان یعنی ضرر. برای تامین سریع قطعه با ما در تماس باشید.",
    "موجودی، قیمت و شرایط ارسال را از ما بپرسید؛ پاسخگوی شما هستیم.",
    "برای سفارش عمده و تامین مستمر قطعات، با کارشناسان ما صحبت کنید.",
]
FA_LABELS = {
    "inner_diameter": "قطر داخلی", "outer_diameter": "قطر خارجی", "brake_disc_thickness": "ضخامت دیسک",
    "thickness": "ضخامت", "height": "ارتفاع", "width": "عرض", "length": "طول", "weight": "وزن",
    "thread_size": "اندازه رزوه", "thread_length": "طول رزوه", "bore_diameter": "قطر سوراخ",
    "number_of_teeth": "تعداد دندانه", "number_of_holes": "تعداد سوراخ", "fitting_position": "موقعیت نصب",
    "brake_disc_type": "نوع دیسک", "operating_mode": "نحوه عملکرد", "shock_absorber_type": "نوع کمک فنر",
    "quality_grade": "گرید", "bolt_head_diameter": "قطر سر پیچ", "head_height": "ارتفاع سر پیچ",
}
FA_VALUES = {
    "front axle": "محور جلو", "rear axle": "محور عقب", "manual": "دستی", "oil pressure": "روغنی",
    "gas pressure": "گازی",
}
FA_UNITS = {"PCS": "عدد", "SET": "ست", "KIT": "کیت", "PAIR": "جفت"}
FA_BASE_TAGS = ["قطعات_یدکی_کامیون", "لوازم_یدکی_کامیون", "قطعات_کامیون", "کامیون", "تریلی", "ناوگان_حمل_و_نقل"]


def _fa_value(v: str) -> str:
    return " | ".join(FA_VALUES.get(p.strip().lower(), p.strip()) for p in v.split("|"))


def _fa_tags(cfg: dict, category: str, limit: int, brand: str) -> str:
    cat = cfg["categories"].get(category, {})
    tags = []
    if cat.get("title_fa"):
        tags.append(cat["title_fa"].replace(" ", "_").replace("\u200c", "_"))
    tags += FA_BASE_TAGS
    tags += [t for t in cat.get("tags", [])][:2]
    brand_tag = "".join(ch for ch in cfg["brand"]["name"].lower() if ch.isalnum())
    tags.insert(0, brand_tag)
    if brand:
        tags.append(brand.lower().replace(" ", ""))
    seen, out = set(), []
    for t in tags:
        t = t.lstrip("#")
        if t and t not in seen:
            seen.add(t)
            out.append("#" + t)
    return " ".join(out[:limit])


def build_fa(cfg: dict, category: str, code: str, rng: random.Random) -> dict[str, str]:
    brand = cfg["brand"]
    rec = data.record(category, code)
    cat = cfg["categories"].get(category, {})
    name = rec.get("name_fa") or cat.get("title_fa") or cat.get("title", category)
    lines = [f"🔧 {name}", f"کد فنی: {code}", ""]
    if rec.get("brand"):
        lines.append(f"✅ برند: {rec['brand']}")
    if rec.get("oe"):
        lines.append(f"✅ شماره OE: {rec['oe'][:60]}")
    if rec.get("vehicles"):
        lines.append(f"✅ مناسب: {rec['vehicles'][:80]}")
    specs = []
    for key in FA_LABELS:
        if rec.get(key) and len(specs) < 5:
            specs.append(f"{FA_LABELS[key]}: {_fa_value(rec[key])}")
    if specs:
        lines.append("📐 مشخصات فنی:")
        lines += [f"▫️ {x}" for x in specs[:5]]
    if rec.get("pack_qty"):
        unit = FA_UNITS.get(rec.get("unit", "").upper(), rec.get("unit", ""))
        lines.append(f"📦 تعداد در بسته: {rec['pack_qty']} {unit}".rstrip())
    body = "\n".join(lines) + "\n\n" + rng.choice(FA_TEMPLATES)
    contact = []
    if brand.get("phone"):
        contact.append(f"📞 {brand['phone']}")
    if brand.get("whatsapp"):
        contact.append(f"💬 واتساپ: {brand['whatsapp']}")
    if brand.get("email"):
        contact.append(f"✉️ {brand['email']}")
    contact_txt = "\n".join(contact)
    brand_name = rec.get("brand", "")
    ig = f"{body}\n\n{contact_txt}\n🌐 {brand['website']} (لینک در بیو)"
    if brand.get("instagram"):
        ig += f"\n📸 {brand['instagram']}"
    ig += f"\n\n{_fa_tags(cfg, category, cfg['captions'].get('max_hashtags_instagram', 15), brand_name)}"
    short = _fa_tags(cfg, category, 5, brand_name)
    fb = f"{body}\n\n{contact_txt}\n🌐 {brand['website_url']}\n\n{short}"
    tg = (f"<b>{html.escape(lines[0], quote=False)}</b>\n" +
          html.escape("\n".join(lines[1:]) + "\n\n" + body.split("\n\n")[-1], quote=False) +
          f"\n\n{html.escape(contact_txt, quote=False)}\n🌐 <a href=\"{html.escape(brand['website_url'])}\">{html.escape(brand['website'])}</a>")
    if len(tg) + len(short) + 2 <= 1024:
        tg += f"\n\n{short}"
    return {"instagram": ig, "facebook": fb, "telegram": tg}
