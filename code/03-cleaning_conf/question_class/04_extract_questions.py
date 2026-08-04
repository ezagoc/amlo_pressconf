"""
build_questions_dataset.py
==========================
Extract individual questions and opinion statements from mañanera transcripts
for each journalist, using GPT-4o-mini.

For each (date, journalist) pair in the periodistas dataset:
  1. Locate the raw transcript CSV for that date.
  2. Find the journalist's PREGUNTA block (consecutive rows where they spoke).
  3. Send the block to GPT and ask it to split it into individual interventions,
     classifying each as "pregunta" or "opinion".

Output
------
  questions_dataset.parquet        — one row per question/opinion
  questions_checkpoint.parquet     — resumable progress
  questions_failed.csv             — (date, reporter) pairs where all retries failed

Output schema
-------------
  date          datetime64   conference date
  reporter      str          reporter name (from periodistas)
  reporter_aux  str          normalized reporter name
  outlet        str          outlet name
  outlet_aux    str          normalized outlet name
  turn_index    int          order of this journalist within the conference
  item_index    int          order of this item within the journalist's turn
  item_type     str          "pregunta" or "opinion"
  text          str          text of the question or opinion

Usage
-----
  python build_questions_dataset.py
  python build_questions_dataset.py --start-date 2021-01-01 --end-date 2021-12-31
"""

from __future__ import annotations

import argparse
import getpass
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional
import sys

import pandas as pd
from openai import OpenAI
from tqdm import tqdm

sys.path.append(str(Path(__file__).resolve().parents[2]))
from project_paths import media_path, media_output_path


# =============================================================================
# Paths
# =============================================================================

DATA_ROOT        = media_path("data")
RAW_ROOT         = DATA_ROOT / "02-conferences/raw"
PERIODISTAS_PATH = DATA_ROOT / "02-conferences/auxiliar/periodistas_v2_all_years.parquet"
OUTPUT_DIR       = DATA_ROOT / "02-conferences/auxiliar"
CHECKPOINT_PATH  = OUTPUT_DIR / "questions_checkpoint.parquet"
FINAL_OUTPUT     = OUTPUT_DIR / "questions_dataset.parquet"
FAILED_CSV       = OUTPUT_DIR / "questions_failed.csv"

# =============================================================================
# Config
# =============================================================================

DEFAULT_START_DATE = "2018-01-01"
DEFAULT_END_DATE   = "2024-09-30"

MODEL          = "gpt-4o-mini"
RETRY_ATTEMPTS = 3
RETRY_DELAY    = 5      # base seconds; doubles on each attempt
SAVE_INTERVAL  = 100    # save checkpoint every N (date, journalist) pairs processed

