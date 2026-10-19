# Read-only audit of the external datasets. Writes only to the selected report dir.
# Run from repo root: Rscript scripts/audit_outlet_expansion.R [report-directory]
suppressPackageStartupMessages({library(dplyr); library(readxl); library(jsonlite); library(arrow)})
source("project_paths.R")
source("src/attendance_roles.R")
source("src/reviewed_outlet_linkage.R")
args <- commandArgs(trailingOnly = TRUE)
report_dir <- if (length(args)) args[1] else "output/outlet_review_20261016"
dir.create(report_dir, recursive = TRUE, showWarnings = FALSE)
manifest <- fromJSON("info_newspapers_gpt/outlet_expansion_20261016.json", simplifyVector = FALSE)
full_review <- fromJSON("info_newspapers_gpt/outlet_review_20261016/youtube_extraction_manifest.json", simplifyVector = FALSE)
metadata_file <- media_path("data","00-newspaper_data","newspaper_metadata.xlsx")
metadata <- read_excel(metadata_file)
for (entry in full_review$entries) {
  if (entry$name %in% vapply(manifest$entries, `[[`, character(1), "name")) next
  i <- match(entry$name, metadata$name.page)
  legal <- if(!is.na(i)) metadata$legal_name[i] else NA_character_
  entry$id <- normalize_reviewed_label(entry$linkage_id)
  entry$legal_entities <- if(!is.na(legal) && nzchar(legal)) list(list(
    name=legal,source=paste0(metadata_file,"#Hoja1!K",i+1L),
    relationship="legal name inherited from existing metadata; not independently reverified in this review",
    status="existing_metadata_unverified")) else list()
  manifest$entries[[length(manifest$entries)+1L]] <- entry
}
aliases <- read_outlet_aliases("info_newspapers_gpt/attendance_aliases_20261016.tsv")
attendance_file <- media_path("data", "02-conferences", "raw", "attendance", "merged", "attendance_merged_dedup.xlsx")
contracts_file <- media_path("data", "06-outcomes", "comsoc", "contracts_2012_2024_clean.parquet")
attendance <- read_excel(attendance_file)
attendance$eligible_role <- keep_attendance_role(attendance$cargo)
attendance$outlet_final <- NA_character_
attendance <- apply_reviewed_attendance_linkage(attendance, aliases)
labels <- attendance |>
  group_by(medios, cargo, eligible_role, outlet_final, outlet_linkage_status, outlet_linkage_reason) |>
  summarise(records = n(), first_date = min(as.Date(fecha), na.rm = TRUE),
            last_date = max(as.Date(fecha), na.rm = TRUE), .groups = "drop")
write.csv(filter(labels, outlet_linkage_status != "legacy_unreviewed"),
          file.path(report_dir, "attendance_review.csv"), row.names = FALSE, na = "")
contracts <- read_parquet(contracts_file) |>
  select(beneficiario, rfcb, bene_clean, bene_final, year.gasto)
key <- function(x) gsub("[^a-z0-9]", "", normalize_reviewed_label(x))
contracts$key <- key(contracts$beneficiario)
contracts$rfc_key <- toupper(gsub("[^A-Za-z0-9]", "", contracts$rfcb))
entities <- contracts |>
  group_by(beneficiario, rfcb, bene_clean, bene_final, key, rfc_key) |>
  summarise(dataset_rows = n(), first_year = if(all(is.na(year.gasto))) NA_real_ else min(year.gasto, na.rm = TRUE),
            last_year = if(all(is.na(year.gasto))) NA_real_ else max(year.gasto, na.rm = TRUE), .groups = "drop")
