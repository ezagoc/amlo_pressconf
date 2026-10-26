"""Download and prepare every main Sheinbaum transcript; no model calls.

Run from anywhere with the repository .venv. Data defaults to a separate tree
under MEDIA_ROOT; --output-root can select a staging directory instead.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import quote

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
from project_paths import media_path

REPOSITORY = "NOSTRODATA/conferencias_matutinas_sheinbaum"
DEFAULT_ROOT = media_path("data", "02-conferences-sheinbaum")
FILE_RE = re.compile(r"^\d{4}/[^/]+/[^/]+/mananera_(\d{1,2})_(\d{1,2})_(\d{4})\.csv$", re.I)


def session():
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=Retry(
        total=4, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])))
    return s


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temp.replace(path)


def discover(tree, start=None, end=None):
    if tree.get("truncated"):
        raise ValueError("GitHub returned a truncated tree; refusing incomplete discovery")
    records = []
    for entry in tree["tree"]:
        match = FILE_RE.fullmatch(entry["path"])
        if not match:
            continue
        day, month, year = map(int, match.groups())
        date = pd.Timestamp(year, month, day).strftime("%Y-%m-%d")
        if (start and date < start) or (end and date > end):
            continue
        records.append({"date": date, "source_path": entry["path"], "git_blob_sha": entry["sha"]})
    records.sort(key=lambda x: (x["date"], x["source_path"]))
    if not records or len({r["date"] for r in records}) != len(records):
        raise ValueError("No transcripts found, or more than one main transcript for a date")
    return records


def blob_sha(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def download(record, root, revision):
    path = root / "raw" / record["source_path"]
    if path.exists() and blob_sha(path.read_bytes()) == record["git_blob_sha"]:
        return
    url = f"https://raw.githubusercontent.com/{REPOSITORY}/{revision}/{quote(record['source_path'])}"
    response = session().get(url, timeout=90)
    response.raise_for_status()
    if blob_sha(response.content) != record["git_blob_sha"]:
        raise ValueError(f"Git blob hash mismatch: {record['source_path']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".download")
    temp.write_bytes(response.content)
    temp.replace(path)


def normalize(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFD", str(value))
                            if unicodedata.category(c) != "Mn").upper().split()).rstrip(":")


def is_question_speaker(value):
    label = normalize(value)
    return bool(re.fullmatch(r"PREGUNTAS?(?:\s.*)?|INTERLOCUT(?:OR|ORA|ORES|ORAS|IR)(?:\s.*)?", label))


def context_dates(date):
    date = pd.Timestamp(date)
    return [date - pd.Timedelta(days=d) for d in ([3, 2, 1] if date.weekday() == 0 else [1])]


def prepare(root, tree, start=None, end=None):
    manifest = discover(tree, start, end)
    frames, conference_rows = [], []
    for record in manifest:
        path = root / "raw" / record["source_path"]
        data = path.read_bytes()
        if blob_sha(data) != record["git_blob_sha"]:
            raise ValueError(f"Raw file differs from pinned source: {path}")
        df = pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False)
        required = {"Participante", "Texto", "Dia", "Mes", "Anio"}
        if required - set(df.columns):
            raise ValueError(f"Missing columns in {path}: {required - set(df.columns)}")
        embedded_dates = pd.to_datetime(dict(year=df.Anio, month=df.Mes, day=df.Dia))
        if not embedded_dates.eq(pd.Timestamp(record["date"])).all():
            raise ValueError(f"Filename and row dates disagree: {path}")
        # Source row IDs are zero-based CSV data rows, excluding the header.
        clean = pd.DataFrame({
            "date": pd.Timestamp(record["date"]),
            "source_row": range(len(df)),
            "participant_raw": df.Participante,
            "participant": df.Participante.map(normalize),
            "text": df.Texto.astype(str).str.strip(),
            "source_path": record["source_path"],
        })
        clean["is_question_speaker"] = clean.participant.map(is_question_speaker)
        clean["word_count"] = clean.text.str.split().str.len()
        # Do not discard repeated paragraphs: they may be distinct interventions.
        frames.append(clean)
        conference_rows.append({**record, "n_rows": len(clean),
            "n_question_rows": int(clean.is_question_speaker.sum()),
            "n_empty_text_rows": int(clean.text.eq("").sum()),
            "sha256": hashlib.sha256(data).hexdigest()})
    rows = pd.concat(frames, ignore_index=True)
    question_rows = rows.loc[rows.is_question_speaker & rows.text.ne("")].copy()
    question_rows["question_row"] = question_rows.groupby("date").cumcount()
    out = root / "auxiliar"
    out.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(out / "transcript_rows.parquet", index=False)
    question_rows.to_parquet(out / "question_rows.parquet", index=False)
    question_rows.to_csv(out / "question_rows.csv", index=False)
    pd.DataFrame(conference_rows).to_csv(out / "conference_manifest.csv", index=False)
    labels = rows.groupby(["participant_raw", "participant", "is_question_speaker"]).size().reset_index(name="n_rows")
    labels.to_csv(out / "speaker_labels.csv", index=False)
    coverage = pd.DataFrame(conference_rows)
    coverage.loc[coverage.n_question_rows.eq(0)].to_csv(out / "conferences_without_question_rows_review.csv", index=False)
    coverage["month"] = coverage.date.str[:7]
    coverage.groupby("month").agg(n_conferences=("date", "size"),
        n_rows=("n_rows", "sum"), n_question_rows=("n_question_rows", "sum")).to_csv(out / "monthly_coverage.csv")
    # Weekday gaps are review candidates, never presumed missing conferences.
    weekdays = pd.bdate_range(coverage.date.min(), coverage.date.max())
    pd.DataFrame({"date": weekdays.difference(pd.to_datetime(coverage.date))}).to_csv(out / "weekday_gaps_for_review.csv", index=False)
    summaries_path = media_path("data", "00-newspaper_data", "processed", "daily_summaries.parquet")
    available = set()
    if summaries_path.exists():
        summaries = pd.read_parquet(summaries_path)
        available = set(pd.to_datetime(summaries.loc[summaries.daily_summary.fillna("").str.strip().ne(""), "date"]).dt.normalize())
    context = []
    for date in coverage.date:
        expected = context_dates(date)
        present = [d for d in expected if d in available]
        context.append({"date": date, "expected_days": len(expected), "available_days": len(present),
            "context_complete": len(expected) == len(present),
            "missing_dates": ";".join(d.strftime("%Y-%m-%d") for d in expected if d not in available)})
    pd.DataFrame(context).to_csv(out / "news_context_coverage.csv", index=False)
    report = {"repository": f"https://github.com/{REPOSITORY}", "source_revision": tree["sha"],
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "date_min": coverage.date.min(), "date_max": coverage.date.max(),
        "n_conferences": len(coverage), "n_transcript_rows": len(rows),
        "n_question_speaker_rows": len(question_rows),
        "n_conferences_without_question_rows": int(coverage.n_question_rows.eq(0).sum()),
        "n_conferences_with_complete_news_context": sum(c["context_complete"] for c in context),
        "n_weekday_gaps_for_review": len(weekdays) - len(weekdays.intersection(pd.to_datetime(coverage.date))),
        "llm_stages_status": "not run by prepare.py",
        "notes": ["All available main transcripts selected unless date filters supplied.",
                  "Question-speaker rows are paragraphs, not extracted individual questions.",
                  "Source Sentimiento is excluded: NOSTRODATA says it is not valid.",
                  "Weekday gaps can be holidays, cancellations, or missing source files."]}
    atomic_json(out / "preprocessing_report.json", report)
    atomic_json(root / "source_manifest.json", {"revision": tree["sha"], "files": conference_rows})
    print(json.dumps(report, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--tree-json", type=Path, help="Use a previously downloaded GitHub recursive tree")
    parser.add_argument("--ref", default="main")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--offline", action="store_true", help="Validate and prepare already downloaded files")
    args = parser.parse_args()
    root = args.output_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.tree_json:
        tree = json.loads(args.tree_json.read_text())
    elif args.offline:
        tree = json.loads((root / "source_tree.json").read_text())
    else:
        response = session().get(f"https://api.github.com/repos/{REPOSITORY}/git/trees/{quote(args.ref, safe='')}?recursive=1", timeout=90)
        response.raise_for_status()
        tree = response.json()
    manifest = discover(tree, args.start_date, args.end_date)
    atomic_json(root / "source_tree.json", tree)
    if not args.offline:
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda r: download(r, root, tree["sha"]), manifest))
        for name in ["README.md", "LICENSE.md"]:
            response = session().get(f"https://raw.githubusercontent.com/{REPOSITORY}/{tree['sha']}/{name}", timeout=60)
            response.raise_for_status()
            target = root / "source_metadata" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.content)
    prepare(root, tree, args.start_date, args.end_date)


if __name__ == "__main__":
    main()
