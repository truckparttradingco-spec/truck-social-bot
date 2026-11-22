#!/usr/bin/env python3
"""Developer tool: merges the product information you sent (attr/*.txt, kaan-attr/*.txt and the
.xlsx sheets) into data/products_db.json, matched to the images in products/.

  python tools/build_database.py /path/to/claude-product-data

Run it again whenever the information files change.  Needs: openpyxl."""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def slug(s: str) -> str:
    s = re.sub(r"[øØ]", "", str(s).lower())
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


COUNTRY_FA = {"ترکیه": "TURKEY", "چین": "CHINA", "تایوان": "TAIWAN", "هند": "INDIA", "آلمان": "GERMANY",
              "ایران": "IRAN", "ایتالیا": "ITALY", "ژاپن": "JAPAN", "کره": "KOREA", "اسپانیا": "SPAIN"}

# which xlsx sheets describe which product folders
SHEETS = {
    "ABS RING.xlsx": ["abs"], "ABS SENSOR.xlsx": ["sensor"], "ADJUSTER BRAKE.xlsx": ["adj"],
    "AIR SPRING.xlsx": ["air"], "BALLBEARING.xlsx": ["bearing"], "BRAKE DISC.xlsx": ["disc"],
    "BRAKE PAD.xlsx": ["pad", "knorr"], "CALIPER CARRIER.xlsx": ["carrier"],
    "CALIPER REPAIR KIT.xlsx": ["bpnew", "bpw", "bremse", "holland", "meritor", "wabco", "zcam", "kaan", "china"],
    "CHINESE TRUCKS.xlsx": ["howo", "china"], "KAAN.xlsx": ["kaan"], "KNORR-BREMSE.xlsx": ["knorr"],
    "OIL SEALS.xlsx": ["seal"], "RUBBER BUSH.xlsx": ["bush"], "SHOCK ABSORBER.xlsx": ["shock"],
    "SUSPENTION.xlsx": ["suspension", "air"], "WHEEL BOLT.xlsx": ["bolt"], "WHEEL HUB.xlsx": ["other"],
}

BASE_HEADERS = {
    "code": "code", "sku": "code", "part name fa": "name_fa", "part nam fa": "name_fa", "name": "name_fa",
    "نام فارسی": "name_fa", "part name en": "name_en", "brand": "brand", "برند": "brand",
    "country": "country", "کشور": "country", "unit": "unit", "set/pcs/kit": "unit", "box": "pack_qty",
    "each box": "pack_qty", "main box": "carton_qty", "main oe": "oe", "mian oe": "oe", "oe number": "oe",
    "oe code": "oe", "fit vehicles": "vehicles", "type vehicles": "vehicles", "type  vehicles": "vehicles",
    "type": "type", "groups": "group",
}

