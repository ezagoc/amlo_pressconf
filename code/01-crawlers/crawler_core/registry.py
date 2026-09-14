"""Build and audit the Mexican newspaper crawler source registry."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import numpy as np
import pandas as pd


PERIODICOS_SHEET = "Periodicos"
ESTADOS_SHEET = "Estados"

RAW_COLUMN_RENAMES = {
    "bene_final": "owner_group",
    "name.comsoc": "comsoc_name",
    "source. Name": "source_name_raw",
    "sa.de.cv": "company_suffix_flag",
    "name.page": "source_name",
    "names.transcripts": "transcripts_name",
    "names.conference": "conference_name",
    "twitter.handle": "twitter_handle",
    "youtube.channel": "youtube_channel",
    "CVE_ENT": "cve_ent",
    "scrapped": "scraped_flag",
    "year_founded": "founded_year",
    "name.page2": "source_name_alt",
    "name.comsoc2": "comsoc_name_alt",
    "not.newspaper": "not_newspaper_flag",
    "antibot.java": "antibot_java_flag",
    "last.date.scrapped": "last_date_scraped",
    "ideology.subjective": "ideology_subjective",
    "ideology.source": "ideology_source",
    "type.media": "media_type",
    "journalist.ma\u00f1anera": "journalist_mananera",
    "Unnamed: 27": "unnamed_27",
}

OUTPUT_COLUMNS = [
    "source_id",
    "row_id",
    "source_name",
    "canonical_url",
    "domain",
    "url_path",
    "state",
    "municipality",
    "cve_ent",
    "media_type",
    "owner_group",
    "comsoc_name",
    "conference_name",
    "transcripts_name",
    "twitter_handle",
    "youtube_channel",
    "subscription_flag",
    "antibot_java_flag",
    "not_newspaper_flag",
    "scraped_flag",
    "crawl_candidate",
    "candidate_reason",
    "folder_name",
    "file_name",
    "platform_cluster",
    "crawl_strategy_hint",
    "founded_year",
    "last_date_scraped",
    "ideology_subjective",
    "ideology_source",
    "journalist_mananera",
]


@dataclass(frozen=True)
class RegistryOutputs:
    """Paths written by the registry builder."""

    sources_csv: Path
    sources_parquet: Path | None
    audit_report: Path
    parquet_error: str | None = None


def read_workbook(workbook_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the workbook sheets needed for registry construction."""
    periodicos = pd.read_excel(workbook_path, sheet_name=PERIODICOS_SHEET)
    estados = pd.read_excel(workbook_path, sheet_name=ESTADOS_SHEET)
    return periodicos, estados


def build_registry(periodicos: pd.DataFrame, estados: pd.DataFrame) -> pd.DataFrame:
    """Return a normalized, machine-readable source registry."""
    df = periodicos.copy()
    df.insert(0, "row_id", np.arange(1, len(df) + 1))
    df = df.rename(columns=RAW_COLUMN_RENAMES)

    _ensure_expected_columns(df)
    _strip_string_columns(df)

    df["canonical_url"] = df["url"].map(normalize_url)
    parsed = df["canonical_url"].map(parse_url_parts)
    df["domain"] = parsed.map(lambda item: item[0])
    df["url_path"] = parsed.map(lambda item: item[1])

    for column in [
        "scraped_flag",
        "subscription",
        "antibot_java_flag",
        "not_newspaper_flag",
        "cve_ent",
        "founded_year",
    ]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["subscription_flag"] = df.pop("subscription")
    df["platform_cluster"] = df.apply(infer_platform_cluster, axis=1)
    df["crawl_strategy_hint"] = df.apply(infer_strategy_hint, axis=1)
    df["folder_name"] = assign_folder_names(df)
    df["file_name"] = df["file_name"].fillna("articles.parquet")
    df["source_id"] = assign_source_ids(df)

    candidate = df.apply(candidate_status, axis=1, result_type="expand")
    df["crawl_candidate"] = candidate[0]
    df["candidate_reason"] = candidate[1]

    for column in OUTPUT_COLUMNS:
        if column not in df.columns:
            df[column] = np.nan

    return df[OUTPUT_COLUMNS].copy()


