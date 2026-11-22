from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import captions as cap
from . import catalog, data, hosting, poster, visuals
from .config import ROOT, contact_line
from .publishers import Facebook, Instagram, PublishError, Telegram
from .state import State

log = logging.getLogger("tsb")
MAX_ATTEMPTS = 3


def _products(cfg):
    sel = cfg.get("selection", {})
    return catalog.scan(ROOT / "products", sel.get("exclude_file_names", []), sel.get("exclude_categories", []))


def template_for(cfg: dict, product: catalog.Product) -> str | None:
    """Poster template slug for this product (by category, and by brand when the category lists brands)."""
    if not cfg.get("poster", {}).get("use_templates", True):
        return None
    spec = (cfg.get("templates") or {}).get(product.category)
    if isinstance(spec, dict):
        brand = (data.record(product.category, product.code).get("brand") or "").upper()
        spec = spec.get(brand) or spec.get("*")
    return spec if spec and poster.available(spec) else None


def make_assets(cfg: dict, product: catalog.Product, theme_idx: int, out_dir: Path) -> dict:
    """Render the images for a product. Uses the PSD-based poster template when the
    category has one (config.yaml -> templates), otherwise the automatic design.
    Returns {"post": 4:5 image, "story": 9:16 image, "wide": image for Facebook/Telegram}."""
    brand = cfg["brand"]
    cat = cfg["categories"].get(product.category, {})
    safe = product.code.replace(" ", "_").replace("/", "-")
    base = f"{product.category}_{safe}"
    slug = template_for(cfg, product)
    if slug:
        fields = data.fields_for(cfg, product.category, product.code, data.load())
        img = poster.render_poster(slug, product.path, fields)
        return {
            "template": slug,
            "wide": visuals.save_jpeg(img, out_dir / f"{base}_poster.jpg"),
            "post": visuals.save_jpeg(poster.to_feed(img), out_dir / f"{base}_post.jpg"),
            "story": visuals.save_jpeg(poster.to_story(img), out_dir / f"{base}_story.jpg"),
        }
    title = cat.get("title", product.category.title())
    group = cat.get("group", "Truck Parts")
    contact = contact_line(brand)
    out = {"template": None}
    for kind in ("post", "story"):
        img = visuals.render(product.path, product.code, title, group, brand, contact, kind, theme_idx)
        out[kind] = visuals.save_jpeg(img, out_dir / f"{base}_{kind}.jpg")
    out["wide"] = out["post"]
    return out


