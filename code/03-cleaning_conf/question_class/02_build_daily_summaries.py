"""
article_classification.py
=========================
Generate a one-paragraph daily news summary from La Jornada and 24 Horas
articles using the OpenAI API.

For each calendar day in the date range the pipeline:
  1. Loads articles from both newspaper parquet files, filtered by topic.
  2. For La Jornada: uses the summary field when available, otherwise the title.
     For 24 Horas: uses the title only.
  3. Groups articles by day and sends the full list to GPT — labelled by source
     so the model knows their editorial alignment — and asks for a single
     paragraph summarising the main events of that day.
  4. Saves a resumable checkpoint every SAVE_INTERVAL days.

Output files (in OUTPUT_DIR)
-----------------------------
  daily_summaries.parquet          — main output: one row per day
  daily_summaries_checkpoint.parquet — incremental progress (safe to delete)
  daily_summaries_failed.csv       — dates where all retries failed

Source editorial alignment
--------------------------
  La Jornada  — left-leaning, editorially aligned with the AMLO government.
  24 Horas    — editorially oppositional to the government.

Usage
-----
  # Full run (default: 2018-01-01 to 2024-09-30)
  python article_classification.py

  # Custom date range
  python article_classification.py --start-date 2021-01-01 --end-date 2021-12-31
"""

from __future__ import annotations

import argparse
import os
import time
from collections import defaultdict
from pathlib import Path
import sys

import pandas as pd
from openai import OpenAI
from tqdm import tqdm

sys.path.append(str(Path(__file__).resolve().parents[2]))
from project_paths import media_path, media_output_path


# =============================================================================
# Configuration
# =============================================================================

DATA_ROOT   = media_path("data", "00-newspaper_data")
OUTPUT_DIR  = media_output_path("data", "00-newspaper_data", "processed", ".keep").parent

CHECKPOINT_PATH = OUTPUT_DIR / "daily_summaries_checkpoint.parquet"
FINAL_OUTPUT    = OUTPUT_DIR / "daily_summaries.parquet"
FAILED_CSV      = OUTPUT_DIR / "daily_summaries_failed.csv"

DEFAULT_START_DATE = "2018-01-01"
DEFAULT_END_DATE   = "2024-09-30"

MODEL          = "gpt-4o-mini"
RETRY_ATTEMPTS = 3
RETRY_DELAY    = 5      # base seconds; doubles on each attempt
SAVE_INTERVAL  = 50     # write checkpoint every N days processed


# =============================================================================
# Source configuration
# =============================================================================
# To add a new newspaper: add an entry here. No other changes needed.
#
# Keys:
#   path           — parquet file path
#   title_col      — column containing the article title
#   summary_col    — column containing a summary (None → always use title)
#   topic_col      — column containing the topic/section tag
#   tz_aware       — True if dates are stored as UTC-aware timestamps (24H files)
#   label          — editorial description shown to GPT in the prompt
#   topic_allowlist— set of topic strings to keep (pre-filter before sending to API)