def write_registry_outputs(
    registry: pd.DataFrame,
    audit_report: str,
    registry_dir: Path,
    reports_dir: Path,
) -> RegistryOutputs:
    """Write registry parquet/csv and audit markdown files."""
    registry_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    sources_csv = registry_dir / "sources.csv"
    sources_parquet = registry_dir / "sources.parquet"
    report_path = reports_dir / "metadata_audit.md"

    registry.to_csv(sources_csv, index=False, encoding="utf-8")
    parquet_error = None
    try:
        registry.to_parquet(sources_parquet, index=False)
    except ImportError as exc:
        sources_parquet = None
        parquet_error = str(exc).splitlines()[0]
    report_path.write_text(audit_report, encoding="utf-8")

    return RegistryOutputs(
        sources_csv=sources_csv,
        sources_parquet=sources_parquet,
        audit_report=report_path,
        parquet_error=parquet_error,
    )


def build_audit_report(
    registry: pd.DataFrame,
    raw_periodicos: pd.DataFrame,
    estados: pd.DataFrame,
    workbook_path: Path,
) -> str:
    """Create a markdown audit report for human review."""
    state_issues = state_cve_issues(raw_periodicos, estados)
    duplicate_urls = registry[
        registry["canonical_url"].notna()
        & registry.duplicated("canonical_url", keep=False)
    ].sort_values(["canonical_url", "source_name"])
    duplicate_domains = registry["domain"].value_counts(dropna=True)
    duplicate_domains = duplicate_domains[duplicate_domains > 1]
    candidates = registry[registry["crawl_candidate"]]

    lines = [
        "# Mexican Newspaper Registry Audit",
        "",
        f"Generated from: `{workbook_path}`",
        "",
        "## Summary",
        "",
        f"- Workbook rows: {len(raw_periodicos):,}",
        f"- Registry rows: {len(registry):,}",
        f"- Rows with URL: {registry['canonical_url'].notna().sum():,}",
        f"- Unique non-missing URLs: {registry['canonical_url'].dropna().nunique():,}",
        f"- Newspaper rows: {(registry['media_type'] == 'periodico').sum():,}",
        f"- Crawl candidates: {len(candidates):,}",
        f"- Already marked scraped: {registry['scraped_flag'].eq(1).sum():,}",
        f"- Subscription flagged: {registry['subscription_flag'].eq(1).sum():,}",
        f"- Antibot/JavaScript flagged: {registry['antibot_java_flag'].eq(1).sum():,}",
        f"- Missing state: {registry['state'].isna().sum():,}",
        f"- Missing CVE_ENT: {registry['cve_ent'].isna().sum():,}",
        "",
        "## Candidate Reasons",
        "",
        markdown_table(
            registry["candidate_reason"]
            .fillna("<missing>")
            .value_counts()
            .rename_axis("reason")
            .reset_index(name="rows")
        ),
        "",
        "## Platform Clusters",
        "",
        markdown_table(
            registry["platform_cluster"]
            .fillna("<missing>")
            .value_counts()
            .rename_axis("platform_cluster")
            .reset_index(name="rows")
            .head(30)
        ),
        "",
        "## Multi-Row Domains",
        "",
        markdown_table(duplicate_domains.head(30).rename_axis("domain").reset_index(name="rows")),
        "",
        "## Duplicate URLs",
        "",
    ]

    if duplicate_urls.empty:
        lines.append("No duplicate canonical URLs found.")
    else:
        lines.append(
            markdown_table(
                duplicate_urls[
                    [
                        "source_name",
                        "canonical_url",
                        "state",
                        "scraped_flag",
                        "folder_name",
                        "source_id",
                    ]
                ].head(80)
            )
        )

    lines.extend(["", "## State/CVE Issues", ""])
    if state_issues.empty:
        lines.append("No state/CVE mismatches found where both values are populated.")
    else:
        lines.append(markdown_table(state_issues))

    lines.extend(
        [
            "",
            "## First 50 Crawl Candidates",
            "",
            markdown_table(
                candidates[
                    [
                        "source_id",
                        "source_name",
                        "canonical_url",
                        "state",
                        "platform_cluster",
                        "crawl_strategy_hint",
                    ]
                ].head(50)
            ),
            "",
            "## Next Step",
            "",
            "Run a capability probe against rows where `crawl_candidate == True`, "
            "then prioritize shared platform adapters before one-off crawlers.",
            "",
        ]
    )
    return "\n".join(lines)


