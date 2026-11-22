#!/usr/bin/env python3
"""Truck Part Trading - social media autopilot.

  python main.py setup                 connection wizard: Telegram, Facebook, Instagram, image hosting
  python main.py test                  verify that every connection works
  python main.py check                 validate setup (products, fonts, credentials)
  python main.py preview --count 6     render sample posts/stories into output/preview (no publishing)
  python main.py preview --templates   one sample per PSD poster template
  python main.py export-data           create data/products.csv (names / specs for the poster templates)
  python main.py guide                 show which field goes where on each template
  python main.py post --slot 1         create + publish one post and story right now
  python main.py post --dry-run        same, but only render files + captions
  python main.py tick                  publish any scheduled slot that is due (use with cron / Task Scheduler)
  python main.py run                   stay running and publish at the scheduled times
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

from tsb import bot, catalog, data, poster, setup, visuals
from tsb import captions as cap
from tsb.config import ROOT, load_config, load_env
from tsb.state import State


def setup_logging() -> None:
    (ROOT / "logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    root = logging.getLogger("tsb")
    root.setLevel(logging.INFO)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = RotatingFileHandler(ROOT / "logs" / "bot.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(sh)
    root.addHandler(fh)


def cmd_check(cfg, args):
    products = bot._products(cfg)
    cats: dict[str, int] = {}
    for p in products:
        cats[p.category] = cats.get(p.category, 0) + 1
    print(f"Products: {len(products)} images in {len(cats)} categories")
    missing = [c for c in cats if c not in cfg["categories"]]
    if missing:
        print("  ! categories without a title in config.yaml:", ", ".join(missing))
    f = visuals.font("bold", 20)
    use: dict[str, int] = {}
    for p in products:
        use[bot.template_for(cfg, p) or "auto design"] = use.get(bot.template_for(cfg, p) or "auto design", 0) + 1
    print("Template usage:", ", ".join(f"{k}: {v}" for k, v in sorted(use.items())))
    have = sum(1 for p in products if data.record(p.category, p.code))
    print(f"Product data: {have} of {len(products)} products have information (data/products_db.json)")
    print("Font OK:", getattr(f, "path", "built-in fallback (put fonts/bold.ttf + fonts/regular.ttf for best look)"))
    logo = ROOT / cfg["brand"].get("logo", "")
    print("Logo:", "found" if logo.is_file() else "not found (initials badge will be used)")
    need = {
        "instagram": ["IG_USER_ID", "IG_ACCESS_TOKEN"],
        "facebook": ["FB_PAGE_ID", "FB_PAGE_TOKEN"],
        "telegram": ["TG_BOT_TOKEN", "TG_CHAT_ID"],
    }
    for plat, keys in need.items():
        on = cfg["platforms"].get(plat)
        miss = [k for k in keys if not os.environ.get(k)]
        print(f"{plat:10s} {'enabled ' if on else 'disabled'} credentials: {'OK' if not miss else 'missing ' + ', '.join(miss)}")
    if cfg["platforms"].get("instagram"):
        print("Image hosting for Instagram:", cfg["hosting"]["mode"])
    print("Schedule:", cfg["schedule"]["posts"], cfg["schedule"]["timezone"])


def cmd_preview(cfg, args):
    products = bot._products(cfg)
    rng = random.Random(args.seed)
    out = ROOT / "output" / "preview"
    picks = []
    if args.templates:                       # one sample per template (product that has the most data)
        by_slug: dict[str, list] = {}
        for p in products:
            slug = bot.template_for(cfg, p)
            if slug:
                by_slug.setdefault(slug, []).append(p)
        for slug, ps in sorted(by_slug.items()):
            ps.sort(key=lambda p: -len(data.record(p.category, p.code)))
            picks.append(rng.choice(ps[:5]))
    else:
        cats = sorted({p.category for p in products})
        rng.shuffle(cats)
        for i in range(args.count):
            picks.append(rng.choice([p for p in products if p.category == cats[i % len(cats)]]))
    for i, prod in enumerate(picks):
        a = bot.make_assets(cfg, prod, i, out)
        texts = cap.build(cfg, prod.category, prod.code, rng)
        print(f"- {prod.key} [{a['template'] or 'auto design'}]: {a['post'].name}, {a['story'].name}")
        if i == 0:
            print("\nSample Instagram caption:\n" + "-" * 40 + "\n" + texts["instagram"] + "\n" + "-" * 40)
    print(f"\nPreview files are in {out}")


def cmd_export_data(cfg, args):
    """Writes data/products.csv (pre-filled from the product database) with one row per templated product;
    edit any cell to override what is printed on that product's poster."""
    import csv
    products = bot._products(cfg)
    tpl_cats = {c for c, slug in (cfg.get("templates") or {}).items() if poster.available(slug)}
    fields = [f for f in poster.all_field_names() if f not in ("code",)]
    path = ROOT / "data" / "products.csv"
    existing = data.load(path)
    cols = ["category", "code"] + fields
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for p in products:
            if p.category in tpl_cats:
                row = {"category": p.category, "code": p.code}
                rec = data.record(p.category, p.code)
                row.update({k: rec[k] for k in fields if rec.get(k)})
                row.update({k: v for k, v in existing.get((p.category.lower(), p.code.upper()), {}).items() if k in cols and v})
                w.writerow(row)
    print(f"Wrote {path} - open it in Excel, fill what you know (empty cells show '-').")


