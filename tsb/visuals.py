"""Renders Instagram/Facebook posts (1080x1350) and stories (1080x1920) from a
product cut-out image: gradient + stripe background, glow, studio panel,
soft shadows, part-number badge, brand header and call-to-action footer."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .config import ROOT

# --------------------------------------------------------------------------
# Themes (rotated automatically so the feed doesn't look monotone)
# --------------------------------------------------------------------------
THEMES = [
    dict(name="orange", bg1=(12, 20, 38), bg2=(30, 41, 66), accent=(255, 122, 26),
         accent_text=(20, 20, 20), panel_c=(255, 255, 255), panel_e=(207, 216, 230)),
    dict(name="yellow", bg1=(16, 16, 18), bg2=(40, 40, 46), accent=(255, 205, 0),
         accent_text=(20, 20, 20), panel_c=(255, 255, 255), panel_e=(222, 222, 226)),
    dict(name="red", bg1=(26, 14, 20), bg2=(54, 26, 36), accent=(236, 64, 76),
         accent_text=(255, 255, 255), panel_c=(255, 255, 255), panel_e=(230, 214, 218)),
    dict(name="cyan", bg1=(8, 24, 36), bg2=(14, 52, 74), accent=(0, 190, 240),
         accent_text=(8, 24, 36), panel_c=(255, 255, 255), panel_e=(200, 222, 234)),
]

MUTED = (170, 182, 205)
WHITE = (255, 255, 255)

# --------------------------------------------------------------------------
# Layouts
# --------------------------------------------------------------------------
LAYOUTS = {
    "post": dict(
        size=(1080, 1350), header_y=46, panel=(60, 160, 1020, 1012), margin=60,
        title_y=1046, title_size=62, sub_y=1124, sub_size=28,
        btn=(60, 1196, 500, 1272), url_anchor="right", url_x=1020, url_y=1234, url_size=34,
        contact_y=1302, contact_size=24, align="left", badge_scale=1.0,
    ),
    # Stories keep ~250px free at top/bottom (Instagram UI overlays live there)
    "story": dict(
        size=(1080, 1920), header_y=262, panel=(70, 372, 1010, 1244), margin=70,
        title_y=1286, title_size=68, sub_y=1372, sub_size=30,
        btn=(190, 1456, 890, 1552), url_anchor="center", url_x=540, url_y=1604, url_size=38,
        contact_y=1664, contact_size=26, align="center", badge_scale=1.1,
    ),
}


# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------
_FONT_PATHS = {
    "bold": [
        "fonts/bold.ttf", "fonts/bold.otf",
        "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ],
    "regular": [
        "fonts/regular.ttf", "fonts/regular.otf",
        "/usr/share/fonts/opentype/inter/Inter-Medium.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ],
}
_font_cache: dict = {}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    key = (kind, size)
    if key in _font_cache:
        return _font_cache[key]
    for cand in _FONT_PATHS[kind]:
        p = Path(cand)
        p = p if p.is_absolute() else ROOT / p
        if p.exists():
            try:
                _font_cache[key] = ImageFont.truetype(str(p), size)
                return _font_cache[key]
            except OSError:
                continue
    _font_cache[key] = ImageFont.load_default(size)
    return _font_cache[key]


def fit_text(draw: ImageDraw.ImageDraw, xy, text: str, kind: str, size: int, max_w: int,
             fill, anchor="la", min_size=16) -> int:
    """Draw text, shrinking the font until it fits max_w. Returns used size."""
    while size > min_size and draw.textlength(text, font=font(kind, size)) > max_w:
        size -= 2
    draw.text(xy, text, font=font(kind, size), fill=fill, anchor=anchor)
    return size


# --------------------------------------------------------------------------
# Image helpers
# --------------------------------------------------------------------------
def vertical_gradient(size, top, bottom) -> Image.Image:
    g = Image.linear_gradient("L").resize(size)
    return Image.composite(Image.new("RGB", size, bottom), Image.new("RGB", size, top), g)


def radial_fill(size, center, edge) -> Image.Image:
    g = Image.radial_gradient("L").resize(size, Image.BICUBIC)
    return Image.composite(Image.new("RGB", size, edge), Image.new("RGB", size, center), g)


def stripes(size, color, alpha=16, gap=54, width=16) -> Image.Image:
    w, h = size
    ov = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for x in range(-h, w, gap):
        d.line([(x, h), (x + h, 0)], fill=(*color, alpha), width=width)
    return ov


def glow(size, center, radius, color, alpha=80) -> Image.Image:
    ov = Image.new("RGBA", size, (0, 0, 0, 0))
    cx, cy = center
    ImageDraw.Draw(ov).ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(*color, alpha))
    return ov.filter(ImageFilter.GaussianBlur(radius * 0.45))


def load_product(path: Path) -> tuple[Image.Image, bool]:
    """Returns (RGBA image, is_flat). Flat = fully opaque picture (box shot,
    drawing with white background) which is shown as a rounded card instead of
    a cut-out."""
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGBA")
    a = im.getchannel("A")
    hist = a.histogram()
    flat = sum(hist[250:]) / max(1, sum(hist)) > 0.97
    if not flat:
        bbox = a.point(lambda v: 255 if v > 8 else 0).getbbox()
        if bbox:
            im = im.crop(bbox)
    return im, flat


def fit_image(im: Image.Image, box_w: int, box_h: int, max_upscale=2.8) -> Image.Image:
    s = min(box_w / im.width, box_h / im.height, max_upscale)
    new = (max(1, round(im.width * s)), max(1, round(im.height * s)))
    out = im.resize(new, Image.LANCZOS)
    if s > 1.15:                      # restore crispness lost by upscaling
        r, g, b, a = out.split()
        rgb = Image.merge("RGB", (r, g, b)).filter(ImageFilter.UnsharpMask(radius=1.4, percent=70, threshold=2))
        out = Image.merge("RGBA", (*rgb.split(), a))
    return out


def rounded_alpha(im: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=radius, fill=255)
    out = im.copy()
    out.putalpha(mask)
    return out


def shadow_layer(alpha: Image.Image, blur: int, opacity: float) -> Image.Image:
    pad = blur * 3
    mask = Image.new("L", (alpha.width + pad * 2, alpha.height + pad * 2), 0)
    mask.paste(alpha, (pad, pad))
    mask = mask.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * opacity))
    layer = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    layer.putalpha(mask)
    return layer


def paste_with_shadow(canvas: Image.Image, prod: Image.Image, center: tuple[int, int]) -> None:
    x = center[0] - prod.width // 2
    y = center[1] - prod.height // 2
    a = prod.getchannel("A")
    for blur, opacity, dy in ((26, 0.30, 30), (7, 0.28, 8)):      # soft + contact shadow
        sh = shadow_layer(a, blur, opacity)
        canvas.alpha_composite(sh, (x - blur * 3, y - blur * 3 + dy))
    canvas.alpha_composite(prod, (x, y))


def corner_brackets(draw: ImageDraw.ImageDraw, box, color, length=110, width=9, gap=16) -> None:
    x0, y0, x1, y1 = box
    draw.line([(x0 - gap, y0 - gap), (x0 - gap + length, y0 - gap)], fill=color, width=width)
    draw.line([(x0 - gap, y0 - gap), (x0 - gap, y0 - gap + length)], fill=color, width=width)
    draw.line([(x1 + gap, y1 + gap), (x1 + gap - length, y1 + gap)], fill=color, width=width)
    draw.line([(x1 + gap, y1 + gap), (x1 + gap, y1 + gap - length)], fill=color, width=width)


def initials(name: str) -> str:
    letters = [w[0] for w in name.split() if w]
    return "".join(letters)[:3].upper() or "TP"


# --------------------------------------------------------------------------
# Main renderer
# --------------------------------------------------------------------------
def render(product_path: Path, code: str, title: str, group: str, brand: dict,
           contact: str, kind: str = "post", theme_idx: int = 0) -> Image.Image:
    L = LAYOUTS[kind]
    T = THEMES[theme_idx % len(THEMES)]
    W, H = L["size"]
    accent = T["accent"]

    # ---- background -------------------------------------------------------
    bg = vertical_gradient((W, H), T["bg1"], T["bg2"]).convert("RGBA")
    bg.alpha_composite(stripes((W, H), accent))
    bg.alpha_composite(glow((W, H), (int(W * 0.92), int(H * 0.08)), int(W * 0.55), accent, 95))
    bg.alpha_composite(glow((W, H), (int(W * 0.05), int(H * 0.95)), int(W * 0.45), accent, 55))
    draw = ImageDraw.Draw(bg, "RGBA")

    # ---- studio panel -----------------------------------------------------
    px0, py0, px1, py1 = L["panel"]
    pw, ph = px1 - px0, py1 - py0
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((px0, py0 + 20, px1, py1 + 20), radius=38, fill=(0, 0, 0, 150))
    bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(26)))

    panel = radial_fill((pw, ph), T["panel_c"], T["panel_e"]).convert("RGBA")
    pmask = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(pmask).rounded_rectangle((0, 0, pw - 1, ph - 1), radius=38, fill=255)
    panel.putalpha(pmask)

    # product
    prod, flat = load_product(product_path)
    pad_x, pad_top, pad_bottom = 44, 44, 128
    prod = fit_image(prod, pw - pad_x * 2, ph - pad_top - pad_bottom)
    if flat:
        prod = rounded_alpha(prod, 18)
    cy = pad_top + (ph - pad_top - pad_bottom) // 2
    paste_with_shadow(panel, prod, (pw // 2, cy))

    # part-number badge (bottom-left of the panel)
    pd = ImageDraw.Draw(panel, "RGBA")
    s = L["badge_scale"]
    lab_f, code_f = font("bold", int(20 * s)), font("bold", int(38 * s))
    code_txt = code
    while pd.textlength(code_txt, font=code_f) > pw - 260 and len(code_txt) > 6:
        code_txt = code_txt[:-1]
    bw = int(max(pd.textlength("PART NO.", font=lab_f), pd.textlength(code_txt, font=code_f)) + 52 * s)
    bh = int(76 * s)
    bx, by = 34, ph - 34 - bh
    pd.rounded_rectangle((bx, by, bx + bw, by + bh), radius=int(18 * s), fill=(*T["bg1"], 240))
    pd.rounded_rectangle((bx, by, bx + int(8 * s), by + bh), radius=int(4 * s), fill=accent)
    pd.text((bx + int(26 * s), by + int(11 * s)), "PART NO.", font=lab_f, fill=accent)
    pd.text((bx + int(26 * s), by + int(36 * s)), code_txt, font=code_f, fill=WHITE)

    bg.alpha_composite(panel, (px0, py0))
    corner_brackets(draw, L["panel"], accent)

    # ---- header (logo + name + group chip) ----------------------------------
    m, hy = L["margin"], L["header_y"]
    logo_path = ROOT / brand.get("logo", "") if brand.get("logo") else None
    logo_h = 70
    if logo_path and logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((int(logo_h * 3), logo_h))
        bg.alpha_composite(logo, (m, hy))
        name_x = m + logo.width + 18
    else:
        draw.rounded_rectangle((m, hy, m + logo_h, hy + logo_h), radius=16, fill=accent)
        draw.text((m + logo_h // 2, hy + logo_h // 2), initials(brand["name"]), font=font("bold", 27),
                  fill=T["accent_text"], anchor="mm")
        name_x = m + logo_h + 18
    chip_txt = group.upper()
    chip_f = font("bold", 22)
    chip_w = int(draw.textlength(chip_txt, font=chip_f) + 44)
    chip_x1 = W - m
    name_max = chip_x1 - chip_w - 20 - name_x
    fit_text(draw, (name_x, hy + 4), brand["name"], "bold", 38, name_max, WHITE)
    fit_text(draw, (name_x, hy + 48), brand.get("tagline", ""), "regular", 22, name_max, MUTED)
    draw.rounded_rectangle((chip_x1 - chip_w, hy + 14, chip_x1, hy + 56), radius=21, fill=accent)
    draw.text((chip_x1 - chip_w // 2, hy + 35), chip_txt, font=chip_f, fill=T["accent_text"], anchor="mm")

    # ---- footer -------------------------------------------------------------
    center = L["align"] == "center"
    tx = W // 2 if center else m
    anc = "mt" if center else "lt"
    size = fit_text(draw, (tx, L["title_y"]), title, "bold", L["title_size"], W - 2 * m, WHITE, anchor=anc)
    # accent underline
    ul_y = L["title_y"] + size + 10
    ul_w = 120
    ul_x0 = tx - ul_w // 2 if center else m
    draw.rounded_rectangle((ul_x0, ul_y, ul_x0 + ul_w, ul_y + 7), radius=3, fill=accent)
    sub = brand.get("footer_line", "Send us the part number for availability & price")
    fit_text(draw, (tx, L["sub_y"] + 8), sub, "regular", L["sub_size"], W - 2 * m, MUTED, anchor=anc)

    # CTA button
    bx0, by0, bx1, by1 = L["btn"]
    draw.rounded_rectangle((bx0, by0 + 6, bx1, by1 + 6), radius=(by1 - by0) // 2, fill=(0, 0, 0, 90))
    draw.rounded_rectangle((bx0, by0, bx1, by1), radius=(by1 - by0) // 2, fill=accent)
    cta = brand.get("cta", "REQUEST A QUOTE")
    cta_f = font("bold", 30 if kind == "post" else 34)
    tw = draw.textlength(cta, font=cta_f)
    arrow_w = 34
    start = (bx0 + bx1) / 2 - (tw + arrow_w + 14) / 2
    cy_btn = (by0 + by1) / 2
    draw.text((start, cy_btn), cta, font=cta_f, fill=T["accent_text"], anchor="lm")
    ax = start + tw + 14
    draw.line([(ax, cy_btn), (ax + arrow_w, cy_btn)], fill=T["accent_text"], width=5)
    draw.line([(ax + arrow_w - 13, cy_btn - 13), (ax + arrow_w, cy_btn), (ax + arrow_w - 13, cy_btn + 13)],
              fill=T["accent_text"], width=5, joint="curve")

    # website
    ux = L["url_x"]
    uanc = "rm" if L["url_anchor"] == "right" else "mm"
    max_url_w = (W - m - bx1 - 30) if L["url_anchor"] == "right" else W - 2 * m
    fit_text(draw, (ux, L["url_y"]), brand["website"], "bold", L["url_size"], max_url_w, WHITE, anchor=uanc)

    if contact:
        cx = W // 2 if center else m
        fit_text(draw, (cx, L["contact_y"]), contact, "regular", L["contact_size"], W - 2 * m, MUTED,
                 anchor="mm" if center else "lm")

    return bg.convert("RGB")


def save_jpeg(img: Image.Image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=93, optimize=True, subsampling=0)   # Instagram API accepts JPEG only
    return path
