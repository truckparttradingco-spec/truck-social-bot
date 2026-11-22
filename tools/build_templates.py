#!/usr/bin/env python3
"""Developer tool: converts the PSD poster templates into the assets used by the bot.
(Already run - the generated files live in templates/.  Needs ImageMagick `identify`/`convert`.)

  python tools/build_templates.py /path/to/MODUL [/path/to/claude-product-data ...]

For every PSD it writes  templates/<slug>/background.png  (all *static* layers merged) and
templates/<slug>/spec.json (where text and product photos go).  Which PSD layers are
variable is decided by the MAP table below (layer index -> field)."""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent

# slug -> (psd file name, display name)
PSDS = {
    "egd": ("EGD FREN Product Poster Template.psd", "EGD FREN"),
    "abs": ("HUMMER ABS Ring Product Poster .psd", "HUMMER ABS Ring"),
    "bearing": ("HUMMER BEARING Bearing Product Poster.psd", "HUMMER Bearing"),
    "shock": ("HUMMER SHOCKABSORBER Product Poster.psd", "HUMMER Shock Absorber"),
    "kaan": ("KAAN Product Poster Template.psd", "KAAN"),
    "nok": ("NOK BPW Oil Seal Product Poster.psd", "NOK Oil Seal"),
    "wega": ("WEGA SUSPENTION Product Poster .psd", "WEGA Suspension"),
    "afre_disc": ("AFRE BRAKE DISC Product Poster .psd", "AFRE Brake Disc"),
    "afre_seal": ("AFRE OIL SEALS Infographic.psd", "AFRE Oil Seal"),
    "china": ("CHINESE TRUCK Caliper Specifications Flyer.psd", "ORGINAL Chinese Truck Caliper"),
    "adj": ("HUMMER Brake Adjuster Product Brochure.psd", "HUMMER Brake Adjuster"),
    "kaan_seal": ("KAAN Oil Seal Product Catalog Poster.psd", "KAAN Oil Seal"),
    "wega_bolt": ("WEGA Wheel Bolt Product Poster.psd", "WEGA Wheel Bolt"),
}

# text styles: cond = bold condensed (codes/values), bold = bold sans, fa = Persian
# MAP[slug][layer_idx] = ("text", field, style[, extra]) | ("image", slot[, override_box])
T = lambda f, st="cond", **kw: ("text", f, st, kw)
I = lambda slot="product", box=None: ("image", slot, box)
MAP = {
    "egd": {2: T("name_en", "bold"), 3: T("qty", "bold"), 4: I("product", (545, 520, 450, 415)),
            6: T("name_fa", "fa"), 7: T("code"), 8: T("code")},
    "kaan": {3: T("qty", "bold", fit=1.1), 4: T("qty", "bold"), 5: I("product", (545, 520, 450, 415)),
             6: T("name_en", "bold", fit=1.1), 7: T("name_en", "bold"), 8: T("code"), 9: T("code"),
             10: T("code", fit=1.1), 11: T("name_fa", "fa")},
    "abs": {2: T("name_fa", "fa"), 4: I(), 5: T("inner_diameter"), 6: T("outer_diameter"), 7: T("thickness"),
            8: T("weight"), 9: T("code"), 10: T("fitting_position"), 12: T("name_en", "bold")},
    "bearing": {2: I(), 3: T("code", fit=1.15), 4: T("code"), 5: T("inner_diameter"), 7: T("name_fa", "fa"),
                8: T("outer_diameter"), 9: T("width|height")},
    "shock": {4: I(), 5: I(), 6: T("name_fa", "fa"), 7: T("code"), 8: T("name_en", "bold"),
              9: T("shock_absorber_design"), 10: T("mounting_1"), 11: T("mounting_2"), 12: T("mounting_2"),
              13: T("mounting_1"), 14: T("shock_absorber_system"), 15: T("shock_absorber_system"),
              16: T("length_2|max_length"), 17: T("bore_diameter"), 18: T("piston_rod_diameter"), 19: T("weight"),
              20: T("piston_rod_diameter"), 21: T("bore_diameter"), 22: T("length_2|max_length")},
    "nok": {2: T("inner_diameter"), 3: T("outer_diameter"), 4: T("height|width"), 5: T("fitting_position"),
            7: T("code"), 8: I(), 9: T("name_en", "bold"), 10: T("code", fit=1.15), 11: T("name_fa", "fa")},
    "wega": {2: T("pin_diameter"), 3: T("length_2|max_length"), 5: I("product", (350, 425, 650, 225)), 6: I(),
             7: T("mounting_2"), 8: T("bore_diameter"), 9: T("bore_diameter"), 10: T("length_2|max_length"),
             11: T("spring_design"), 12: T("supplementary_article_supplementary_info"), 13: T("weight"),
             14: T("mounting_1"), 15: T("shock_absorber_system"), 16: T("name_en", "bold"), 17: T("name_fa", "fa"),
             18: T("code"), 19: T("code", rotate=-90, fit=1.15)},
    "afre_disc": {2: T("brake_disc_thickness"), 3: T("brake_disc_thickness"), 4: T("outer_diameter"),
                  5: T("outer_diameter"), 6: T("fitting_position"), 7: T("fitting_position_2"),
                  8: T("brake_disc_type"), 9: T("weight"), 11: T("name_en", "bold", fit=1.1),
                  12: T("code"), 13: T("code", fit=1.15), 14: T("name_fa", "fa"), 15: I()},
    "afre_seal": {3: I(), 4: T("code"), 5: T("name_fa", "fa"), 6: T("height"), 7: T("inner_diameter"),
                  8: T("outer_diameter")},
    "china": {4: I(), 5: T("code"), 6: T("name_fa", "fa")},
    "adj": {2: T("weight"), 3: T("number_of_holes"), 5: T("number_of_teeth"), 6: T("bore_diameter"),
            7: T("operating_mode"), 9: I(), 10: T("code"), 11: T("code", fit=1.0), 12: T("name_fa", "fa")},
    "kaan_seal": {2: T("height"), 3: T("inner_diameter"), 4: I(), 5: T("code", fit=1.15), 6: T("code"),
                  7: T("name_fa", "fa"), 8: T("name_en", "bold", fit=1.1), 9: T("outer_diameter")},
    "wega_bolt": {3: T("thread_size"), 4: T("screw_length_below_head", fit=1.0), 5: T("head_height|bolt_head_height", fit=1.0),
                  6: T("length"), 7: T("head_height|bolt_head_height"), 8: T("bolt_head_diameter"),
                  9: T("screw_length_below_head"), 10: T("bolt_head_diameter"), 11: T("thread_size"),
                  12: T("thread_length"), 14: I("product"), 15: T("name_fa", "fa"), 16: T("name_en", "bold", fit=1.1),
                  17: I("product"), 18: T("code"), 19: T("code", fit=1.15), 20: T("qty", "bold", fit=1.1)},
}


