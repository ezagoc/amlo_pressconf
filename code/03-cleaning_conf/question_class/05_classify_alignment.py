"""
05_classify_alignment.py
========================
Classify each journalist intervention in questions_dataset as 'aligned' or
'oppositional' with respect to the AMLO government, using GPT-4o-mini with
the relevant previous-day news context.

For each row in questions_dataset:
  1. Attach the news context for that conference date (summary of the previous
     day's political/economic news from La Jornada + 24 Horas).
  2. Send the context + item type + text to GPT.
  3. Classify as "aligned" (soft/favorable framing) or "oppositional"
     (critical/challenging).

Inputs
------
  questions_dataset.parquet          — one row per question/opinion
  daily_summaries.parquet            — one news paragraph per calendar day

Output
------
  questions_with_alignment.parquet   — questions_dataset + alignment + reason
  alignment_checkpoint.parquet       — resumable progress
  alignment_failed.csv               — row IDs where all retries failed

Usage
-----
  python 05_classify_alignment.py
  python 05_classify_alignment.py --start-date 2021-01-01 --end-date 2021-12-31
"""

from __future__ import annotations

import argparse
import getpass
import json
import time
from pathlib import Path
import sys

import pandas as pd
from openai import OpenAI
from tqdm import tqdm

sys.path.append(str(Path(__file__).resolve().parents[2]))
from project_paths import media_path, media_output_path


# =============================================================================
# Paths
# =============================================================================

DATA_ROOT      = media_path("data")
QUESTIONS_PATH = DATA_ROOT / "02-conferences/auxiliar/questions_dataset.parquet"
SUMMARIES_PATH = DATA_ROOT / "00-newspaper_data/processed/daily_summaries.parquet"
OUTPUT_DIR     = DATA_ROOT / "02-conferences/auxiliar"
CHECKPOINT_PATH = OUTPUT_DIR / "alignment_checkpoint.parquet"
FINAL_OUTPUT    = OUTPUT_DIR / "questions_with_alignment.parquet"
FAILED_CSV      = OUTPUT_DIR / "alignment_failed.csv"


# =============================================================================
# Config
# =============================================================================

DEFAULT_START_DATE = "2018-01-01"
DEFAULT_END_DATE   = "2024-09-30"

MODEL          = "gpt-4o-mini"
RETRY_ATTEMPTS = 3
RETRY_DELAY    = 5      # base seconds; doubles on each attempt
SAVE_INTERVAL  = 200    # save checkpoint every N rows processed


# =============================================================================
# System prompt (Spanish — matches the language of all input data)
# =============================================================================

SYSTEM_PROMPT = (
    "Eres un analista político especializado en conferencias de prensa presidenciales "
    "mexicanas (mañaneras). Tu tarea es clasificar la postura de una intervención "
    "periodística respecto al gobierno.\n\n"
    "Definiciones:\n"
    "- \"aligned\" (alineado): La intervención es favorable, suave o condescendiente "
    "hacia el gobierno. Incluye preguntas que validan la narrativa oficial, afirmaciones "
    "que refuerzan los logros del gobierno, o preguntas que dan al presidente la "
    "oportunidad de comunicar su mensaje sin desafío real.\n"
    "- \"oppositional\" (opositor): La intervención desafía, cuestiona o critica al "
    "gobierno. Incluye preguntas que presuponen fallos gubernamentales, denuncias de "
    "corrupción o violencia, peticiones de rendición de cuentas, o señalamientos de "
    "contradicciones entre el discurso y los hechos.\n\n"
    "Se te proporcionará:\n"
    "1. Un resumen de las noticias del día anterior a la conferencia.\n"
    "2. El tipo de intervención (pregunta u opinión).\n"
    "3. El texto de la intervención.\n\n"
    "Responde ÚNICAMENTE con un objeto JSON con exactamente dos campos:\n"
    "{\"alignment\": \"aligned\" | \"oppositional\", \"reason\": \"<una sola oración>\"}\n"
    "No incluyas texto fuera del JSON."
)