SOURCES: dict[str, dict] = {
    "jornada": {
        "path":           DATA_ROOT / "crawler/jornada/articles_final.parquet",
        "title_col":      "title",
        "summary_col":    "summary",   # use summary when available
        "topic_col":      "topic",
        "tz_aware":       False,
        "label":          "La Jornada (línea editorial afín al gobierno)",
        "topic_allowlist": {
            "politica", "opinion", "economia", "estados", "capital", "sociedad",
        },
    },
    "cdmx_24h": {
        "path":           DATA_ROOT / "crawler/horas24/articles_cdmx_final.parquet",
        "title_col":      "title",
        "summary_col":    None,        # titles only for 24 Horas
        "topic_col":      "topic",
        "tz_aware":       True,
        "label":          "24 Horas (línea editorial opositora)",
        "topic_allowlist": {
            # --- Política ---
            "Política", "AMLO", "EPN", "Sheinbaum", "Gobernadores", "Alcaldes",
            "Alcaldes y Gobernadores", "Desde las Cámaras Legislativas", "Congreso",
            "Elecciones 2018", "Elecciones 2021", "Elecciones 2022",
            "Elecciones EU", "Elecciones EUA", "Elecciones Edomex", "Elecciones MX",
            "Elección 2019", "Donald Trump", "AMLO Rinde Protesta", "Consulta NAIM",
            "revocación de mandato", "Reforma Eléctrica", "Reforma electoral",
            "Cuarto informe de AMLO", "Marcha por el INE",
            "La Divisa del Poder", "Teléfono Rojo", "Hechos y Susurros",
            "Nomenklatura del Poder", "Actos de Poder", "Tablero Político",
            "Itinerario Politico", "Votos y Billetes", "Reporte Lobby",
            "Indebidos Procesos", "Emilio Lozoya", "Javier Duarte", "Roberto Borge",
            "Alfredo del Mazo", "Fideicomisos", "Guacamaya Leaks",
            "Genaro García Luna", "Salvador Cienfuegos",
            "Captura de Ovidio Guzmán", "Captura de Caro Quintero",
            "Opinión", "Columnas", "México", "LOS OTROS DATOS",
            "EXPEDIENTE", "SIN DISTORSIONES", "Obituario - Política",
            # --- Seguridad ---
            "Justicia", "Estado-Justicia", "Ciudad-Justicia", "Seguridad",
            "Agenda de Seguridad y Defensa", "Guardia Nacional",
            "Feminicidio", "Feminicidios", "Derechos Humanos", "Ayotzinapa",
            "El Chapo", "Cerocahui", "sabinas", "Ariadna Fernanda",
            "Debanhi Escobar", "Desaparecidos", "Caso Zona Rosa", "Balacera AICM",
            "Migración", "Caravana Migrante", "Caravana Migrante pf",
            "Sin Fronteras", "Migrantes",
            # --- Economía ---
            "Economía", "Economia", "econo", "Indicadores economicos",
            "Negocios", "Negocios - columnas", "Finanzas24 y Negocios",
            "T-MEC", "USMCA", "Pemex", "CFE", "Petróleo",
            "Desabasto de combustibles", "Split Financiero",
            "Coronavirus Economía", "Apuntes Macro", "AIFA", "Aeropuerto",
            "Tren Maya", "Empresarios del Campo", "Presupuesto 2020",
            "Desde la Banca", "Desde el piso de remates",
            # --- Estados ---
            "Estados", "CDMX", "Quintana Roo", "San Luis Potosí",
            "Aguascalientes", "Guerrero", "Puebla", "Edomex", "Sinaloa",
            "Sonora", "Querétaro", "Baja California Sur", "Yucatán",
            "Hidalgo", "Tlaxcala", "Durango", "Naucalpan", "Oaxaca",
            "Morelos", "Nezahualcóyotl", "Campeche", "Jalisco", "Coahuila",
            "Tamaulipas", "Nuevo León", "Guanajuato", "Chiapas", "Huixquilucan",
        },
    },
}


# =============================================================================
# GPT prompt
# =============================================================================

SYSTEM_PROMPT = (
    "Eres un asistente especializado en el análisis de noticias mexicanas.\n"
    "Se te proporcionará una lista numerada de artículos periodísticos publicados "
    "en un mismo día en México, provenientes de dos fuentes con distintas líneas editoriales:\n"
    "- La Jornada: periódico de izquierda con línea editorial afín al gobierno de AMLO.\n"
    "- 24 Horas: periódico con línea editorial opositora al gobierno.\n\n"
    "Tu tarea: redactar UN párrafo en español (máximo 150 palabras) que describa "
    "los principales eventos, temas y noticias del día cubiertos en esos artículos.\n"
    "Enfócate en política, economía, seguridad y asuntos de gobierno.\n"
    "Sé específico: menciona actores, instituciones y eventos concretos cuando aparezcan.\n"
    "No hagas listas. Solo el párrafo, sin introducción ni conclusión."
)