MONTHS_ES = {
    1: "enero",    2: "febrero",  3: "marzo",    4: "abril",
    5: "mayo",     6: "junio",    7: "julio",     8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

# Minimum words for a journalist block to be worth sending to GPT
MIN_WORDS = 10

# =============================================================================
# System prompt
# =============================================================================

SYSTEM_PROMPT = (
    "Eres un asistente especializado en el análisis de transcripciones de conferencias "
    "de prensa del gobierno mexicano (mañaneras).\n\n"
    "Se te dará el texto completo de las intervenciones de un periodista durante "
    "una mañanera. Tu tarea es:\n"
    "1. Dividir el texto en intervenciones individuales coherentes.\n"
    "2. Clasificar cada intervención como:\n"
    "   - \"pregunta\": una pregunta o solicitud de información dirigida al presidente "
    "u otro funcionario.\n"
    "   - \"opinion\": una afirmación, comentario, introducción, saludo, o declaración "
    "que no es una pregunta.\n\n"
    "Reglas:\n"
    "- Omite saludos cortos, presentaciones de nombre/medio, y despedidas "
    "(e.g. \"Buenos días\", \"Carlos Calzada de Radio Educación\", \"Gracias.\").\n"
    "- Si un comentario largo lleva directamente a una pregunta, inclúyelo como parte "
    "de esa pregunta (un solo item).\n"
    "- Responde ÚNICAMENTE con un JSON array, sin texto adicional. Formato:\n"
    "[{\"type\": \"pregunta\"|\"opinion\", \"text\": \"...\"}]\n"
    "- Si no hay preguntas ni opiniones sustantivas, devuelve un array vacío: []"
)


# =============================================================================
# Transcript path resolution
# =============================================================================

def find_transcript_path(date: pd.Timestamp) -> Optional[Path]:
    """
    Locate the main transcript CSV for a given conference date.
    Directory structure: raw/{year}/{month}-{year}/{month_es} {day}, {year}/
    CSV filename:        mananera_{DD}_{MM}_{YYYY}.csv
    """
    y, m, d = date.year, date.month, date.day
    month_es  = MONTHS_ES[m]
    month_dir = f"{m}-{y}"
    day_dir   = f"{month_es} {d}, {y}"
    csv_name  = f"mananera_{d:02d}_{m:02d}_{y}.csv"

    candidate = RAW_ROOT / str(y) / month_dir / day_dir / csv_name
    if candidate.exists():
        return candidate
    return None


# =============================================================================
# Journalist block extraction
# =============================================================================

def _name_tokens(name: str) -> list[str]:
    """Return meaningful (>2 char) lowercase tokens from a reporter name."""
    return [t.lower() for t in name.split() if len(t) > 2]


def _name_in_text(name: str, text: str) -> bool:
    """Return True if most tokens of name appear in text (case-insensitive)."""
    tokens = _name_tokens(name)
    if not tokens:
        return False
    text_l = text.lower()
    matches = sum(1 for t in tokens if t in text_l)
    return matches >= max(1, len(tokens) - 1)  # allow one token to be missing


def extract_journalist_block(
    pregunta_df: pd.DataFrame,
    reporter: str,
    reporter_aux: str,
) -> Optional[str]:
    """
    Find the rows belonging to a specific journalist in the PREGUNTA dataframe
    and return them as a single concatenated string.

    Strategy:
      - Find the intro row where the journalist's name appears.
      - Take all consecutive rows from that intro up to (not including) the
        next intro row (where a different name appears or a clear break occurs).
    """
    if pregunta_df.empty:
        return None

    texts = pregunta_df["Texto"].fillna("").tolist()

    # Find intro row index (first row containing this journalist's name)
    intro_idx = None
    for i, t in enumerate(texts):
        if _name_in_text(reporter, t) or _name_in_text(reporter_aux, t):
            intro_idx = i
            break

    if intro_idx is None:
        return None

    # Find end of this journalist's block: the next row that looks like a
    # new intro (contains another name pattern — short text with name + comma
    # or "buenos días" / "buenas" phrasing), or end of dataframe.
    block_rows = [texts[intro_idx]]
    for i in range(intro_idx + 1, len(texts)):
        t = texts[i]
        t_lower = t.lower().strip()
        # Heuristics for a new journalist intro
        is_greeting = t_lower.startswith(("buenos", "buenas", "hola", "buen día"))
        is_short_with_comma = (len(t.split()) < 25 and "," in t and
                               any(c.isupper() for c in t.split(",")[0]))
        if (is_greeting or is_short_with_comma) and i > intro_idx + 1:
            # Check it doesn't belong to this same journalist
            if not (_name_in_text(reporter, t) or _name_in_text(reporter_aux, t)):
                break
        block_rows.append(t)

    if not block_rows:
        return None

    combined = " ".join(block_rows).strip()
    if len(combined.split()) < MIN_WORDS:
        return None
    return combined


# =============================================================================
# GPT extraction
# =============================================================================

def call_gpt_extract(
    reporter: str,
    outlet: str,
    date: pd.Timestamp,
    text_block: str,
    client: OpenAI,
) -> Optional[list[dict]]:
    """
    Send a journalist's text block to GPT and return a list of
    {"type": "pregunta"|"opinion", "text": "..."} dicts.
    Returns None if all retries fail.
    """
    user_msg = (
        f"Periodista: {reporter} ({outlet})\n"
        f"Fecha: {date.date()}\n\n"
        f"Texto de la intervención:\n{text_block}"
    )

    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_msg},
                ],
                temperature=0,
                max_tokens=1500,
                timeout=45,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content.strip()
            # GPT may wrap the array in a key; handle both
            import json
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, dict):
                # find the first list value
                items = next((v for v in parsed.values() if isinstance(v, list)), [])
            else:
                items = []
            # Validate shape
            return [
                {"type": it.get("type", "opinion"), "text": str(it.get("text", "")).strip()}
                for it in items
                if it.get("text", "").strip()
            ]
        except Exception as e:
            wait = RETRY_DELAY * (2 ** attempt)
            tqdm.write(f"  [error] {reporter} {date.date()} attempt {attempt + 1}: {e}")
            time.sleep(wait)
    return None


