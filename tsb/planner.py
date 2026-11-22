"""Planner: renders the next N days of Instagram posts + stories (random times) into
media/<date>/ and writes media/plan_<start>.json/.csv.

A scheduler (Metricool) publishes them using the public image links, e.g.
https://raw.githubusercontent.com/<user>/<repo>/main/media/... - no social tokens needed."""
from __future__ import annotations

import csv
import json
import random
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import bot, data, poster
from . import captions_fa
from .config import ROOT


def _hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def fill_ratio(cfg: dict, prod) -> float:
    """Share of the template's data fields that this product actually has (empty cells print '-')."""
    spec = poster.load_spec(bot.template_for(cfg, prod))
    fields = data.fields_for(cfg, prod.category, prod.code)
    items = [t for t in spec["texts"] if t["field"] not in ("fitting_position_2",) and t.get("style") != "fa"]
    if not items:
        return 1.0
    ok = sum(1 for t in items if any(fields.get(n) for n in t["field"].split("|")))
    return ok / len(items)


def plan(cfg: dict, start: date, days: int, out_dir: Path | None = None, keep_days: int = 28,
         categories: list[str] | None = None) -> list[dict]:
    pl = cfg.get("planner", {})
    tz = ZoneInfo(pl.get("timezone", "UTC"))
    windows = [(_hm(a), _hm(b)) for a, b in pl.get("windows", [["09:30", "12:30"], ["17:00", "21:30"]])]
    per_day = pl.get("posts_per_day", [1, 2])
    s_lo, s_hi = pl.get("story_delay_minutes", [25, 90])
    categories = categories or pl.get("categories")
    out_dir = out_dir or ROOT / "media"
    out_dir.mkdir(parents=True, exist_ok=True)
    used_path = out_dir / "used.json"
    used: list[str] = json.loads(used_path.read_text()) if used_path.exists() else []
    used_codes = {data.norm(k.split("/", 1)[1].rsplit(".", 1)[0]) for k in used}
    rng = random.Random(start.toordinal())

    # pool: products that have data and a poster template, only the requested categories
    by_cat: dict[str, list] = {}
    for p in bot._products(cfg):
        if categories and p.category not in categories:
            continue
        if not data.record(p.category, p.code) or not bot.template_for(cfg, p):
            continue
        if fill_ratio(cfg, p) < pl.get("min_fill", 0.75):      # skip posters that would show many '-'
            continue
        by_cat.setdefault(p.category, []).append(p)
    cats = list(by_cat)
    if not cats:
        raise SystemExit("No products with data/template for categories: %s" % categories)
    rng.shuffle(cats)

    rows: list[dict] = []
    n = 0
    tmp = out_dir / "_tmp"
    for d in range(days):
        day = start + timedelta(days=d)
        count = rng.choice(per_day) if isinstance(per_day, list) else int(per_day)
        wins = list(windows) if count >= len(windows) else rng.sample(windows, count)
        wins.sort()
        for lo, hi in wins[:count]:
            cat = cats[n % len(cats)]
            fresh = [p for p in by_cat[cat] if p.key not in used and data.norm(p.code) not in used_codes]
            if not fresh:                           # everything in this category was used -> start over
                fresh = by_cat[cat]
            prod = rng.choice(fresh)
            used.append(prod.key)
            used_codes.add(data.norm(prod.code))
            minute = rng.randrange(lo, hi)
            if minute % 5 == 0:
                minute += rng.randrange(1, 5)       # never exactly on a round minute
            hh, mm = divmod(minute, 60)
            post_dt = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
            story_dt = post_dt + timedelta(minutes=rng.randrange(s_lo, s_hi))
            if story_dt.date() != post_dt.date():
                story_dt = post_dt.replace(hour=23, minute=40)
            a = bot.make_assets(cfg, prod, n, tmp)
            ddir = out_dir / day.isoformat()
            ddir.mkdir(parents=True, exist_ok=True)
            stem = f"{hh:02d}{mm:02d}_{prod.category}_{prod.code.replace(' ', '-')}"
            shutil.copy(a["post"], ddir / f"{stem}.jpg")
            shutil.copy(a["story"], ddir / f"{stem}_story.jpg")
            rows.append({
                "n": n + 1, "date": day.isoformat(), "time": post_dt.strftime("%H:%M"),
                "timezone": pl.get("timezone", "UTC"), "datetime": post_dt.isoformat(),
                "story_datetime": story_dt.isoformat(),
                "product": prod.key, "template": a["template"] or "auto",
                "image": f"media/{day.isoformat()}/{stem}.jpg",
                "story_image": f"media/{day.isoformat()}/{stem}_story.jpg",
                "caption": captions_fa.build_fa(cfg, prod.category, prod.code, rng)["instagram"],
            })
            n += 1
    shutil.rmtree(tmp, ignore_errors=True)
    used_path.write_text(json.dumps(used[-3000:]))
    stem = f"plan_{start.isoformat()}"
    (out_dir / f"{stem}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out_dir / f"{stem}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    cutoff = start - timedelta(days=keep_days)       # prune old days so the repo stays small
    for d in out_dir.iterdir():
        try:
            if d.is_dir() and date.fromisoformat(d.name) < cutoff:
                shutil.rmtree(d)
        except ValueError:
            pass
    return rows