def text_geometry(a: np.ndarray):
    """For slanted text layers: (PIL rotate angle, text height, text length) from the alpha mask."""
    ys, xs = np.where(a > 60)
    if len(xs) < 40:
        return 0, 0, 0
    x, y = xs - xs.mean(), ys - ys.mean()
    w, v = np.linalg.eigh(np.cov(np.vstack([x, y])))
    major = v[:, int(np.argmax(w))]
    theta = float(np.degrees(np.arctan2(major[1], major[0])))
    if theta > 90:
        theta -= 180
    if theta <= -90:
        theta += 180
    elong = float(np.sqrt(w.max() / max(w.min(), 1e-6)))
    if 2 < abs(theta) < 45 and elong > 2.0:
        minor = v[:, int(np.argmin(w))]
        pm = x * minor[0] + y * minor[1]
        pj = x * major[0] + y * major[1]
        return round(-theta, 1), int(pm.max() - pm.min() + 1), int(pj.max() - pj.min() + 1)
    return 0, 0, 0



# Values that are printed into the PSD background but differ per product (packaging size, shock type, bolt grade).
# (search window, fields (one per text line), style, options)  - the old text is erased and re-drawn per product.
PATCHES = {
    "shock": [((385, 838, 560, 880), ["shock_absorber_type"], "reg", {}),
              ((815, 1250, 1000, 1360), ["packaging_length", "packaging_width", "packaging_height"], "reg", {})],
    "wega": [((390, 795, 560, 835), ["shock_absorber_type"], "reg", {}),
             ((835, 1215, 1010, 1330), ["packaging_length", "packaging_width", "packaging_height"], "reg", {})],
    "china": [((770, 1175, 985, 1290), ["packaging_length", "packaging_width", "packaging_height"], "reg",
               {"default": "As per Product"})],
    "wega_bolt": [((420, 935, 520, 980), ["quality_grade|strength_class"], "reg", {})],
}