# =============================================================================
# Context date logic
# (Copied from 03_attach_news_context.py — kept inline for self-containment)
# =============================================================================

def get_context_dates(conf_date: pd.Timestamp) -> list[pd.Timestamp]:
    """
    Return the list of calendar dates whose news provides context for conf_date.

    Monday  → [preceding Friday, Saturday, Sunday]
    Tue–Fri → [previous calendar day]
    """
    dow = conf_date.weekday()  # 0=Mon … 6=Sun
    if dow == 0:  # Monday
        return [
            conf_date - pd.Timedelta(days=3),  # Friday
            conf_date - pd.Timedelta(days=2),  # Saturday
            conf_date - pd.Timedelta(days=1),  # Sunday
        ]
    else:  # Tuesday–Friday
        return [conf_date - pd.Timedelta(days=1)]


# =============================================================================
# Pre-build context map
# =============================================================================

def build_context_map(
    summaries: pd.DataFrame,
    conf_dates: list[pd.Timestamp],
) -> dict[pd.Timestamp, str | None]:
    """
    Build a {conf_date: context_str | None} dict for all unique conference dates.
    context_str concatenates one or more daily summaries with date headers.
    Pre-computing this once avoids redundant work in the main loop.
    """
    summaries_idx = summaries.set_index("date")
    result: dict[pd.Timestamp, str | None] = {}

    for conf_date in conf_dates:
        cdates = get_context_dates(conf_date)
        parts = []
        for d in cdates:
            if d in summaries_idx.index:
                label = d.strftime("%A %Y-%m-%d")
                parts.append(f"[{label}]\n{summaries_idx.loc[d]['daily_summary']}")
        result[conf_date] = "\n\n".join(parts) if parts else None

    return result


# =============================================================================
# Checkpoint helpers
# =============================================================================

def load_checkpoint() -> tuple[list[dict], set[int]]:
    if CHECKPOINT_PATH.exists():
        df   = pd.read_parquet(CHECKPOINT_PATH)
        done = set(df["_row_id"].tolist())
        print(f"Checkpoint loaded: {len(done):,} rows already done")
        return df.to_dict("records"), done
    print("No checkpoint — starting fresh")
    return [], set()


def save_checkpoint(results: list[dict]) -> None:
    if results:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(results).to_parquet(CHECKPOINT_PATH, index=False)


# =============================================================================
# GPT classification
# =============================================================================

