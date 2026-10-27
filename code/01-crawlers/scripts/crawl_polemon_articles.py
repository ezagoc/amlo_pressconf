"""Collect the Polemon 2015-2025 archive through the WordPress REST API and export it."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
CRAWLER_DIR = SCRIPT_DIR.parents[0]
CODE_DIR = SCRIPT_DIR.parents[1]
REPO_ROOT = SCRIPT_DIR.parents[2]

for path in (CRAWLER_DIR, CODE_DIR, REPO_ROOT):
    sys.path.insert(0, str(path))

from crawler_core.polemon import (  # noqa: E402
    Stop,
    build_posts_table,
    clean_posts_table,
    collect_posts,
    collect_sitemap,
    export_delivery,
    now,
)
from project_paths import media_output_path  # noqa: E402


DEFAULT_STATE_DIR = REPO_ROOT / "tmp" / "articles_polemon"
DEFAULT_OUT_DIR = media_output_path("data", "00-newspaper_data", "crawler", ".keep").parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Polemon through the WordPress REST API only. collect and sitemap make requests "
            "(2.5 s apart, stop on a block or 3 errors in a row); build, clean and export are offline."
        )
    )
    parser.add_argument("step", choices=["collect", "sitemap", "build", "clean", "export"])
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR,
                        help="Raw API responses and request log. Default: <repo>/tmp/articles_polemon")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                        help="export writes <out-dir>/polemon/. Default: MEDIA_ROOT/data/00-newspaper_data/crawler")
    parser.add_argument("--pause-seconds", type=float, default=2.5)
    parser.add_argument("--export-date", default=dt.date.today().isoformat())
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    try:
        if args.step == "collect":
            collect_posts(args.state_dir, args.pause_seconds)
        elif args.step == "sitemap":
            collect_sitemap(args.state_dir, args.pause_seconds)
        elif args.step == "build":
            posts = build_posts_table(args.state_dir)
            print(f"{len(posts):,} posts -> {args.state_dir / 'polemon_posts.parquet'}")
        elif args.step == "clean":
            clean, excluded = clean_posts_table(build_posts_table(args.state_dir, save=False))
            print(f"delivered {len(clean):,}, excluded {len(excluded)}: {excluded['post_id'].tolist()}")
        else:
            report = export_delivery(args.state_dir, args.out_dir, args.export_date)
            print(json.dumps({k: report[k] for k in ("rows_collected", "rows_excluded_invalid", "rows_delivered",
                                                     "read_back_checks")}, indent=1))
    except Stop as exc:
        print(f"STOPPED: {exc}", flush=True)
        (args.state_dir / "STOPPED.txt").write_text(f"{now()} {exc}\n", encoding="utf-8")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