def find_bands(rgb: np.ndarray, win, thr=130):
    """Text lines inside a window: list of (x, y, w, h) of the dark pixels per line."""
    x0, y0, x1, y1 = win
    g = rgb[y0:y1, x0:x1].mean(axis=2)
    dark = g < thr
    rows = np.where(dark.any(axis=1))[0]
    bands, start, prev = [], None, None
    for r in rows:
        if start is None:
            start = prev = r
        elif r - prev > 4:
            bands.append((start, prev))
            start = prev = r
        else:
            prev = r
    if start is not None:
        bands.append((start, prev))
    out = []
    for a, b in bands:
        cols = np.where(dark[a:b + 1].any(axis=0))[0]
        out.append((x0 + int(cols.min()), int(y0 + a), int(cols.max() - cols.min() + 1), int(b - a + 1)))
    return out


def layers_of(psd: Path):
    out = subprocess.run(["identify", "-format", "%p|%[label]|%g\n", str(psd)], capture_output=True, text=True).stdout
    res = []
    for line in out.strip().splitlines():
        p, label, g = line.split("|")
        w, h, x, y = map(int, re.match(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", g).groups())
        res.append(dict(idx=int(p), name=label, w=w, h=h, x=x, y=y))
    return res


def build(srcs: list[Path], slug: str):
    fname, title = PSDS[slug]
    psd = next((d / fname for d in srcs if (d / fname).exists()), None)
    if psd is None:
        print("missing PSD for", slug, fname)
        return
    ls = layers_of(psd)
    flat = subprocess.run(["convert", f"{psd}[0]", "-flatten", "png:-"], capture_output=True).stdout
    W, H = Image.open(io.BytesIO(flat)).size
    bg = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    spec = {"name": title, "size": [W, H], "images": [], "texts": []}
    for l in ls:
        if l["idx"] == 0:
            continue
        png = subprocess.run(["convert", f"{psd}[{l['idx']}]", "-background", "none", "-alpha", "set", "png32:-"],
                             capture_output=True).stdout
        im = Image.open(io.BytesIO(png)).convert("RGBA")
        m = MAP[slug].get(l["idx"])
        if m is None:                      # static layer -> goes into the background
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            layer.paste(im, (l["x"], l["y"]))
            bg.alpha_composite(layer)
            continue
        a = np.asarray(im.getchannel("A"))
        ys, xs = np.where(a > 20)
        box = [int(l["x"] + xs.min()), int(l["y"] + ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]
        rgb = np.asarray(im.convert("RGB"))[a > 200]
        color = [int(v) for v in np.median(rgb, axis=0)] if len(rgb) else [0, 0, 0]
        if m[0] == "image":
            spec["images"].append({"slot": m[1], "box": list(m[2]) if m[2] else box})
        else:
            _, field, style, extra = m
            item = {"field": field, "style": style, "box": box, "color": color, **extra}
            if "rotate" not in item and style != "fa":
                ang, cap, length = text_geometry(a)
                if ang:
                    item.update(rotate=ang, cap=cap, length=length)
            spec["texts"].append(item)
    for win, fields, style, opts in PATCHES.get(slug, []):
        arr = np.asarray(bg.convert("RGB")).astype(int)
        bands = find_bands(arr, win)
        if len(bands) != len(fields):
            print(f"  ! {slug}: expected {len(fields)} text lines in {win}, found {len(bands)} - patch skipped")
            continue
        cap = min(b[3] for b in bands)
        dr = ImageDraw.Draw(bg)
        for (bx, by, bw, bh), field in zip(bands, fields):
            region = arr[by:by + bh, bx:bx + bw].reshape(-1, 3)
            dark = region[region.mean(axis=1) < 130]
            color = [int(v) for v in np.median(dark, axis=0)] if len(dark) else [0, 0, 0]
            win_pix = arr[win[1]:win[3], win[0]:win[2]].reshape(-1, 3)
            light = win_pix[win_pix.mean(axis=1) > 215]
            fill = tuple(int(v) for v in np.median(light, axis=0)) if len(light) else (255, 255, 255)
            dr.rectangle((bx - 4, by - 3, bx + bw + 4, by + bh + 3), fill=fill + (255,))
            spec["texts"].append({"field": field, "style": style, "box": [bx, by, bw, bh], "color": color,
                                  "align": "left", "cap": int(cap), "base_y": int(by + cap), **opts})
    d = ROOT / "templates" / slug
    d.mkdir(parents=True, exist_ok=True)
    bg.convert("RGB").save(d / "background.png", optimize=True)
    (d / "spec.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")
    print(slug, "->", d)


if __name__ == "__main__":
    dirs = [Path(p) for p in (sys.argv[1:] or ["MODUL"])]
    for slug in PSDS:
        build(dirs, slug)