# Persian / mixed labels used inside the attr files -> canonical key
ATTR_LABELS = {
    "قطر خارجی": "outer_diameter", "قطر داخلی": "inner_diameter", "ارتفاع": "height", "طول": "length",
    "طول 1": "length_1", "طول 2": "length_2", "عرض": "width", "عرض 1": "width_1", "ضخامت": "thickness",
    "Brake Disc ضخامت": "brake_disc_thickness", "Minimum thickness": "minimum_thickness",
    "Centering Diameter": "centering_diameter", "Thread طول": "thread_length",
    "Screw length below head": "screw_length_below_head", "Bolt Head Diameter": "bolt_head_diameter",
    "Shock Absorber Mounting Type": "shock_absorber_mounting_type", "سیستم کمک فنر": "shock_absorber_system",
    "Weight": "weight", "قطر سوراخ": "bore_diameter", "تعداد سوراخ": "number_of_holes",
    "قطر دایره پیچ": "bolt_hole_circle", "اندازه رزوه": "thread_size", "اندازه رزوه 1": "thread_size_1",
    "اندازه رزوه 2": "thread_size_2", "قطر خارجی 1": "outer_diameter_1", "قطر خارجی 2": "outer_diameter_2",
    "قطر داخلی 1": "inner_diameter_1", "قطر داخلی 2": "inner_diameter_2", "Spring Design": "spring_design",
    "Spanner Size": "spanner_size", "Surface": "surface", "Thread Type": "thread_type", "Toothing": "toothing",
    "Piston Rod Diameter": "piston_rod_diameter", "Brake Disc Type": "brake_disc_type", "Shape": "shape",
    "Bore Distance": "bore_distance", "Diameter up to": "diameter_up_to", "Strength class": "strength_class",
    "Trade Numbers": "trade_numbers", "ارتفاع 1": "height_1", "ارتفاع 2": "height_2", "Diameter": "diameter",
}
ATTR_TOP = {
    "نام محصول": "name_fa", "نام انگلیسی": "name_en", "کد فنی / SKU": "code", "کد فنی": "code", "برند": "brand",
    "واحد عرضه": "unit", "واحد شمارش": "unit", "تعداد در بسته": "pack_qty", "تعداد در جعبه": "pack_qty",
    "تعداد در کارتن مادر": "carton_qty", "تعداد در بسته مادر": "carton_qty", "شماره OE": "oe",
    "خودروهای مرتبط": "vehicles", "نوع کامیون / سازنده خودرو": "vehicles", "مدل های مرتبط": "models",
    "سری یا مدل خودرو": "models", "کشور سازنده": "country", "ساخت کشور": "country", "وزن قطعه": "weight",
    "وزن": "weight", "کارکرد": "function", "کاربرد": "function", "قطعات مرتبط": "related_parts",
    "موقعیت نصب": "fitting_position", "نوع کمک فنر": "shock_absorber_type", "جنس": "material",
    "نحوه عملکرد": "operating_mode", "تعداد دندانه": "number_of_teeth", "توضیحات": "notes",
    "اندازه رزوه": "thread_size",
}


def clean(v) -> str:
    if v is None:
        return ""
    s = html.unescape(str(v)).replace("\t", " ").replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return "" if s.lower() in ("none", "nan", "-") else s


def clean_name_en(s: str) -> str:
    """'10.13022 Brake Adjuster' / 'CB0225 Shock Absorber, cab suspension' -> drop the leading article number."""
    toks = clean(s).split()
    while len(toks) > 2 and (any(c.isdigit() for c in toks[0]) or
                             (toks[0].isupper() and any(c.isdigit() for c in toks[1]))):
        toks.pop(0)
        if toks and toks[0].isdigit():
            toks.pop(0)
    return " ".join(toks)


# --------------------------------------------------------------------------
def parse_attr(path: Path) -> dict:
    rec: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        parts = [p.strip() for p in line.split(":")]
        head = parts[0]
        if head in ("ابعاد", "مشخصات") and len(parts) >= 3:
            label, val = parts[1], ":".join(parts[2:]).strip()
            key = ATTR_LABELS.get(label)
            if key is None:
                key = slug(label)
                if not key:
                    continue
            if clean(val):
                rec.setdefault(key, clean(val))
        else:
            key = ATTR_TOP.get(head)
            val = clean(":".join(parts[1:]))
            if key and val:
                rec.setdefault(key, val)
    if rec.get("country") in COUNTRY_FA:
        rec["country"] = COUNTRY_FA[rec["country"]]
    return rec