# =============================================================================
# Data loading
# =============================================================================

def get_text_per_article(row: dict, cfg: dict) -> str:
    """Return the summary if available and non-empty, otherwise the title."""
    if cfg["summary_col"]:
        s = str(row.get(cfg["summary_col"]) or "").strip()
        if s:
            return s
    return str(row.get(cfg["title_col"]) or "").strip()


def load_source(source_name: str, cfg: dict, date_range: tuple[str, str]) -> pd.DataFrame:
    """
    Load one parquet source, apply date + topic filters, and return a DataFrame
    with columns: date_only (date), label (str), text (str).
    """
    df = pd.read_parquet(cfg["path"])
    df = df.drop_duplicates(subset="url")

    if cfg["tz_aware"]:
        df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
    else:
        df["date"] = pd.to_datetime(df["date"])

    start, end = date_range
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    df["date_only"] = df["date"].dt.date

    topic_col = cfg["topic_col"]
    df[topic_col] = df[topic_col].fillna("").astype(str)
    df = df[df[topic_col].isin(cfg["topic_allowlist"])].copy()

    rows = df.to_dict("records")
    df["text"]  = [get_text_per_article(r, cfg) for r in rows]
    df["label"] = cfg["label"]
    df = df[df["text"].str.len() > 0]

    print(f"  {source_name}: {len(df):,} articles after filter")
    return df[["date_only", "label", "text"]]


def build_daily_entries(date_range: tuple[str, str]) -> pd.DataFrame:
    """
    Load all sources, concatenate, and group by calendar day.

    Returns a DataFrame with columns:
        date    — calendar date
        entries — list of (label, text) tuples for that day
    """
    frames = [load_source(name, cfg, date_range) for name, cfg in SOURCES.items()]
    all_articles = pd.concat(frames, ignore_index=True)
    all_articles["_entry"] = list(zip(all_articles["label"], all_articles["text"]))

    daily = (
        all_articles
        .groupby("date_only")["_entry"]
        .apply(list)
        .reset_index()
        .rename(columns={"date_only": "date", "_entry": "entries"})
    )

    print(f"\nDays with articles: {len(daily):,}")
    print(f"Total article texts: {len(all_articles):,}")
    print(f"Avg articles/day:   {len(all_articles) / len(daily):.1f}")
    return daily


# =============================================================================
# Prompt builder
# =============================================================================

def build_user_message(entries: list[tuple[str, str]]) -> str:
    """
    Format a day's (label, text) entries as a source-labelled block list.

    Example output:
        Artículos del día:

        [La Jornada (línea editorial afín al gobierno)]
          1. Resumen del artículo A
          2. Resumen del artículo B

        [24 Horas (línea editorial opositora)]
          1. Título del artículo C
    """
    by_source: dict[str, list[str]] = defaultdict(list)
    for label, text in entries:
        by_source[label].append(text)

    blocks = []
    for label, texts in by_source.items():
        numbered = "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(texts) if t)
        blocks.append(f"[{label}]\n{numbered}")

    return "Artículos del día:\n\n" + "\n\n".join(blocks)


# =============================================================================
# API call
# =============================================================================

def call_api(entries: list[tuple[str, str]], client: OpenAI) -> str | None:
    """
    Send one day's article entries to GPT and return the summary paragraph.
    Returns None if all retry attempts fail.
    """
    user_msg = build_user_message(entries)

    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_msg},
                ],
                temperature=0,
                max_tokens=300,
                timeout=30,
            )
            return resp.choices[0].message.content.strip()

        except Exception as e:
            wait = RETRY_DELAY * (2 ** attempt)
            print(f"  [error] attempt {attempt + 1}: {e}")
            time.sleep(wait)

    return None