def normalize_url(value: object) -> str | float:
    """Normalize a workbook URL without changing its destination semantics."""
    if pd.isna(value):
        return np.nan
    url = str(value).strip()
    if not url:
        return np.nan
    if "://" not in url:
        url = "https://" + url

    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") + "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def markdown_table(df: pd.DataFrame) -> str:
    """Render a small DataFrame as a GitHub-compatible Markdown table."""
    if df.empty:
        return "_No rows._"

    formatted = df.fillna("").astype(str)
    headers = list(formatted.columns)
    rows = formatted.values.tolist()

    def clean(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")

    output = [
        "| " + " | ".join(clean(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(clean(value) for value in row) + " |")
    return "\n".join(output)


def parse_url_parts(value: object) -> tuple[str | float, str | float]:
    """Return normalized domain and path for a URL value."""
    if pd.isna(value):
        return np.nan, np.nan
    parsed = urlparse(str(value))
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or np.nan, parsed.path or "/"


def slugify(value: object, fallback: str = "source") -> str:
    """Return a stable ASCII slug for identifiers and folders."""
    if pd.isna(value):
        return fallback
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    text = re.sub(r"_+", "_", text)
    return text or fallback


def assign_folder_names(df: pd.DataFrame) -> pd.Series:
    """Use existing folder names, filling gaps with deterministic slugs."""
    existing = df["folder_name"].copy()
    generated = []
    for _, row in df.iterrows():
        if pd.notna(row.get("folder_name")) and str(row["folder_name"]).strip():
            generated.append(slugify(row["folder_name"]))
            continue

        domain = row.get("domain")
        source_name = row.get("source_name")
        if pd.notna(domain):
            parts = str(domain).split(".")
            base = parts[0] if parts else str(domain)
            if base in {"com", "org", "net"} and len(parts) > 1:
                base = parts[1]
        else:
            base = source_name

        folder = slugify(base)
        generated.append(folder)

    result = pd.Series(generated, index=df.index)
    duplicate_mask = result.duplicated(keep=False)
    for idx in result[duplicate_mask].index:
        state = slugify(df.at[idx, "state"], fallback="")
        path_slug = slugify(df.at[idx, "url_path"], fallback="")
        suffix_parts = [part for part in [state, path_slug] if part]
        if suffix_parts:
            result.at[idx] = "_".join([result.at[idx], *suffix_parts])
    return result


def assign_source_ids(df: pd.DataFrame) -> pd.Series:
    """Create stable unique source IDs from folder/source/state metadata."""
    ids = []
    seen: dict[str, int] = {}
    for _, row in df.iterrows():
        base = slugify(row.get("folder_name"), fallback="source")
        state = slugify(row.get("state"), fallback="")
        name = slugify(row.get("source_name"), fallback="")
        source_id = base
        if source_id in seen and state:
            source_id = f"{base}_{state}"
        if source_id in seen and name:
            source_id = f"{base}_{name}"
        seen[source_id] = seen.get(source_id, 0) + 1
        if seen[source_id] > 1:
            source_id = f"{source_id}_{seen[source_id]}"
            seen[source_id] = 1
        ids.append(source_id)
    return pd.Series(ids, index=df.index)


def infer_platform_cluster(row: pd.Series) -> str:
    """Infer shared site/platform groups for adapter prioritization."""
    domain = str(row.get("domain") or "")
    owner = str(row.get("owner_group") or "").lower()
    name = str(row.get("source_name") or "").lower()

    if domain == "oem.com.mx":
        return "oem"
    if domain == "elimparcial.com":
        return "grupo_healy_elimparcial"
    if "24horas" in domain or "24 horas" in name:
        return "horas24"
    if "lajornada" in domain or "jornada" in name:
        return "jornada_family"
    if domain in {
        "diariobasta.com",
        "tabascohoy.com",
        "quintanaroohoy.com",
        "campechehoy.mx",
    } or "grupo canton" in owner:
        return "grupo_canton"
    if domain in {"yucatan.com.mx", "sipse.com"}:
        return "epme_sipse_yucatan"
    if pd.notna(row.get("domain")):
        return domain
    return "missing_url"


def infer_strategy_hint(row: pd.Series) -> str:
    """Return the first strategy worth trying before live capability probing."""
    domain = str(row.get("domain") or "")
    path = str(row.get("url_path") or "")
    cluster = str(row.get("platform_cluster") or "")

    if cluster in {"oem", "horas24", "jornada_family", "grupo_canton", "grupo_healy_elimparcial"}:
        return f"platform_adapter:{cluster}"
    if "wordpress" in domain:
        return "wordpress_probe"
    if path and path != "/":
        return "section_or_subsite_probe"
    if pd.notna(row.get("canonical_url")):
        return "capability_probe"
    return "no_url"


def candidate_status(row: pd.Series) -> tuple[bool, str]:
    """Decide whether a source is ready for first-wave capability probing."""
    if pd.isna(row.get("canonical_url")):
        return False, "missing_url"
    if row.get("not_newspaper_flag") == 1:
        return False, "not_newspaper"
    if row.get("media_type") != "periodico":
        return False, "not_periodico"
    if row.get("scraped_flag") == 1:
        return False, "already_scraped"
    if row.get("subscription_flag") == 1:
        return False, "subscription_flagged"
    if row.get("antibot_java_flag") == 1:
        return False, "antibot_flagged"
    return True, "first_wave_candidate"


def state_cve_issues(periodicos: pd.DataFrame, estados: pd.DataFrame) -> pd.DataFrame:
    """Return rows where workbook state and CVE_ENT disagree."""
    state_lookup = dict(zip(estados["state"], estados["CVE_ENT"]))
    rows = []
    for idx, row in periodicos.iterrows():
        state = row.get("state")
        cve = row.get("CVE_ENT")
        if pd.isna(state) or pd.isna(cve) or state not in state_lookup:
            continue
        expected = state_lookup[state]
        if int(cve) != int(expected):
            rows.append(
                {
                    "row_id": idx + 1,
                    "source_name": row.get("name.page"),
                    "state": state,
                    "cve_ent": cve,
                    "expected_cve_ent": expected,
                }
            )
    return pd.DataFrame(rows)


def _strip_string_columns(df: pd.DataFrame) -> None:
    for column in df.columns:
        if pd.api.types.is_object_dtype(df[column]):
            df[column] = df[column].map(
                lambda value: value.strip() if isinstance(value, str) else value
            )
            df[column] = df[column].replace("", np.nan)


def _ensure_expected_columns(df: pd.DataFrame) -> None:
    required = set(RAW_COLUMN_RENAMES.values()) | {
        "row_id",
        "url",
        "state",
        "municipality",
        "subscription",
        "folder_name",
        "file_name",
    }
    missing = sorted(column for column in required if column not in df.columns)
    if missing:
        raise ValueError("Missing expected workbook columns: " + ", ".join(missing))