def calendar_pick(products: list, n: int):
    """Stateless, deterministic rotation: post number n always maps to the same product,
    categories interleave and nothing repeats until every product was shown once.
    Used for cloud cron jobs that have no persistent disk."""
    by_cat: dict[str, list] = {}
    for p in products:
        by_cat.setdefault(p.category, []).append(p)
    total = len(products)
    rng = random.Random(1000 + n // total)
    cats = sorted(by_cat)
    rng.shuffle(cats)
    for c in cats:
        rng.shuffle(by_cat[c])
    order, i = [], 0
    while len(order) < total:
        for c in cats:
            if i < len(by_cat[c]):
                order.append(by_cat[c][i])
        i += 1
    return order[n % total]


def current_slot(cfg: dict, now: datetime | None = None) -> tuple[int, int]:
    """(slot number 1.., global post counter) for a cron run: the scheduled time closest to now."""
    tz = ZoneInfo(cfg["schedule"].get("timezone", "UTC"))
    now = now or datetime.now(tz)
    times = cfg["schedule"]["posts"]
    best, best_d = 1, None
    for i, t in enumerate(times, 1):
        h, m = (int(x) for x in t.split(":"))
        d = abs((now - now.replace(hour=h, minute=m, second=0, microsecond=0)).total_seconds())
        if best_d is None or d < best_d:
            best, best_d = i, d
    day = (now.date() - datetime(2026, 1, 1).date()).days
    return best, day * len(times) + best - 1


def run_slot(cfg: dict, slot_key: str, dry_run: bool = False, only: set[str] | None = None,
             calendar_n: int | None = None) -> bool:
    """Create and publish one post (+ story). Returns True if at least one
    platform succeeded (or if dry_run)."""
    state = State(ROOT / "state" / "state.json")
    rng = random.Random()
    if calendar_n is not None:                      # stateless mode (cloud cron job)
        product = calendar_pick(_products(cfg), calendar_n)
        theme_idx = calendar_n
    else:
        product = state.pick(_products(cfg), rng)
        theme_idx = state.data["posts_total"]
    out_dir = ROOT / "output" / datetime.now().strftime("%Y-%m-%d") / slot_key.replace("#", "_slot")
    assets = make_assets(cfg, product, theme_idx, out_dir)
    post_img, story_img, wide_img = assets["post"], assets["story"], assets["wide"]
    texts = cap.build(cfg, product.category, product.code, rng)
    (out_dir / "captions.json").write_text(json.dumps(texts, indent=1, ensure_ascii=False), encoding="utf-8")
    log.info("Selected %s (%s) -> %s", product.key, assets["template"] or "auto design", out_dir)
    if dry_run:
        log.info("DRY RUN: nothing published. Files: %s, %s", post_img.name, story_img.name)
        return True

    enabled = {k for k, v in cfg["platforms"].items() if v}
    if only:
        enabled &= only
    version = cfg.get("graph_api_version", "v23.0")
    story = cfg["schedule"].get("story_with_each_post", True)
    env = dict(os.environ)
    results: dict[str, dict] = {}

    def attempt(platform: str, step: str, fn):
        try:
            res = fn()
            results.setdefault(platform, {})[step] = {"ok": True, "id": res}
            log.info("%s %s OK (%s)", platform, step, res)
        except Exception as e:                       # keep going with other platforms
            results.setdefault(platform, {})[step] = {"ok": False, "error": str(e)}
            log.error("%s %s FAILED: %s", platform, step, e)

    if "instagram" in enabled:
        try:
            ig = Instagram(env, version)
            post_url = hosting.public_url(post_img, cfg)
            attempt("instagram", "post", lambda: ig.post_photo(post_url, texts["instagram"]))
            if story:
                story_url = hosting.public_url(story_img, cfg)
                attempt("instagram", "story", lambda: ig.post_story(story_url))
        except (PublishError, hosting.HostingError) as e:
            results["instagram"] = {"setup": {"ok": False, "error": str(e)}}
            log.error("instagram setup FAILED: %s", e)

    if "facebook" in enabled:
        try:
            fb = Facebook(env, version)
            attempt("facebook", "post", lambda: fb.post_photo(wide_img, texts["facebook"]))
            if story:
                attempt("facebook", "story", lambda: fb.post_story(story_img))
        except PublishError as e:
            results["facebook"] = {"setup": {"ok": False, "error": str(e)}}
            log.error("facebook setup FAILED: %s", e)

    if "telegram" in enabled:
        try:
            tg = Telegram(env)
            attempt("telegram", "post", lambda: tg.post_photo(wide_img, texts["telegram"]))
        except PublishError as e:
            results["telegram"] = {"setup": {"ok": False, "error": str(e)}}
            log.error("telegram setup FAILED: %s", e)

    ok = any(s.get("ok") for steps in results.values() for s in steps.values())
    with open(ROOT / "logs" / "published.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "slot": slot_key,
                            "product": product.key, "results": results}, ensure_ascii=False) + "\n")
    if ok and calendar_n is None:
        state.mark_used(product)
        state.save()
    return ok


def due_slots(cfg: dict, now: datetime, state: State):
    grace = timedelta(minutes=cfg["schedule"].get("grace_minutes", 120))
    for i, t in enumerate(cfg["schedule"]["posts"], 1):
        h, m = (int(x) for x in t.split(":"))
        due = now.replace(hour=h, minute=m, second=0, microsecond=0)
        key = f"{now.date().isoformat()}#{i}"
        if now >= due and now - due <= grace and not state.is_done(key) and state.attempts(key) < MAX_ATTEMPTS:
            yield key


def tick(cfg: dict, dry_run: bool = False, now: datetime | None = None) -> int:
    """Publish every slot that is due and not yet done. Safe to call every few
    minutes from cron / Task Scheduler / the built-in loop."""
    tz = ZoneInfo(cfg["schedule"].get("timezone", "UTC"))
    now = now or datetime.now(tz)
    state = State(ROOT / "state" / "state.json")
    count = 0
    for key in list(due_slots(cfg, now, state)):
        log.info("Slot %s is due", key)
        if not dry_run:
            state.add_attempt(key)
            state.save()
        ok = run_slot(cfg, key, dry_run=dry_run)
        if ok and not dry_run:
            state = State(ROOT / "state" / "state.json")     # reload (run_slot saved)
            state.mark_done(key)
            state.save()
        count += 1
    return count