def cmd_guide(cfg, args):
    """Draws every template with the name of each fillable field (to know what to put in the CSV)."""
    out = ROOT / "output" / "guides"
    out.mkdir(parents=True, exist_ok=True)
    from PIL import Image, ImageDraw
    for d in sorted((ROOT / "templates").iterdir()):
        if not (d / "spec.json").exists():
            continue
        spec = poster.load_spec(d.name)
        im = Image.open(d / "background.png").convert("RGBA")
        dr = ImageDraw.Draw(im, "RGBA")
        f = visuals.font("bold", 18)
        for t in spec["texts"]:
            x, y, w, h = t["box"]
            dr.rectangle((x - 2, y - 2, x + w + 2, y + h + 2), fill=(255, 220, 0, 150), outline=(220, 0, 0, 255))
            dr.text((x, y - 20), t["field"], font=f, fill=(200, 0, 0, 255))
        for i in spec["images"]:
            x, y, w, h = i["box"]
            dr.rectangle((x, y, x + w, y + h), outline=(0, 160, 0, 255), width=4)
            dr.text((x + 6, y + 6), "PRODUCT PHOTO", font=f, fill=(0, 140, 0, 255))
        im.convert("RGB").save(out / f"guide_{d.name}.jpg", quality=88)
    print(f"Guides saved in {out}")


def cmd_setup(cfg, args):
    setup.run_wizard(cfg)


def cmd_test(cfg, args):
    sys.exit(0 if setup.run_test(cfg, send_test=args.send_test) else 1)


def cmd_post(cfg, args):
    only = set(args.platforms.split(",")) if args.platforms else None
    if args.auto:                      # cloud cron: slot from the clock, product from the calendar (no disk needed)
        slot, n = bot.current_slot(cfg)
        key = f"{datetime.now().date().isoformat()}#cron{slot}"
        ok = bot.run_slot(cfg, key, dry_run=args.dry_run, only=only, calendar_n=n)
        sys.exit(0 if ok else 1)
    key = f"{datetime.now().date().isoformat()}#manual{args.slot}"
    ok = bot.run_slot(cfg, key, dry_run=args.dry_run, only=only)
    sys.exit(0 if ok else 1)


def cmd_tick(cfg, args):
    bot.tick(cfg, dry_run=args.dry_run)


def cmd_run(cfg, args):
    log = logging.getLogger("tsb")
    log.info("Autopilot started. Schedule: %s (%s). Press Ctrl+C to stop.",
             cfg["schedule"]["posts"], cfg["schedule"]["timezone"])
    while True:
        try:
            bot.tick(cfg, dry_run=args.dry_run)
        except Exception:
            log.exception("tick failed")
        time.sleep(30)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("preview"); p.add_argument("--count", type=int, default=6); p.add_argument("--seed", type=int, default=1)
    p.add_argument("--templates", action="store_true", help="one sample for every poster template")
    sub.add_parser("export-data"); sub.add_parser("guide"); sub.add_parser("setup")
    p = sub.add_parser("test"); p.add_argument("--send-test", action="store_true", help="also post a test message to the Telegram channel")
    p = sub.add_parser("post"); p.add_argument("--slot", type=int, default=1); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--auto", action="store_true", help="for cron jobs: pick slot/product from the clock, needs no saved state")
    p.add_argument("--platforms", help="comma list, e.g. telegram or instagram,facebook")
    p = sub.add_parser("tick"); p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("run"); p.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env()
    setup_logging()
    cfg = load_config(args.config)
    {"check": cmd_check, "preview": cmd_preview, "post": cmd_post, "tick": cmd_tick, "run": cmd_run,
     "export-data": cmd_export_data, "guide": cmd_guide, "setup": cmd_setup, "test": cmd_test}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
