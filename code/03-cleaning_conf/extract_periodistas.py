"""
extract_periodistas.py
======================
Extract journalist names and media outlets from mañanera press conference
transcripts (PREGUNTA.CSV files) using the OpenAI API.

Pipeline
--------
1. Discover all PREGUNTA.CSV files across the configured year range.
2. For each conference day, send the truncated transcript rows to GPT as a
   numbered list and ask it to identify journalist self-introductions.
3. Parse the structured JSON response into one row per (journalist × outlet × day).
4. Journalists detected without any outlet are flagged for manual review.
5. Save a resumable checkpoint every SAVE_INTERVAL files.
6. Normalize names/outlets and write the final parquet + review spreadsheet.

Output files (in OUTPUT_DIR)
-----------------------------
  periodistas_v2_all_years.parquet   — main long-format dataset
  v2_checkpoint.parquet              — incremental progress (safe to delete after run)
  v2_no_outlet_review.xlsx           — journalists with no outlet detected → fill manually
  v2_failed_dates.csv                — dates where all API retries failed → re-run separately

Usage
-----
  # Set API key first (never hardcode)
  export OPENAI_API_KEY=sk-...

  # Full run (2018-2024)
  python extract_periodistas.py

  # Quick test on a single year
  python extract_periodistas.py --years 2021

  # Custom year range
  python extract_periodistas.py --years 2021 2022 2023
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import unicodedata
from pathlib import Path
import sys

import chardet
import pandas as pd
from openai import OpenAI
from tqdm import tqdm

sys.path.append(str(Path(__file__).resolve().parents[1]))
from project_paths import media_path, media_output_path


# =============================================================================
# Configuration
# =============================================================================

BASE_PATH       = media_path("data", "02-conferences", "raw")
OUTPUT_DIR      = media_output_path("data", "02-conferences", "auxiliar", ".keep").parent
CHECKPOINT_PATH = OUTPUT_DIR / "v2_checkpoint.parquet"
FINAL_OUTPUT    = OUTPUT_DIR / "periodistas_v2_all_years.parquet"

DEFAULT_YEAR_RANGE = range(2018, 2025)

MODEL             = "gpt-4o-mini"
MAX_CHARS_PER_ROW = 150   # journalist names always appear in the first sentence
RETRY_ATTEMPTS    = 3
RETRY_DELAY       = 5     # base seconds between retries (doubles on each attempt)
SAVE_INTERVAL     = 50    # write checkpoint every N conference files


# =============================================================================
# Month name mapping (directory structure uses Spanish month names)
# =============================================================================

MONTH_TO_SPANISH = {
    1: "enero",      2: "febrero",   3: "marzo",
    4: "abril",      5: "mayo",      6: "junio",
    7: "julio",      8: "agosto",    9: "septiembre",
    10: "octubre",   11: "noviembre", 12: "diciembre",
}


# =============================================================================
# GPT prompt
# =============================================================================
# The model receives all transcript rows for one conference day as a numbered
# list (each row truncated to MAX_CHARS_PER_ROW characters).  It returns a
# JSON array of journalists with all their mentioned outlets.
#
# Design notes:
#   - We list the common Spanish self-introduction patterns explicitly so the
#     model recognises them reliably.
#   - Two-line introductions (greeting on one row, name+outlet on the next) are
#     handled because the model sees consecutive rows in order.
#   - `temperature=0` ensures deterministic extraction.
#   - `response_format={"type": "json_object"}` guarantees parseable JSON output
#     (OpenAI requires the word "JSON" to appear somewhere in the prompt).
#   - `outlets: []` signals a journalist detected with no outlet → no_outlet_flag.

SYSTEM_PROMPT = (
    "Eres un asistente especializado en extraer nombres de periodistas "
    "y sus medios de comunicación de transcripciones de conferencias de prensa "
    "del gobierno mexicano.\n\n"
    "Se te dará una lista numerada de fragmentos de texto. Cada fragmento es una "
    "línea de la transcripción. Los periodistas suelen presentarse usando frases como:\n"
    '- "Soy [Nombre], de [Medio]."\n'
    '- "[Nombre], de [Medio]."\n'
    '- "Buenos días, [Nombre], de [Medio]."\n'
    '- "[Nombre], corresponsal de [Medio], de [ciudad]."\n'
    '- "Mi nombre es [Nombre], del periódico/canal/revista [Medio]."\n'
    "- A veces la presentación está en dos líneas consecutivas: una con el saludo, "
    "otra con el nombre y medio.\n\n"
    "INSTRUCCIONES:\n"
    "1. Identifica todos los periodistas que se presentaron con su nombre.\n"
    "2. Extrae TODOS los medios que mencionaron (pueden ser varios).\n"
    '3. Si el periodista no mencionó ningún medio, usa "outlets": [] (lista vacía).\n'
    "4. Normaliza el nombre: capitalización correcta, sin títulos "
    "(señor, licenciado, etc.).\n"
    "5. El campo 'name' debe ser siempre el nombre de una persona física "
    "(nombre y apellido). NUNCA pongas el nombre de un medio de comunicación "
    "ni una frase como 'Del periódico Reforma' en el campo 'name'.\n"
    "6. NO incluyas al presidente, secretarios, subsecretarios ni otros "
    "funcionarios del gobierno, aunque se presenten. Solo periodistas y "
    "reporteros de medios de comunicación.\n"
    "7. Si no hay periodistas, devuelve una lista vacía en periodistas.\n\n"
    "FORMATO: JSON válido únicamente, sin texto adicional ni markdown.\n"
    "Devuelve siempre un objeto con esta estructura exacta:\n"
    '{"periodistas": [{"name": "Nombre Apellido", "outlets": ["Medio1", "Medio2"]}, ...]}'
)


# =============================================================================
# File discovery
# =============================================================================

def discover_all_files(base_path: Path, year_range) -> list[dict]:
    """
    Walk the nested conference directory structure and return a sorted list of
    file records for every day where a PREGUNTA.CSV exists.

    Expected directory layout:
        {base_path}/{year}/{month}-{year}/{month_sp} {day}, {year}/
            csv_por_participante/PREGUNTA.CSV

    Parameters
    ----------
    base_path : Path
        Root directory containing year-level subdirectories.
    year_range : iterable of int
        Years to scan (e.g. range(2018, 2025)).

    Returns
    -------
    list of dict, each with keys: path, date, year, month, day
    """
    records = []

    for year in year_range:
        for month in range(1, 13):
            month_sp  = MONTH_TO_SPANISH[month]
            month_dir = base_path / str(year) / f"{month}-{year}"

            if not month_dir.exists():
                continue

            for day in range(1, 32):
                day_dir = month_dir / f"{month_sp} {day}, {year}"

                # Try both upper- and lower-case filenames
                for fname in ["PREGUNTA.CSV", "PREGUNTA.csv"]:
                    csv_path = day_dir / "csv_por_participante" / fname
                    if csv_path.exists():
                        try:
                            records.append({
                                "path":  csv_path,
                                "date":  pd.Timestamp(year, month, day).date(),
                                "year":  year,
                                "month": month,
                                "day":   day,
                            })
                        except ValueError:
                            pass  # invalid calendar date (e.g. Feb 30) — skip
                        break   # no need to check the other case variant

    return sorted(records, key=lambda r: r["date"])


# =============================================================================
# CSV reading
# =============================================================================

def read_pregunta_csv(path: Path) -> pd.DataFrame | None:
    """
    Load a PREGUNTA.CSV with automatic encoding detection via chardet.

    chardet inspects the raw bytes to identify the actual encoding (utf-8,
    latin-1, cp1252, etc.), which prevents the accented-character corruption
    seen when guessing the wrong encoding.  Falls back to latin-1 if detection
    is inconclusive (confidence < 0.7).

    Returns the DataFrame if successful, or None if reading fails or the
    'Texto' column is absent.
    """
    try:
        raw = path.read_bytes()
        detected = chardet.detect(raw)
        encoding = detected["encoding"] if (detected["confidence"] or 0) >= 0.7 else "latin-1"
        df = pd.read_csv(path, encoding=encoding)
        if "Texto" in df.columns:
            return df
    except Exception:
        # chardet or pandas failed — try common encodings as fallback
        for enc in ["utf-8", "latin-1", "cp1252"]:
            try:
                df = pd.read_csv(path, encoding=enc)
                if "Texto" in df.columns:
                    return df
            except Exception:
                continue
    return None


# =============================================================================
# API call helpers
# =============================================================================

def build_user_message(rows: list[str]) -> str:
    """
    Format a list of transcript rows as a numbered list for the API prompt.

    Rows are already truncated to MAX_CHARS_PER_ROW characters by the caller.
    Numbering helps the model reference specific lines when parsing two-line
    journalist introductions.
    """
    return "\n".join(f"{i + 1}. {text.strip()}" for i, text in enumerate(rows))


def parse_journalists(parsed) -> list[dict]:
    """
    Normalise the GPT JSON response into a flat list of journalist dicts.

    The prompt asks for {"periodistas": [{...}, ...]}.  This function also
    handles fallback shapes in case the model wraps it differently.
    Each item in the returned list is guaranteed to be a dict.
    """
    if isinstance(parsed, dict):
        candidates = (
            parsed.get("periodistas")
            or parsed.get("journalists")
            or next((v for v in parsed.values() if isinstance(v, list)), [])
        )
    elif isinstance(parsed, list):
        candidates = parsed
    else:
        return []

    # Filter out any non-dict items (e.g. plain strings) to avoid .get() errors
    return [item for item in candidates if isinstance(item, dict)]


def extract_journalists(file_record: dict, client: OpenAI) -> list[dict] | None:
    """
    Extract journalist names and outlets for a single conference day.

    Sends all transcript rows (truncated) as a numbered list to GPT and parses
    the JSON response into per-(journalist, outlet) records.

    Parameters
    ----------
    file_record : dict
        A record from discover_all_files() with keys: path, date, year, month, day.
    client : OpenAI
        Initialised OpenAI client.

    Returns
    -------
    list of dict
        Each dict has: date, reporter, outlet (str or None), no_outlet_flag (bool).
        Empty list means the conference had no journalist self-introductions.
    None
        All retry attempts failed — caller should log this date for re-processing.
    """
    df = read_pregunta_csv(file_record["path"])
    if df is None or df.empty:
        return []

    # Truncate each row: journalist names always appear in the opening sentence,
    # so we don't need the full question text (which can be very long).
    rows     = df["Texto"].fillna("").str[:MAX_CHARS_PER_ROW].tolist()
    user_msg = build_user_message(rows)

    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_msg},
                ],
                temperature=0,                          # deterministic extraction
                response_format={"type": "json_object"}, # guaranteed valid JSON
                max_tokens=600,                         # ~10 journalists × ~60 tokens each
                timeout=30,
            )

            raw        = resp.choices[0].message.content.strip()
            parsed     = json.loads(raw)
            journalists = parse_journalists(parsed)

            results = []
            for j in journalists:
                name = j.get("name", "").strip()
                if not is_valid_reporter_name(name):
                    continue  # skip malformed entries, fragments, outlet names

                outlets = j.get("outlets", [])

                if outlets:
                    # One row per outlet so downstream analysis is purely long-format
                    for outlet in outlets:
                        outlet_clean = str(outlet).strip()
                        # Skip outlets that are too short to be meaningful (e.g. "tv", "W")
                        if outlet_clean and len(outlet_clean) >= 3:
                            results.append({
                                "date":           file_record["date"],
                                "reporter":       name,
                                "outlet":         outlet_clean,
                                "no_outlet_flag": False,
                            })
                else:
                    # Journalist was identified but mentioned no outlet.
                    # Flagged for manual review rather than silently dropped.
                    results.append({
                        "date":           file_record["date"],
                        "reporter":       name,
                        "outlet":         None,
                        "no_outlet_flag": True,
                    })

            return results

        except json.JSONDecodeError as e:
            print(f"  [JSON error] {file_record['date']} attempt {attempt + 1}: {e}")
            time.sleep(RETRY_DELAY)

        except Exception as e:
            # Exponential backoff — handles rate limits (HTTP 429) and transient errors
            wait = RETRY_DELAY * (2 ** attempt)
            print(f"  [API error]  {file_record['date']} attempt {attempt + 1}: {e}")
            time.sleep(wait)

    print(f"  [FAILED]     {file_record['date']} — all {RETRY_ATTEMPTS} attempts exhausted")
    return None


# =============================================================================
# Checkpoint helpers
# =============================================================================

def load_checkpoint() -> tuple[list[dict], set[str]]:
    """
    Load previously extracted rows from the checkpoint file (if it exists).

    Returns a tuple of:
      - list of already-extracted row dicts  (passed to all_results)
      - set of date strings already processed (used to skip files)
    """
    if CHECKPOINT_PATH.exists():
        df   = pd.read_parquet(CHECKPOINT_PATH)
        done = set(df["date"].astype(str).unique())
        print(f"Checkpoint loaded: {len(done)} dates already processed")
        return df.to_dict("records"), done

    print("No checkpoint found — starting fresh")
    return [], set()


def save_checkpoint(results: list[dict]) -> None:
    """Persist the accumulated results to the checkpoint parquet file."""
    if results:
        pd.DataFrame(results).to_parquet(CHECKPOINT_PATH, index=False)


# =============================================================================
# Text normalisation
# =============================================================================

# Prepositions and articles that can legitimately start an outlet name but
# should never start a person's name.  Used by is_valid_reporter_name().
# Includes English "the" to catch outlet names like "The New York Times"
_NAME_FRAGMENT_PREFIXES = re.compile(
    r"^(del|de la|de los|de las|de|el|la|los|las|un|una|the)\b",
    re.IGNORECASE,
)

# Known literal garbage values the model occasionally returns
_GARBAGE_NAMES = {"outlets", "periodistas", "nombre", "medio", "n/a", "na", "none"}


def is_valid_reporter_name(name: str) -> bool:
    """
    Return False for strings that are clearly not a person's name:
      - Fewer than 2 words (a real name needs at least first + last)
      - Starts with a preposition/article ('Del periódico...', 'La Silla Rota')
      - Matches known garbage values the model sometimes emits
      - Fewer than 5 characters total (too short to be a real name)
    """
    if not name:
        return False
    normalised = name.strip().lower()
    if normalised in _GARBAGE_NAMES:
        return False
    if len(normalised) < 5:
        return False
    if len(normalised.split()) < 2:
        return False
    if _NAME_FRAGMENT_PREFIXES.match(normalised):
        return False
    return True


def clean_name(text) -> str:
    """
    Normalise a person's name for fuzzy matching / deduplication:
      - Lowercase, strip accents, remove non-alphabetic chars, collapse spaces.
    Numbers are stripped from names (unlike outlets).
    """
    if not text or pd.isna(text):
        return ""
    text = str(text).lower()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    text = re.sub(r"[^a-z\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_outlet(text) -> str:
    """
    Normalise an outlet name for fuzzy matching / deduplication:
      - Lowercase, strip accents, remove non-alphanumeric chars, collapse spaces.
    Numbers are PRESERVED so 'Canal 11', 'Canal 40', 'ADN 40' remain distinct.
    """
    if not text or pd.isna(text):
        return ""
    text = str(text).lower()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    # Keep letters, digits, and spaces; strip punctuation
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


# =============================================================================
# Post-processing: clean, normalise, save
# =============================================================================

def build_final_dataframe(all_results: list[dict]) -> pd.DataFrame:
    """
    Convert raw extraction results into the final clean DataFrame.

    Adds normalised auxiliary columns (reporter_aux, outlet_aux) used for
    deduplication and fuzzy matching in downstream analysis.

    Output schema (long format — one row per journalist × outlet × day):
        date            datetime64   conference date
        reporter        str          name as extracted by GPT
        outlet          str | None   outlet (None when no_outlet_flag is True)
        no_outlet_flag  bool         True = journalist found but no outlet detected
        reporter_aux    str          normalised reporter name
        outlet_aux      str          normalised outlet name
    """
    df = pd.DataFrame(all_results)

    df["reporter_aux"]   = df["reporter"].apply(clean_name)
    df["outlet_aux"]     = df["outlet"].fillna("").apply(clean_outlet)
    df["date"]           = pd.to_datetime(df["date"])
    df["no_outlet_flag"] = df["no_outlet_flag"].astype(bool)

    return (
        df[["date", "reporter", "outlet", "no_outlet_flag", "reporter_aux", "outlet_aux"]]
        .sort_values(["date", "reporter_aux"])
        .reset_index(drop=True)
    )


# =============================================================================
# Validation & manual review export
# =============================================================================

def run_validation(df: pd.DataFrame, failed_dates: list[str]) -> None:
    """
    Print a summary of the extraction results and write auxiliary files:
      - v2_failed_dates.csv          — dates where all API retries failed
      - v2_no_outlet_review.xlsx     — journalist appearances with no outlet detected
      - comparison with v1 output if available
    """
    print("\n=== Extraction Summary ===")
    print(f"Total rows:         {len(df)}")
    print(f"Date range:         {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"Unique dates:       {df['date'].nunique()}")
    print(f"Unique reporters:   {df['reporter_aux'].nunique()}")
    per_day = df.groupby("date").size()
    print(f"Rows/day:           min={per_day.min()}  max={per_day.max()}  "
          f"mean={per_day.mean():.1f}")
    print(f"No-outlet flags:    {df['no_outlet_flag'].sum()}")

    # Compare against v1 output on the 2021-2023 overlap if available
    v1_path = OUTPUT_DIR / "periodistas_long_2021_2023.parquet"
    if v1_path.exists():
        df_v1   = pd.read_parquet(v1_path)
        overlap = df[df["date"].between("2021-01-01", "2023-12-31")]
        print("\n=== V1 vs V2 (2021-2023 overlap) ===")
        print(f"V2 rows:            {len(overlap)}")
        print(f"V1 rows:            {len(df_v1)}")
        print(f"V2 unique reporters:{overlap['reporter_aux'].nunique()}")
        print(f"V1 unique reporters:{df_v1['reporter_aux'].nunique()}")

    # Write failed dates for targeted re-run
    if failed_dates:
        failed_path = OUTPUT_DIR / "v2_failed_dates.csv"
        pd.Series(failed_dates, name="failed_date").to_csv(failed_path, index=False)
        print(f"\nFailed dates ({len(failed_dates)}) saved → {failed_path}")

    # Export no-outlet cases for manual review
    no_outlet = (
        df[df["no_outlet_flag"]]
        .drop_duplicates(["date", "reporter"])
        .sort_values(["date", "reporter_aux"])
        .reset_index(drop=True)
    )
    if len(no_outlet) > 0:
        review_path = OUTPUT_DIR / "v2_no_outlet_review.xlsx"
        no_outlet[["date", "reporter", "reporter_aux"]].to_excel(review_path, index=False)
        print(f"No-outlet cases ({len(no_outlet)}) saved → {review_path}")


# =============================================================================
# Main
# =============================================================================

def main(year_range) -> None:
    """Run the full extraction pipeline for the given year range."""

    # --- Initialise OpenAI client ---
    # Always prompt so the user can paste their current key.
    # Input is hidden (not echoed to terminal).
    import getpass
    api_key = getpass.getpass("Enter your OpenAI API key: ").strip()
    if not api_key:
        raise EnvironmentError("No API key provided.")
    client = OpenAI(api_key=api_key)

    # --- Discover files ---
    print(f"Scanning years: {list(year_range)}")
    all_files = discover_all_files(BASE_PATH, year_range)
    print(f"Discovered {len(all_files)} conference days with PREGUNTA.CSV\n")

    # --- Load checkpoint (resume if a previous run was interrupted) ---
    all_results, processed_dates = load_checkpoint()

    remaining = [f for f in all_files if str(f["date"]) not in processed_dates]
    print(f"To process: {len(remaining)} | Skipping (already done): {len(processed_dates)}\n")

    # --- Main extraction loop ---
    failed_dates = []

    for i, file_record in enumerate(tqdm(remaining, desc="Extracting journalists")):
        result = extract_journalists(file_record, client)

        if result is None:
            # All retries exhausted — log and continue; don't abort the whole run
            failed_dates.append(str(file_record["date"]))
        else:
            all_results.extend(result)

        # Save incremental checkpoint so progress is not lost on interruption
        if (i + 1) % SAVE_INTERVAL == 0:
            save_checkpoint(all_results)
            tqdm.write(
                f"  Checkpoint saved: {i + 1} files done, {len(failed_dates)} failures"
            )

    # Final checkpoint save before post-processing
    save_checkpoint(all_results)
    print(f"\nExtraction done. Rows collected: {len(all_results)} | "
          f"Failed dates: {len(failed_dates)}")

    if not all_results:
        print("No results to save. Exiting.")
        return

    # --- Post-processing ---
    df = build_final_dataframe(all_results)

    df.to_parquet(FINAL_OUTPUT, index=False)
    print(f"Final output saved → {FINAL_OUTPUT}  ({df.shape[0]} rows)")

    # --- Validation & review files ---
    run_validation(df, failed_dates)


# =============================================================================
# CLI entry point
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract journalist names and outlets from mañanera transcripts."
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=None,
        metavar="YEAR",
        help=(
            "Years to process (e.g. --years 2021 2022 2023). "
            "Defaults to 2018-2024."
        ),
    )
    args = parser.parse_args()

    year_range = args.years if args.years else DEFAULT_YEAR_RANGE

    main(year_range)