def call_gpt_classify(
    text: str,
    item_type: str,
    context_str: str | None,
    client: OpenAI,
) -> dict | None:
    """
    Classify one intervention as 'aligned' or 'oppositional'.
    Returns {"alignment": ..., "reason": ...} or None if all retries fail.
    """
    context_block = context_str if context_str else "(Sin contexto disponible)"
    user_msg = (
        f"Contexto de noticias del día anterior:\n{context_block}\n\n"
        f"Tipo de intervención: {item_type}\n\n"
        f"Texto:\n{text}"
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
                max_tokens=150,
                timeout=30,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content.strip()
            parsed = json.loads(raw)

            # Validate structure
            alignment = parsed.get("alignment", "")
            reason    = str(parsed.get("reason", "")).strip()
            if alignment in {"aligned", "oppositional"} and reason:
                return {"alignment": alignment, "reason": reason}
            raise ValueError(f"Invalid JSON structure: {parsed}")

        except Exception as e:
            wait = RETRY_DELAY * (2 ** attempt)
            tqdm.write(f"  [error] attempt {attempt + 1}: {e}")
            time.sleep(wait)

    return None


# =============================================================================
# Main
# =============================================================================

def main(start_date: str, end_date: str) -> None:
    # --- API key ---
    api_key = getpass.getpass("Enter your OpenAI API key: ").strip()
    if not api_key:
        raise EnvironmentError("No API key provided.")
    client = OpenAI(api_key=api_key)

    # --- Load questions dataset ---
    print("Loading questions dataset...")
    q = pd.read_parquet(QUESTIONS_PATH)
    q["date"] = pd.to_datetime(q["date"])
    q = q[(q["date"] >= start_date) & (q["date"] <= end_date)].copy()
    q = q.reset_index(drop=True)
    q["_row_id"] = q.index   # stable unique key (source file is static)
    print(f"  {len(q):,} rows  ({q['date'].min().date()} → {q['date'].max().date()})")

    # --- Load summaries and build context map ---
    print("Loading daily summaries and building context map...")
    summaries = pd.read_parquet(SUMMARIES_PATH)
    summaries["date"] = pd.to_datetime(summaries["date"])
    unique_conf_dates = q["date"].drop_duplicates().tolist()
    context_map = build_context_map(summaries, unique_conf_dates)
    n_with_ctx = sum(1 for v in context_map.values() if v is not None)
    print(f"  {n_with_ctx}/{len(context_map)} conference dates have news context")

    # --- Checkpoint ---
    all_results, done_ids = load_checkpoint()
    work = q[~q["_row_id"].isin(done_ids)].copy()
    print(f"  To classify: {len(work):,}  |  Already done: {len(done_ids):,}")

    # --- Main loop ---
    failed_ids: list[int] = []
    n_done = 0

    for _, row in tqdm(work.iterrows(), total=len(work), desc="Classifying alignment"):
        row_id      = int(row["_row_id"])
        conf_date   = row["date"]
        context_str = context_map.get(conf_date)

        result = call_gpt_classify(
            text=row["text"],
            item_type=row["item_type"],
            context_str=context_str,
            client=client,
        )

        if result is None:
            failed_ids.append(row_id)
            done_ids.add(row_id)
            continue

        all_results.append({
            "date":         conf_date,
            "reporter":     row["reporter"],
            "reporter_aux": row["reporter_aux"],
            "outlet":       row["outlet"],
            "outlet_aux":   row["outlet_aux"],
            "turn_index":   row["turn_index"],
            "item_index":   row["item_index"],
            "item_type":    row["item_type"],
            "text":         row["text"],
            "alignment":    result["alignment"],
            "reason":       result["reason"],
            "_row_id":      row_id,
        })

        done_ids.add(row_id)
        n_done += 1

        if n_done % SAVE_INTERVAL == 0:
            save_checkpoint(all_results)
            tqdm.write(
                f"  Checkpoint saved ({n_done} classified, {len(failed_ids)} failed)"
            )

    # Final checkpoint
    save_checkpoint(all_results)
    print(f"\nDone. Classified: {n_done:,}  |  Failed: {len(failed_ids):,}")

    # --- Build final output ---
    if not all_results:
        print("No results to save.")
        return

    df_out = pd.DataFrame(all_results).drop(columns=["_row_id"])
    df_out["date"] = pd.to_datetime(df_out["date"])
    df_out = (
        df_out
        .sort_values(["date", "reporter", "turn_index", "item_index"])
        .reset_index(drop=True)
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df_out.to_parquet(FINAL_OUTPUT, index=False)
    print(f"\nSaved → {FINAL_OUTPUT}  shape: {df_out.shape}")

    # --- Summary stats ---
    print("\n=== Alignment distribution ===")
    print(df_out["alignment"].value_counts().to_string())
    print("\n=== By item_type × alignment ===")
    print(
        df_out.groupby(["item_type", "alignment"])
              .size()
              .unstack(fill_value=0)
              .to_string()
    )

    if failed_ids:
        pd.Series(failed_ids, name="row_id").to_csv(FAILED_CSV, index=False)
        print(f"\nFailed rows ({len(failed_ids)}) → {FAILED_CSV}")


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Classify journalist interventions as aligned/oppositional."
    )
    parser.add_argument(
        "--start-date", default=DEFAULT_START_DATE, metavar="YYYY-MM-DD",
        help=f"Start date (inclusive). Default: {DEFAULT_START_DATE}",
    )
    parser.add_argument(
        "--end-date", default=DEFAULT_END_DATE, metavar="YYYY-MM-DD",
        help=f"End date (inclusive). Default: {DEFAULT_END_DATE}",
    )
    args = parser.parse_args()
    main(args.start_date, args.end_date)
