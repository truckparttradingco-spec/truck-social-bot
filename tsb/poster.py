"""Fills the brand poster templates (converted from the PSD files, see templates/).

Each template folder holds  background.png  (all static layers) and  spec.json
(where the product photos and the variable texts go).  This module draws the
product photo(s) and the texts at those places, then builds the feed (4:5) and
story (9:16) versions of the poster."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

from .config import ROOT
from .visuals import fit_image, load_product, paste_with_shadow

TEMPLATES_DIR = ROOT / "templates"
_spec_cache: dict = {}


def available(slug: str) -> bool:
    return (TEMPLATES_DIR / slug / "background.png").exists()


def load_spec(slug: str) -> dict:
    if slug not in _spec_cache:
        _spec_cache[slug] = json.loads((TEMPLATES_DIR / slug / "spec.json").read_text(encoding="utf-8"))
    return _spec_cache[slug]


def all_field_names() -> list[str]:
    fields: list[str] = []
    for d in sorted(TEMPLATES_DIR.iterdir()):
        if (d / "spec.json").exists():
            for t in load_spec(d.name)["texts"]:
                for name in t["field"].split("|"):
                    if name not in fields:
                        fields.append(name)
    return fields


# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------
_FA_CANDIDATES = [
    "fonts/aviny.ttf",                     # your Persian font (clear at small sizes)
    "fonts/fa.ttf", "fonts/fa.otf",
    "C:/Windows/Fonts/tahomabd.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
    "fonts/fa-DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_FA_JAVAN = ["fonts/javan.ttf", "fonts/aviny.ttf"]   # display font for big Persian lines
_LATIN_CANDIDATES = {
    "cond": ["fonts/cond.ttf", "fonts/cond.otf"],
    "bold": ["fonts/bold.ttf", "fonts/bold.otf"],
}
_VAR_FONT = ROOT / "fonts" / "Roboto-Var.ttf"
_font_cache: dict = {}


def _first_existing(cands):
    for c in cands:
        p = Path(c)
        p = p if p.is_absolute() else ROOT / p
        if p.exists():
            return p
    return None


def get_font(style: str, size: int) -> ImageFont.FreeTypeFont:
    key = (style, size)
    if key in _font_cache:
        return _font_cache[key]
    f = None
    if style in ("fa", "fa_javan"):
        p = _first_existing(_FA_JAVAN if style == "fa_javan" else _FA_CANDIDATES)
        f = ImageFont.truetype(str(p), size) if p else ImageFont.load_default(size)
    else:
        p = _first_existing(_LATIN_CANDIDATES.get(style, []))
        if p:
            f = ImageFont.truetype(str(p), size)
        elif _VAR_FONT.exists():                       # bundled Roboto variable font
            f = ImageFont.truetype(str(_VAR_FONT), size)
            axes = {a["name"]: a for a in f.get_variation_axes()}
            vals = []
            for name, a in ((n["name"], n) for n in f.get_variation_axes()):
                if name == b"Weight":
                    vals.append(400 if style == "reg" else 700)
                elif name == b"Width":
                    vals.append(75 if style == "cond" else 100)
                else:
                    vals.append(a["default"])
            f.set_variation_by_axes(vals)
        else:
            f = ImageFont.load_default(size)
    _font_cache[key] = f
    return f


def _shape_fa(text: str) -> str:
    """Persian/Arabic needs shaping + right-to-left. Pillow does it itself when
    libraqm is present; otherwise fall back to arabic-reshaper + python-bidi."""
    if features.check("raqm"):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except ImportError:
        return text


def _has_persian(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in text)


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------
def _size_for_cap_height(style: str, cap_h: int) -> int:
    lo, hi = 6, 220
    while lo < hi:
        mid = (lo + hi + 1) // 2
        b = get_font(style, mid).getbbox("H")
        if b[3] - b[1] <= cap_h:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _size_for_width(style: str, sample: str, width: int) -> int:
    lo, hi = 8, 200
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if get_font(style, mid).getlength(sample) <= width:
            lo = mid
        else:
            hi = mid - 1
    return lo


def draw_text(canvas: Image.Image, item: dict, text: str) -> None:
    x, y, w, h = item["box"]
    style = item["style"]
    if style == "fa" and item.get("font") == "javan":
        style = "fa_javan"
    rotate = item.get("rotate", 0)
    cx, cy = x + w / 2, y + h / 2
    W, H = canvas.size
    if item.get("align") == "left":                 # erased baked text, re-drawn left aligned
        size = _size_for_cap_height(style, item["cap"])
        max_w = min(W - 14 - x, 360)
        font = get_font(style, size)
        while size > 10 and font.getlength(text) > max_w:
            size -= 1
            font = get_font(style, size)
        d = ImageDraw.Draw(canvas)
        d.text((x, item["base_y"]), text, font=font, fill=tuple(item["color"]), anchor="ls")
        return
    if style in ("fa", "fa_javan"):
        text = _shape_fa(text) if text else text
        size = _size_for_width(style, _shape_fa("نام فارسی کالا"), w)
        max_w = max(w * 1.7, 200)
    else:
        fit = item.get("fit", 1.6)               # <1.6 for texts printed on a small box label
        if "cap" in item:                        # slanted text on a box label
            size = _size_for_cap_height(style, item["cap"])
            max_w = item["length"] * max(fit, 1.0)
        else:
            size = _size_for_cap_height(style, w if rotate else h)
            max_w = max((h if rotate else w) * fit, 110 if fit >= 1.5 else 0)
    max_w = min(max_w, 2 * min(cx, W - cx) - 20) if not rotate else max_w
    cx = min(max(cx, 8), W - 8)
    font = get_font(style, size)
    while size > 10 and font.getlength(text) > max_w:
        size -= 1
        font = get_font(style, size)
    color = tuple(item["color"])
    tw = int(font.getlength(text)) + 16
    th = int(size * 2)
    layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if style in ("fa", "fa_javan"):
        d.text((tw / 2, th / 2), text, font=font, fill=color, anchor="mm")
        base_y = th / 2
    else:
        hb = font.getbbox("H")
        cap = hb[3] - hb[1]
        base_y = th / 2 + cap / 2                      # cap-height centre sits on the layer centre
        d.text((tw / 2, base_y), text, font=font, fill=color, anchor="ms")
    if rotate:
        layer = layer.rotate(rotate, expand=True, resample=Image.BICUBIC)
        canvas.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))
    elif style in ("fa", "fa_javan"):
        canvas.alpha_composite(layer, (int(cx - tw / 2), int(cy - th / 2)))
    else:
        # the new text's baseline sits on the bottom edge of the original (placeholder) text
        canvas.alpha_composite(layer, (int(cx - tw / 2), int(y + h - base_y)))


# --------------------------------------------------------------------------
# Product photo
# --------------------------------------------------------------------------
def place_image(canvas: Image.Image, box, path: Path) -> None:
    x, y, w, h = box
    im, flat = load_product(path)
    pad = 0.04
    bw, bh = int(w * (1 - 2 * pad)), int(h * (1 - 2 * pad))
    best = None
    for rot in (0, -90):
        cand = im.rotate(rot, expand=True) if rot else im
        scale = min(bw / cand.width, bh / cand.height)
        if best is None or scale > best[0] * 1.3:      # rotate only when it clearly helps
            best = (scale, cand)
    prod = fit_image(best[1], bw, bh, max_upscale=3.0)
    paste_with_shadow(canvas, prod, (x + w // 2, y + h // 2))


# --------------------------------------------------------------------------
# Whole poster
# --------------------------------------------------------------------------
def render_poster(slug: str, product_path: Path, fields: dict[str, str]) -> Image.Image:
    spec = load_spec(slug)
    canvas = Image.open(TEMPLATES_DIR / slug / "background.png").convert("RGBA")
    for img in spec["images"]:
        place_image(canvas, img["box"], product_path)
    for item in spec["texts"]:
        text = next((fields[f] for f in item["field"].split("|") if fields.get(f)), item.get("default", "-"))
        draw_text(canvas, item, text)
    return canvas.convert("RGB")


def _blurred_backdrop(poster: Image.Image, size: tuple[int, int]) -> Image.Image:
    bw, bh = size
    scale = max(bw / poster.width, bh / poster.height)
    bg = poster.resize((int(poster.width * scale) + 1, int(poster.height * scale) + 1), Image.BILINEAR)
    left, top = (bg.width - bw) // 2, (bg.height - bh) // 2
    bg = bg.crop((left, top, left + bw, top + bh)).filter(ImageFilter.GaussianBlur(40))
    dark = Image.new("RGB", size, (8, 16, 36))
    return Image.blend(bg, dark, 0.55)


def to_feed(poster: Image.Image) -> Image.Image:
    """Instagram feed only accepts 4:5 .. 1.91:1, the posters are 2:3 -> 1080x1350 canvas."""
    size = (1080, 1350)
    out = _blurred_backdrop(poster, size)
    p = poster.resize((int(poster.width * 1350 / poster.height), 1350), Image.LANCZOS)
    out.paste(p, ((1080 - p.width) // 2, 0))
    return out


def to_story(poster: Image.Image) -> Image.Image:
    """9:16 story canvas; poster kept inside the safe zone (about 250px free top/bottom)."""
    size = (1080, 1920)
    out = _blurred_backdrop(poster, size)
    th = 1420
    p = poster.resize((int(poster.width * th / poster.height), th), Image.LANCZOS)
    out.paste(p, ((1080 - p.width) // 2, (1920 - th) // 2))
    return out