matches <- list(); summaries <- list()
for (entry in manifest$entries) {
  direct <- list();related <- list();results <- list()
  for (legal in entry$legal_entities) {
    k <- key(legal$name)
    approved_keys <- c(k, vapply(legal$dataset_name_aliases, key, character(1)))
    hit_name <- !is.na(entities$key) & entities$key %in% approved_keys
    hit_rfc <- rep(FALSE, nrow(entities))
    if (!is.null(legal$rfc)) {
      # Historical export includes a trailing 0 after many otherwise valid RFCs.
      # Retain the raw value and explicitly label this match method.
      hit_rfc <- entities$rfc_key %in% c(legal$rfc, paste0(legal$rfc, "0"))
    }
    # A misspelled beneficiary can also be identified by the verified RFC. Only
    # propagate to EXACT spellings observed with that RFC, never similar names.
    known_keys <- unique(entities$key[hit_name | hit_rfc])
    hit <- entities$key %in% known_keys
    selected <- entities[hit, ]
    if (nrow(selected)) {
      selected$outlet_id <- entry$id;selected$outlet_name <- entry$name
      selected$verified_legal_name <- legal$name;selected$source_url <- legal$source
      selected$relationship <- legal$relationship
      selected$match_method <- ifelse(selected$key == k, "exact_normalized_legal_name",
        ifelse(selected$key %in% approved_keys, "reviewed_legal_name_alias",
        ifelse(selected$rfc_key %in% legal$rfc, "exact_verified_rfc",
          ifelse(selected$rfc_key %in% paste0(legal$rfc, "0"), "verified_rfc_with_export_suffix",
                 "exact_beneficiary_spelling_observed_with_verified_rfc"))))
      selected$link_status <- if (!is.null(legal$status) && legal$status == "related_entity")
        "related_entity_match" else if (!is.null(legal$status) && legal$status == "partial")
        "partial_legal_name_match_review" else if (!is.null(legal$status) && legal$status == "existing_metadata_unverified")
        "existing_metadata_match_review" else "confirmed_entity_match"
      results[[length(results) + 1L]] <- selected
    }
  }
  result <- bind_rows(results)
  confirmed <- if (nrow(result)) filter(result, link_status == "confirmed_entity_match") else result
  if (nrow(result)) matches[[length(matches) + 1L]] <- result
  a <- filter(attendance, outlet_final == entry$id, eligible_role)
  summaries[[length(summaries) + 1L]] <- data.frame(
    outlet_name = entry$name, outlet_id = entry$id,
    reviewed_attendance_records = nrow(a), reviewed_attendance_days = n_distinct(a$fecha),
    reviewed_records_pass_n_gt_4 = nrow(a) > 4,
    comsoc_status = if(nrow(confirmed)) "confirmed_entity_match" else if(nrow(result))
      "related_or_partial_identity_review" else if(length(entry$legal_entities))
      "no_exact_match_in_2012_2024_file" else "legal_identity_unresolved",
    comsoc_bene_final = if(nrow(confirmed)) paste(sort(unique(confirmed$bene_final)), collapse = " | ") else "",
    comsoc_rows = if(nrow(confirmed)) sum(distinct(confirmed, beneficiario, rfcb, bene_final, .keep_all=TRUE)$dataset_rows) else NA_integer_,
    stringsAsFactors = FALSE)
}
matches <- bind_rows(matches)
write.csv(matches, file.path(report_dir, "comsoc_matches.csv"), row.names = FALSE, na = "")
summary <- bind_rows(summaries)
write.csv(summary, file.path(report_dir, "outlet_summary.csv"), row.names = FALSE, na = "")
write_json(list(attendance_file=attendance_file,attendance_rows=nrow(attendance),
                contracts_file=contracts_file,contracts_rows=nrow(contracts),
                contract_years=sort(unique(contracts$year.gasto)),
                generated_at=format(Sys.time(),tz="UTC",usetz=TRUE),
                note="Attendance counts cover only labels in the reviewed alias table, not all legacy matches. Counts are dataset records, not people or unique contracts; no exact match is not proof of no government advertising."),
           file.path(report_dir,"audit_inputs.json"),pretty=TRUE,auto_unbox=TRUE)
print(count(summary,comsoc_status))