# =============================================================================
# Checkpoint helpers
# =============================================================================

def load_checkpoint() -> tuple[list[dict], set[str]]:
    if CHECKPOINT_PATH.exists():
        df   = pd.read_parquet(CHECKPOINT_PATH)
        done = set(df["_ckpt_key"].tolist())
        print(f"Checkpoint loaded: {len(done):,} (date, reporter) pairs already done")
        return df.to_dict("records"), done
    print("No checkpoint — starting fresh")
    return [], set()


def save_checkpoint(results: list[dict]) -> None:
    pd.DataFrame(results).to_parquet(CHECKPOINT_PATH, index=False)


# =============================================================================
# Main
# =============================================================================

def main(start_date: str, end_date: str) -> None:
    # --- API key ---
    api_key = getpass.getpass("Enter your OpenAI API key: ").strip()
    if not api_key:
        raise EnvironmentError("No API key provided.")
    client = OpenAI(api_key=api_key)

    # --- Load periodistas ---
    print("Loading periodistas...")
    periodistas = pd.read_parquet(PERIODISTAS_PATH)
    periodistas["date"] = pd.to_datetime(periodistas["date"])
    periodistas = periodistas[
        (periodistas["date"] >= start_date) &
        (periodistas["date"] <= end_date)
    ].copy()
    print(f"  {len(periodistas):,} rows  "
          f"({periodistas['date'].min().date()} → {periodistas['date'].max().date()})")

    # --- Checkpoint ---
    all_results, processed_keys = load_checkpoint()

    # --- Build work list: one entry per (date, reporter) ---
    work = periodistas.copy()
    work["_ckpt_key"] = (
        work["date"].astype(str) + "|" + work["reporter_aux"].fillna(work["reporter"])
    )
    work = work[~work["_ckpt_key"].isin(processed_keys)].reset_index(drop=True)
    print(f"  To process: {len(work):,}  |  Already done: {len(processed_keys):,}")

    # Cache loaded transcripts to avoid re-reading the same file many times
    _transcript_cache: dict[str, pd.DataFrame] = {}
    failed_keys = []

    def get_pregunta_df(date: pd.Timestamp) -> Optional[pd.DataFrame]:
        key = str(date.date())
        if key not in _transcript_cache:
            path = find_transcript_path(date)
            if path is None:
                _transcript_cache[key] = None
            else:
                try:
                    df = pd.read_csv(path, encoding="utf-8")
                    _transcript_cache[key] = df[df["Participante"] == "PREGUNTA"].reset_index(drop=True)
                except Exception as e:
                    tqdm.write(f"  [warn] could not read {path}: {e}")
                    _transcript_cache[key] = None
        return _transcript_cache[key]

    # --- Group by date to assign turn_index per day ---
    # turn_index = order in which journalists appeared that day
    date_turn_counter: dict[str, dict[str, int]] = defaultdict(dict)

    def get_turn_index(date_str: str, reporter: str) -> int:
        dc = date_turn_counter[date_str]
        if reporter not in dc:
            dc[reporter] = len(dc)
        return dc[reporter]

    n_done = 0
    n_missing_transcript = 0
    n_missing_block = 0

    for _, row in tqdm(work.iterrows(), total=len(work), desc="Extracting questions"):
        date       = row["date"]
        reporter   = row["reporter"]
        rep_aux    = row["reporter_aux"] if pd.notna(row["reporter_aux"]) else reporter
        outlet     = row["outlet"]     if pd.notna(row["outlet"])     else ""
        out_aux    = row["outlet_aux"] if pd.notna(row["outlet_aux"]) else outlet
        ckpt_key   = row["_ckpt_key"]
        date_str   = str(date.date())

        # Load transcript
        pregunta_df = get_pregunta_df(date)
        if pregunta_df is None:
            n_missing_transcript += 1
            failed_keys.append(ckpt_key)
            processed_keys.add(ckpt_key)
            continue

        # Extract journalist's block
        block = extract_journalist_block(pregunta_df, reporter, rep_aux)
        if block is None:
            n_missing_block += 1
            failed_keys.append(ckpt_key)
            processed_keys.add(ckpt_key)
            continue

        # GPT extraction
        items = call_gpt_extract(reporter, outlet, date, block, client)
        if items is None:
            failed_keys.append(ckpt_key)
            processed_keys.add(ckpt_key)
            continue

        turn_idx = get_turn_index(date_str, reporter)
        for item_idx, item in enumerate(items):
            all_results.append({
                "date":         date,
                "reporter":     reporter,
                "reporter_aux": rep_aux,
                "outlet":       outlet,
                "outlet_aux":   out_aux,
                "turn_index":   turn_idx,
                "item_index":   item_idx,
                "item_type":    item["type"],
                "text":         item["text"],
                "_ckpt_key":    ckpt_key,
            })

        processed_keys.add(ckpt_key)
        n_done += 1

        if n_done % SAVE_INTERVAL == 0:
            save_checkpoint(all_results)
            tqdm.write(f"  Checkpoint saved ({n_done} done, "
                       f"{n_missing_transcript} no-transcript, "
                       f"{n_missing_block} no-block, "
                       f"{len(failed_keys)} failed)")

    # Final checkpoint
    save_checkpoint(all_results)
    print(f"\nDone.")
    print(f"  Pairs processed:         {n_done:,}")
    print(f"  Missing transcripts:     {n_missing_transcript:,}")
    print(f"  Block not found:         {n_missing_block:,}")
    print(f"  GPT failures:            {len(failed_keys) - n_missing_transcript - n_missing_block:,}")

    # --- Build final output ---
    df = pd.DataFrame(all_results)
    df = df.drop(columns=["_ckpt_key"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "reporter", "item_index"]).reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(FINAL_OUTPUT, index=False)
    print(f"\nSaved → {FINAL_OUTPUT}")
    print(f"Shape: {df.shape}")
    print(f"Date range: {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"Unique reporters: {df['reporter'].nunique():,}")
    print(f"Questions: {(df['item_type'] == 'pregunta').sum():,}")
    print(f"Opinions:  {(df['item_type'] == 'opinion').sum():,}")

    if failed_keys:
        pd.Series(failed_keys, name="failed_key").to_csv(FAILED_CSV, index=False)
        print(f"Failed keys ({len(failed_keys)}) → {FAILED_CSV}")


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract journalist questions from mañanera transcripts.")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE,
                        help=f"Start date (YYYY-MM-DD), default: {DEFAULT_START_DATE}")
    parser.add_argument("--end-date",   default=DEFAULT_END_DATE,
                        help=f"End date   (YYYY-MM-DD), default: {DEFAULT_END_DATE}")
    args = parser.parse_args()
    main(args.start_date, args.end_date)
