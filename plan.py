#!/usr/bin/env python3
"""python plan.py [--start YYYY-MM-DD] [--days 7] [--categories seal,bearing,shock,suspension]
Renders posts + stories (random times) into media/ and writes media/plan_<start>.json."""
import argparse
from datetime import date, timedelta
from pathlib import Path

import yaml

from tsb import planner
from tsb.config import ROOT, load_config

ap = argparse.ArgumentParser()
ap.add_argument("--start", default="")
ap.add_argument("--days", type=int, default=7)
ap.add_argument("--categories", default="")
args = ap.parse_args()

cfg = load_config()
extra = yaml.safe_load((ROOT / "plan_config.yaml").read_text(encoding="utf-8"))
cfg.setdefault("captions", {}).update(extra.get("captions", {}))
cfg["planner"] = extra["planner"]
start = date.fromisoformat(args.start) if args.start else date.today() + timedelta(days=1)
cats = [c for c in args.categories.split(",") if c] or None
rows = planner.plan(cfg, start, args.days, categories=cats)
print(f"Planned {len(rows)} posts + stories from {start}")
for r in rows:
    print(f"  {r['date']} {r['time']} (story {r['story_datetime'][11:16]})  {r['product']:<24s} {r['template']}")