# =============================================================================
# Checkpoint helpers
# =============================================================================

def load_checkpoint() -> tuple[list[dict], set[str]]:
    """Load previously processed days from the checkpoint file (if it exists)."""
    if CHECKPOINT_PATH.exists():
        df   = pd.read_parquet(CHECKPOINT_PATH)
        done = set(df["date"].astype(str).tolist())
        print(f"Checkpoint loaded: {len(done):,} dates already processed")
        return df.to_dict("records"), done
    print("No checkpoint found — starting fresh")
    return [], set()


def save_checkpoint(results: list[dict]) -> None:
    """Persist accumulated results to the checkpoint parquet file."""
    if results:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(results).to_parquet(CHECKPOINT_PATH, index=False)


# =============================================================================
# Main pipeline
# =============================================================================

def main(start_date: str, end_date: str) -> None:
    """Run the full daily summary pipeline for the given date range."""

    # --- OpenAI client ---
    import getpass
    api_key = getpass.getpass("Enter your OpenAI API key: ").strip()
    if not api_key:
        raise EnvironmentError("No API key provided.")
    client = OpenAI(api_key=api_key)

    # --- Load and group articles ---
    print(f"Loading articles: {start_date} → {end_date}")
    daily = build_daily_entries((start_date, end_date))

    # --- Checkpoint ---
    all_results, processed_dates = load_checkpoint()

    remaining = daily[~daily["date"].astype(str).isin(processed_dates)]
    print(f"\nTo process: {len(remaining):,} | Already done: {len(processed_dates):,}\n")

    # --- Main loop ---
    failed_dates: list[str] = []

    for i, row in enumerate(tqdm(remaining.itertuples(index=False), total=len(remaining),
                                  desc="Daily summaries")):
        summary = call_api(row.entries, client)

        if summary is None:
            failed_dates.append(str(row.date))
        else:
            all_results.append({
                "date":          row.date,
                "daily_summary": summary,
                "n_articles":    len(row.entries),
            })
            processed_dates.add(str(row.date))

        if (i + 1) % SAVE_INTERVAL == 0:
            save_checkpoint(all_results)
            tqdm.write(f"  Checkpoint saved: {i + 1} days done, {len(failed_dates)} failed")

    save_checkpoint(all_results)
    print(f"\nDone. {len(all_results):,} days processed | {len(failed_dates)} failures")

    # --- Final output ---
    if not all_results:
        print("No results to save.")
        return

    df = pd.DataFrame(all_results)
    df["date"]       = pd.to_datetime(df["date"])
    df["n_articles"] = df["n_articles"].astype(int)
    df = df.sort_values("date").reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(FINAL_OUTPUT, index=False)
    print(f"Saved → {FINAL_OUTPUT}  ({len(df):,} rows)")

    # --- Summary stats ---
    print("\n=== Summary ===")
    print(f"Date range:        {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"Avg articles/day:  {df['n_articles'].mean():.1f}")
    print(f"Min articles/day:  {df['n_articles'].min()}")
    print(f"Max articles/day:  {df['n_articles'].max()}")

    if failed_dates:
        pd.Series(failed_dates, name="failed_date").to_csv(FAILED_CSV, index=False)
        print(f"Failed dates ({len(failed_dates)}) → {FAILED_CSV}")


# =============================================================================
# CLI entry point
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate daily news summaries from La Jornada and 24 Horas articles."
    )
    parser.add_argument(
        "--start-date",
        default=DEFAULT_START_DATE,
        metavar="YYYY-MM-DD",
        help=f"Start date (inclusive). Default: {DEFAULT_START_DATE}",
    )
    parser.add_argument(
        "--end-date",
        default=DEFAULT_END_DATE,
        metavar="YYYY-MM-DD",
        help=f"End date (inclusive). Default: {DEFAULT_END_DATE}",
    )
    args = parser.parse_args()
    main(args.start_date, args.end_date)
