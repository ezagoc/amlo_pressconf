"""Collect a WordPress source through its REST API only and export it (crawler_core/wordpress_api.py).

collect and sitemap make requests (2.5 s apart, stop on a block or 3 errors in a row); build, clean and
export are offline. Network steps are resumable: every page is saved the moment it arrives and a restart
skips pages already saved. RUNNING.lock holds the pid; creating PAUSE_REQUESTED in the state folder stops
before the next request and writes PAUSED.txt; a stop writes STOPPED.txt; a finished step writes
<STEP>_DONE.txt.

    python code/01-crawlers/scripts/crawl_wordpress_api.py collect --source noticiasdequeretaro --state-dir <dir>
    python code/01-crawlers/scripts/crawl_wordpress_api.py export --source polemon --state-dir <dir> --out-dir <dir>
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
CRAWLER_DIR = SCRIPT_DIR.parents[0]
CODE_DIR = SCRIPT_DIR.parents[1]
REPO_ROOT = SCRIPT_DIR.parents[2]

for path in (CRAWLER_DIR, CODE_DIR, REPO_ROOT):
    sys.path.insert(0, str(path))

from crawler_core.wordpress_api import SOURCES, Paused, Stop, load_source, now  # noqa: E402
from project_paths import media_output_path  # noqa: E402


def default_out_dir() -> Path:
    return media_output_path("data", "00-newspaper_data", "crawler", "articles", ".keep").parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("step", choices=["collect", "sitemap", "build", "clean", "export"])
    parser.add_argument("--source", required=True, choices=SOURCES, help="registry source_id of the newspaper")
    parser.add_argument("--state-dir", type=Path,
                        help="Raw API responses and request log. Default: <repo>/tmp/articles_<source>")
    parser.add_argument("--out-dir", type=Path,
                        help="export writes <out-dir>/<source>/. Default: MEDIA_ROOT/data/00-newspaper_data/crawler/articles")
    parser.add_argument("--sample-dir", type=Path, help="earlier sample run, for sources whose audit uses one")
    parser.add_argument("--pause-seconds", type=float)
    parser.add_argument("--export-date", default=dt.date.today().isoformat())
    return parser.parse_args()


def pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def run_network_step(source, step: str, state_dir: Path, pause: float | None) -> int:
    lock, pause_request, paused = state_dir / "RUNNING.lock", state_dir / "PAUSE_REQUESTED", state_dir / "PAUSED.txt"
    if lock.exists():
        try:
            pid = json.loads(lock.read_text(encoding="utf-8"))["pid"]
        except (OSError, ValueError, KeyError):
            pid = None
        if pid and pid_alive(pid):
            print(f"already running (pid {pid})", flush=True)
            return 1
    if (state_dir / "STOPPED.txt").exists():
        (state_dir / "stop_history").mkdir(exist_ok=True)
        (state_dir / "STOPPED.txt").replace(state_dir / "stop_history" / f"STOPPED_{now()[:19].replace(':', '')}.txt")
    lock.write_text(json.dumps({"pid": os.getpid(), "started_at_utc": now()}), encoding="utf-8")
    paused.unlink(missing_ok=True)
    print(f"{now()} {source.source_id} {step} started (pid {os.getpid()})", flush=True)
    try:
        (source.collect_posts if step == "collect" else source.collect_sitemap)(state_dir, pause)
        (state_dir / f"{step.upper()}_DONE.txt").write_text(now() + "\n", encoding="utf-8")
    except Paused:
        pause_request.unlink(missing_ok=True)
        paused.write_text(f"{now()} paused on request\n", encoding="utf-8")
        print(f"{now()} paused on request", flush=True)
    except Stop as exc:
        (state_dir / "STOPPED.txt").write_text(f"{now()} {exc}\n", encoding="utf-8")
        print(f"{now()} STOPPED: {exc}", flush=True)
        return 2
    finally:
        lock.unlink(missing_ok=True)
    return 0


def main() -> int:
    args = parse_args()
    source = load_source(args.source)
    state_dir = args.state_dir or REPO_ROOT / "tmp" / f"articles_{source.source_id}"
    state_dir.mkdir(parents=True, exist_ok=True)
    if args.step in ("collect", "sitemap"):
        return run_network_step(source, args.step, state_dir, args.pause_seconds)
    if args.step == "build":
        posts = source.build_posts_table(state_dir)
        print(f"{len(posts):,} posts -> {state_dir / f'{source.source_id}_posts.parquet'}")
    elif args.step == "clean":
        clean, excluded, duplicates = source.clean_posts_table(source.build_posts_table(state_dir, save=False))
        print(f"delivered {len(clean):,}, excluded invalid {len(excluded)}, excluded duplicate imports {len(duplicates)}")
    else:
        report = source.export_delivery(state_dir, args.out_dir or default_out_dir(), args.export_date, args.sample_dir)
        print(json.dumps({k: report[k] for k in ("rows_collected", "rows_excluded_invalid", "rows_delivered")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