def parse_xlsx(path: Path) -> dict[str, dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hi = next(i for i, r in enumerate(rows) if sum(c is not None for c in r) > 3)
    keys = []
    for h in rows[hi]:
        h = clean(h)
        m = re.match(r"(Dimensions and size|Specifications|Shipping Details)\s*-\s*(.+)", h, re.I)
        if m:
            k = slug(m.group(2))
            keys.append("shipping_" + k if m.group(1).lower().startswith("ship") else k)
        elif h.lower() == "product title":
            keys.append("product_title")
        else:
            keys.append(BASE_HEADERS.get(h.lower(), slug(h) if h else ""))
    out: dict[str, dict] = {}
    for r in rows[hi + 1:]:
        rec: dict[str, str] = {}
        for k, v in zip(keys, r):
            v = clean(v)
            if k and v:
                rec.setdefault(k, v)
        code = rec.get("code")
        if code:
            out.setdefault(norm(code), rec)
    return out


def finish(rec: dict) -> dict:
    if not rec.get("name_en") and rec.get("product_title"):
        rec["name_en"] = rec["product_title"]
    if rec.get("name_en"):
        rec["name_en"] = clean_name_en(rec["name_en"])
    rec.pop("product_title", None)
    if not rec.get("weight"):
        rec["weight"] = rec.get("shipping_weight", "")
    if rec.get("country") and rec["country"] in COUNTRY_FA:
        rec["country"] = COUNTRY_FA[rec["country"]]
    rec["country"] = rec.get("country", "").strip().upper()
    rec["brand"] = rec.get("brand", "").strip().upper()
    # two mounting types are stored as "Top eye | Bottom eye"
    mt = rec.get("shock_absorber_mounting_type", "")
    if mt:
        parts = [p.strip() for p in mt.split("|")]
        rec["mounting_1"] = parts[0]
        rec["mounting_2"] = parts[1] if len(parts) > 1 else parts[0]
    multi_ok = ("mounting", "fitting_position", "vehicles", "models", "supplementary", "notes", "function",
                "related", "oe", "type", "design", "material", "cat")
    for k, v in list(rec.items()):
        if "|" in v and not any(m in k for m in multi_ok):
            parts = [x.strip() for x in v.split("|")]
            rec[k] = next((x for x in parts if x.lower().endswith("mm")), parts[0])
    fp = rec.get("fitting_position", "")
    if fp:
        parts = [x.strip() for x in fp.split("|")]
        rec["fitting_position_1"] = parts[0]
        if len(parts) > 1:
            rec["fitting_position_2"] = parts[1]
    if rec.get("pack_qty") and rec.get("unit"):
        rec["qty"] = f"{rec['pack_qty']} {rec['unit']}"
    elif rec.get("pack_qty"):
        rec["qty"] = rec["pack_qty"]
    # drop empty / overly long free text that no template uses
    return {k: v for k, v in rec.items() if v and k not in ("source_url", "cross_reference_numbers", "oe_numbers")}


def main(src: Path) -> None:
    attrs: dict[str, list[dict]] = {}
    for d in ("attr", "kaan-attr"):
        for f in sorted((src / d).glob("*.txt")):
            rec = parse_attr(f)
            code = rec.get("code") or f.stem
            attrs.setdefault(norm(code), []).append(rec)
            attrs.setdefault(norm(f.stem), []).append(rec) if norm(f.stem) != norm(code) else None
    sheets = {}
    for xf, cats in SHEETS.items():
        p = src / xf
        if p.exists():
            sheets[xf] = (cats, parse_xlsx(p))
    db: dict[str, dict] = {}
    stats = {"attr": 0, "xlsx": 0, "both": 0, "none": 0}
    for cat_dir in sorted(p for p in (ROOT / "products").iterdir() if p.is_dir()):
        cat = cat_dir.name
        for f in sorted(cat_dir.iterdir()):
            if f.suffix.lower() not in EXTS or f.stem.lower() == "pack":
                continue
            k = norm(f.stem)
            rec: dict[str, str] = {}
            from_attr = from_x = False
            cands = attrs.get(k, [])
            if cands:
                rec.update(cands[0])
                from_attr = True
            for xf, (cats, rows) in sheets.items():
                if cat in cats and k in rows:
                    for kk, vv in rows[k].items():
                        rec.setdefault(kk, vv)
                    from_x = True
            stats["both" if from_attr and from_x else "attr" if from_attr else "xlsx" if from_x else "none"] += 1
            if rec:
                rec.pop("code", None)
                db[f"{cat}/{k}"] = finish(rec)
    out = ROOT / "data" / "products_db.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(db, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print(f"{len(db)} products with data -> {out}   (attr only {stats['attr']}, xlsx only {stats['xlsx']}, "
          f"both {stats['both']}, no data {stats['none']})")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "claude-product-data"))
