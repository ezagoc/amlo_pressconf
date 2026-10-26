# Full-source descriptive statistics, not restricted to metadata/YouTube matches.
# No source files, panels, regression estimates, or existing figures are modified.
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1]]) else
  file.path(getwd(), "code/07-final_panel/25-full-period-conference-descriptives.R")
root <- normalizePath(file.path(dirname(script_path), "../.."), mustWork = TRUE)
source(file.path(root, "project_paths.R"))
source(file.path(root, "src/final_panel_helpers.R"))
suppressPackageStartupMessages({
  library(arrow); library(dplyr); library(tidyr); library(readr)
  library(stringr); library(lubridate); library(ggplot2); library(patchwork)
})
out_dir <- media_path("results", "descriptives", "full_period_press_conferences")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
pdf_dir <- file.path(root, "output", "desc_stats")
dir.create(pdf_dir, recursive = TRUE, showWarnings = FALSE)
lottery <- as.Date("2022-04-18")
claudia <- as.Date("2024-10-01")
source_paths <- c(
  attendance = media_path("data/02-conferences/raw/attendance/merged/attendance_clean.parquet"),
  attendance_panel = media_path("data/02-conferences/raw/attendance/panel_attendance.parquet.gzip"),
  questions_all = media_path("data/02-conferences/auxiliar/questions_dataset.parquet"),
  questions_named = media_path("data/02-conferences/auxiliar/questions_dataset_dedup.parquet"),
  metadata = media_path("data/00-newspaper_data/processed/newspaper_metadata_geocoded.parquet")
)
source_hashes <- tools::md5sum(source_paths)
a <- read_parquet(source_paths[["attendance"]]) |>
  mutate(date = as.Date(fecha), attendance_id = normalize_panel_key(outlet_final))
# This descriptive series measures recorded people/outlets, not co-affiliation
# assignments. Keep its physical attendance totals comparable over time.
if ("attendance_assumed" %in% names(a)) a <- filter(a, !attendance_assumed)
ap <- read_parquet(source_paths[["attendance_panel"]]) |>
  mutate(date = as.Date(fecha), attendance_id = normalize_panel_key(outlet_final))
q_source <- read_parquet(source_paths[["questions_all"]]) |> mutate(date = as.Date(date))
q_named <- read_parquet(source_paths[["questions_named"]]) |> mutate(date = as.Date(date))
metadata <- read_parquet(source_paths[["metadata"]])
stopifnot(!anyNA(a$date), !anyNA(q_source$date), !anyNA(q_named$date))

# Deduplicate only exactly repeated question-item records. Do NOT deduplicate
# attendance rows: they have no person IDs, so identical rows may be different
# journalists from the same outlet. Keep the upstream attendance count definition.
q_unique <- distinct(q_source)
key <- c("date", "reporter", "outlet", "turn_index", "item_index", "item_type", "text")
q_map <- q_named |>
  select(all_of(key), clean_outlet = outlet_aux, clean_reporter = reporter_aux) |> distinct()
stopifnot(!anyDuplicated(q_map[key]), !anyDuplicated(q_unique[key]))
q <- q_unique |> left_join(q_map, by = key, relationship = "one-to-one") |>
  mutate(question_id = normalize_panel_key(clean_outlet),
    reporter_id = normalize_panel_key(coalesce(clean_reporter, reporter_aux)),
    is_question = item_type %in% c("pregunta", "question"))
questions <- filter(q, is_question)
stopifnot(nrow(q) == nrow(q_unique), all(q_named$date %in% q$date))

# Count conference dates independently of successful question extraction.
transcript_files <- unlist(lapply(2018:2024, function(y) list.files(
  media_path("data/02-conferences/raw", as.character(y)),
  pattern = "^mananera_[0-9]+_[0-9]+_[0-9]+[.]csv$", full.names = TRUE, recursive = TRUE)))
transcript_inventory <- tibble(path = transcript_files,
  date = as.Date(str_extract(basename(transcript_files), "[0-9]+_[0-9]+_[0-9]+"), "%d_%m_%Y"))
stopifnot(nrow(transcript_inventory) > 0, !anyNA(transcript_inventory$date))
conference_dates <- tibble(date = sort(unique(c(a$date, transcript_inventory$date, q$date)))) |>
  mutate(attendance_observed = date %in% a$date,
    transcript_available = date %in% transcript_inventory$date,
    extraction_observed = date %in% q$date,
    question_observed = date %in% questions$date,
    era = case_when(date < lottery ~ "Pre-lottery", date < claudia ~ "Post-lottery: AMLO",
                    TRUE ~ "Claudia"))
daily_attendance <- a |> group_by(date) |> summarise(
  journalist_records = n(), attending_outlets = n_distinct(attendance_id, na.rm = TRUE),
  unknown_outlet_records = sum(is.na(attendance_id)), .groups = "drop")

summary_row <- function(metric, value, dates, definition) tibble(
  metric, value = as.numeric(value), start = min(dates), end = max(dates), definition)
summary <- bind_rows(
  summary_row("Recorded question items", nrow(questions), questions$date,
    "Unique extracted items labeled pregunta or question; includes unknown-outlet items; not a census of all questions."),
  summary_row("Question items with a standardized outlet", sum(!is.na(questions$question_id)), questions$date,
    "Uses the existing curated outlet-name mapping without restricting to metadata."),
  summary_row("Question items without a standardized outlet", sum(is.na(questions$question_id)), questions$date,
    "Included in the total, excluded from distinct outlet counts."),
  summary_row("Outlets asking at least one question", n_distinct(questions$question_id, na.rm = TRUE), questions$date,
    "Distinct nonmissing normalized curated transcript outlet IDs."),
  summary_row("Question-asking outlets matched to metadata", n_distinct(questions$question_id[
    questions$question_id %in% normalize_panel_key(metadata$names.transcripts)], na.rm = TRUE), questions$date,
    "Distinct source IDs, not duplicated metadata rows."),
  summary_row("Journalist attendance records", nrow(a), a$date,
    "Repeated visits count separately; upstream excludes listed technical roles and government entities; not unique people."),
  summary_row("Attendance outlet labels with at least one visit", n_distinct(a$attendance_id, na.rm = TRUE), a$date,
    "All normalized source labels; rare labels may still contain aliases or misspellings, so not verified distinct organizations."),
  summary_row("Attendance outlets in existing restricted panel", n_distinct(ap$attendance_id[ap$n_journalists > 0], na.rm = TRUE), a$date,
    "Original panel keeps outlet labels with more than four attendance records; excludes rare outlets by construction."),
  summary_row("Attending outlets matched to metadata", n_distinct(a$attendance_id[
    a$attendance_id %in% normalize_panel_key(metadata$names.conference)], na.rm = TRUE), a$date,
    "Distinct source IDs matched to metadata, counted once."),
  summary_row("Conference dates with attendance records", n_distinct(a$date), a$date,
    "One conference date per calendar day; venue spelling differences do not create extra conferences."),
  summary_row("Conference dates with archived transcripts", n_distinct(transcript_inventory$date), transcript_inventory$date,
    "Distinct dates parsed from archived mananera_DD_MM_YYYY.csv filenames."),
  summary_row("Conference dates represented in any source", nrow(conference_dates), conference_dates$date,
    "Union of attendance, transcript inventory, and extraction dates; observed-date count, not a verified complete historical census."),
  summary_row("Dates with classified question/opinion items", n_distinct(q$date), q$date,
    "Extraction coverage including unknown outlets and opinion-only dates."),
  summary_row("Dates with at least one recorded question", n_distinct(questions$date), questions$date,
    "Question extraction coverage, not total press conferences."),
  summary_row("Mean journalist records per observed conference date", mean(daily_attendance$journalist_records), a$date,
    "Denominator is dates with a source attendance list, not all calendar days."),
  summary_row("Mean outlet labels per observed conference date", mean(daily_attendance$attending_outlets), a$date,
    "Distinct standardized nonmissing labels within date, averaged across observed lists.")
)

period_summary <- function(dates, period_label) {
  aa <- filter(a, date %in% dates); qq <- filter(questions, date %in% dates)
  cc <- filter(conference_dates, date %in% dates)
  ad <- filter(daily_attendance, date %in% dates)
  tibble(period = period_label, start = min(dates), end = max(dates),
    question_items = if (any(cc$extraction_observed)) nrow(qq) else NA_integer_,
    question_outlets = if (any(cc$extraction_observed)) n_distinct(qq$question_id, na.rm = TRUE) else NA_integer_,
    extraction_dates = sum(cc$extraction_observed), transcript_dates = sum(cc$transcript_available),
    attendance_records = if (nrow(aa)) nrow(aa) else NA_integer_,
    attendance_outlet_labels = if (nrow(aa)) n_distinct(aa$attendance_id, na.rm = TRUE) else NA_integer_,
    attendance_dates = nrow(ad), observed_conference_dates = nrow(cc),
    mean_attendance_per_observed_date = if (nrow(ad)) mean(ad$journalist_records) else NA_real_)
}
annual <- bind_rows(lapply(sort(unique(year(conference_dates$date))), function(y)
  period_summary(conference_dates$date[year(conference_dates$date) == y], as.character(y))))
eras <- bind_rows(lapply(c("Pre-lottery", "Post-lottery: AMLO", "Claudia"), function(x)
  period_summary(conference_dates$date[conference_dates$era == x], x)))
# Use all extraction dates, including opinion-only dates with zero recorded
# questions. Dates without extraction records are unavailable, never zero.
daily_questions <- q |> group_by(date) |> summarise(
  question_items = sum(is_question),
  asking_outlets = n_distinct(question_id[is_question], na.rm = TRUE), .groups = "drop")
monthly <- tibble(month = seq(floor_date(min(c(a$date, q$date)), "month"),
                             floor_date(max(c(a$date, q$date)), "month"), by = "month")) |>
  left_join(daily_attendance |> mutate(month = floor_date(date, "month")) |> group_by(month) |>
    summarise(attendance_records = sum(journalist_records),
      outlet_attendance_days = sum(attending_outlets), attendance_dates = n(),
      mean_journalists = mean(journalist_records), mean_outlets = mean(attending_outlets), .groups = "drop"), by = "month") |>
  left_join(daily_questions |> mutate(month = floor_date(date, "month")) |> group_by(month) |>
    summarise(mean_questions = mean(question_items), mean_asking_outlets = mean(asking_outlets),
      question_items = sum(question_items), extraction_dates = n(),
      .groups = "drop"), by = "month") |>
  left_join(conference_dates |> mutate(month = floor_date(date, "month")) |> group_by(month) |>
    summarise(known_conference_dates = n(), transcript_dates = sum(transcript_available), .groups = "drop"), by = "month") |>
  mutate(attendance_dates = coalesce(attendance_dates, 0L),
    coverage_fraction = attendance_dates / known_conference_dates,
    sparse_coverage = attendance_dates < 5L,
    mean_journalists_plot = if_else(sparse_coverage, NA_real_, mean_journalists),
    mean_outlets_plot = if_else(sparse_coverage, NA_real_, mean_outlets))

events <- tibble::tribble(
  ~date, ~label, ~label_y, ~source,
  "2020-03-23", "COVID restrictions", 1.06, "https://www.imss.gob.mx/prensa/archivo/202003/142",
  "2020-06-01", "Phased reopening", 1.20, "https://www.gob.mx/se/prensa/la-secretaria-de-economia-graciela-marquez-presenta-el-plan-de-reapertura-de-las-actividades-sociales-educativas-y-economicas-242435",
  "2021-06-06", "2021 midterms", 1.06, "https://www.ine.mx/voto-y-elecciones/elecciones-2021/",
  "2022-04-18", "Lottery", 1.06, "https://www.elfinanciero.com.mx/nacional/2022/04/11/la-mananera-es-una-tom-tom-tombola-asi-sera-el-sorteo-para-acomodar-a-reporteros-en-la-conferencia/",
  "2024-06-02", "2024 election", 1.06, "https://portal.ine.mx/voto-y-elecciones/elecciones-2024/eleccion-federal-2024/",
  "2024-10-01", "Claudia takes office", 1.20, "https://www.gob.mx/presidencia/prensa/hoy-llegamos-las-mujeres-a-conducir-los-destinos-de-nuestra-hermosa-nacion-presidenta-claudia-sheinbaum?idiom=es-MX"
) |> mutate(date = as.Date(date))
quality <- tibble::tribble(
  ~check, ~value,
  "Original full question/opinion rows", nrow(q_source),
  "Exactly duplicated full question/opinion rows removed", nrow(q_source) - nrow(q_unique),
  "Original pregunta rows (full source)", sum(q_source$item_type == "pregunta"),
  "Original English question rows (full source)", sum(q_source$item_type == "question"),
  "Full-source question rows removed as exact duplicates", sum(q_source$item_type %in% c("pregunta", "question")) - nrow(questions),
  "Original pregunta rows in named-only dataset (legacy definition)", sum(q_named$item_type == "pregunta"),
  "Attendance records with blank outlet IDs", sum(is.na(a$attendance_id)),
  "Attendance labels appearing only once", sum((a |> filter(!is.na(attendance_id)) |> count(attendance_id))$n == 1),
  "Archived transcript files", nrow(transcript_inventory),
  "Archived transcript dates", n_distinct(transcript_inventory$date),
  "November 2021 attendance dates", sum(daily_attendance$date >= as.Date("2021-11-01") & daily_attendance$date <= as.Date("2021-11-30"))
)
for (nm in c("summary", "annual", "eras", "monthly", "events", "quality", "conference_dates", "transcript_inventory"))
  write_csv(get(nm), file.path(out_dir, paste0(nm, ".csv")))
write_csv(a |> filter(!is.na(attendance_id)) |> count(attendance_id, sort = TRUE, name = "attendance_records"),
  file.path(out_dir, "attendance_outlet_counts.csv"))
write_csv(questions |> filter(!is.na(question_id)) |> count(question_id, sort = TRUE, name = "question_items"),
  file.path(out_dir, "question_outlet_counts.csv"))

# Attendance averages and total monthly question items. Missing question
# extraction remains unavailable, not zero. Coverage stays in the CSV.
blue <- "#315B77"; green <- "#648276"
date_limits <- c(min(monthly$month) - 16, max(monthly$month) + 25)
base_theme <- theme_minimal(base_size = 13) + theme(
  panel.grid.minor = element_blank(), panel.grid.major.x = element_blank(),
  panel.grid.major.y = element_line(color = "#E7EAED", linewidth = .3),
  axis.text = element_text(color = "#42484E"), axis.title = element_text(size = 12),
  plot.title = element_text(size = 14, face = "bold", margin = margin(b = 8)),
  legend.position = "bottom", legend.title = element_blank(),
  plot.margin = margin(8, 14, 5, 8))
time_scale <- function() scale_x_date(limits = date_limits, date_breaks = "1 year", date_labels = "%Y", expand = expansion(mult = 0))
verticals <- function() geom_vline(data = events, aes(xintercept = date), inherit.aes = FALSE,
  linetype = "dashed", color = "#858B90", linewidth = .4)
means <- monthly |> select(month, mean_journalists_plot, mean_outlets_plot) |>
  pivot_longer(-month, names_to = "series", values_to = "value") |>
  mutate(series = recode(series, mean_journalists_plot = "Journalist records", mean_outlets_plot = "Outlet labels"))
max_mean <- max(means$value, na.rm = TRUE)
p_mean <- ggplot(means, aes(month, value, color = series)) + verticals() +
  geom_line(linewidth = .85, na.rm = TRUE) + geom_point(size = 1.25, na.rm = TRUE) +
  geom_text(data = events, aes(x = date, y = label_y * max_mean, label = label),
    inherit.aes = FALSE, size = 3.5, color = "#454B50") +
  scale_color_manual(values = c("Journalist records" = blue, "Outlet labels" = green)) +
  scale_y_continuous(limits = c(0, max_mean * 1.3), expand = expansion(mult = 0)) +
  time_scale() + labs(title = "A   Mean attendance per observed conference", x = NULL, y = "Attendees / outlets") + base_theme +
  theme(axis.text.x = element_blank(), legend.position = "top",
        legend.direction = "horizontal", legend.justification = "left")
max_questions <- max(monthly$question_items, na.rm = TRUE)
question_end <- ceiling_date(max(q$date), "month")
p_questions <- ggplot(monthly, aes(month, question_items)) +
  annotate("rect", xmin = question_end, xmax = date_limits[2], ymin = -Inf, ymax = Inf,
    fill = "#EEF0F2", alpha = .8) + verticals() +
  geom_line(color = blue, linewidth = .85, na.rm = TRUE) +
  geom_point(color = blue, size = 1.25, na.rm = TRUE) +
  annotate("text", x = question_end + as.numeric(date_limits[2] - question_end) / 2,
    y = max_questions * .55, label = "No classified\nquestion data", color = "#727B82", size = 4) +
  scale_y_continuous(limits = c(0, max_questions * 1.15),
    labels = scales::label_comma(), expand = expansion(mult = 0)) +
  time_scale() + labs(title = "B   Total questions asked per month",
    x = NULL, y = "Recorded question items") + base_theme
p <- (p_mean / p_questions) + plot_layout(heights = c(1, 1)) +
  plot_annotation(theme = theme(plot.margin = margin(12, 18, 10, 12)))
pdf_path <- file.path(pdf_dir, "attendance_full_period_monthly.pdf")
ggsave(pdf_path, p, width = 13, height = 10, units = "in", device = "pdf", bg = "white")
writeLines(c(
  "Full-period descriptive statistics. Created from source records, not expanded metadata panels.",
  "Question totals use questions_dataset.parquet so unidentified outlets are retained; canonical names are joined from questions_dataset_dedup.parquet.",
  "Exact duplicate question rows are removed; English question and Spanish pregunta labels both count. Opinion items do not count as questions.",
  "An extracted question item can contain several interrogative sentences; this is the pipeline's item unit, not a count of question marks.",
  "Extraction covers only part of the transcript archive. Missing extraction dates and post-September-2024 questions are unavailable, not zero.",
  "Attendance totals count the upstream filtered records and include outlets dropped by the panel's >4-record threshold.",
  "No person identifier is present in attendance_clean.parquet, so unique journalists and possible same-person duplicate records cannot be established.",
  "All normalized nonblank outlet labels count, but residual name variants mean the all-label total is not a verified count of distinct organizations.",
  "Matched-metadata counts and the original restricted-panel count are supplied separately; no company/outlet multiplication occurs.",
  "Asking a question implies attendance, but this figure intentionally measures recorded attendance lists rather than mixing in inferred minimum counts.",
  "Conference counts are distinct dates in each observed source; the union is not a claim of a complete historical census. Multiple venues/filename duplicates on a date count once.",
  "Attendance begins in March 2019, so the July 2018 election is outside the plotted range.",
  "The lottery marker uses April 18, 2022, consistent with the current analysis and contemporaneous reporting; older attendance code used April 12.",
  "COVID restrictions marker: March 23, 2020, start of the Jornada Nacional de Sana Distancia. This is not the later March 30 mandatory suspension of nonessential activities.",
  "Phased reopening marker: June 1, 2020, start of the national risk-based Nueva Normalidad phase; not an unrestricted reopening or a verified change in press-conference admission rules.",
  "The figure has no overall title, subtitle, or bottom notes; panel labels, axes, legend, and unavailable-data marking remain. Methodological notes are preserved here.",
  "The 2025 totals are through September only; 2019 attendance starts in March; annual totals therefore have different exposure and coverage.",
  "See events.csv for event dates and source URLs, quality.csv for cleaning diagnostics, and monthly.csv for observed coverage.",
  "The revised figure has two panels: mean recorded attendance per observed list date, and TOTAL recorded question items per month (not a mean).",
  "Question totals include all extracted question items, including those without identified outlets. Missing extraction dates are not imputed; months without records remain unavailable.",
  "November 2021 is retained for questions, and post-September-2024 question coverage is shaded as unavailable. Monthly totals and coverage remain in monthly.csv.",
  "No input files or regression estimates were modified. Tables are under configured MEDIA_ROOT/results/descriptives/full_period_press_conferences; the figure is in the repository's output/desc_stats folder."
), file.path(out_dir, "README.txt"))
stopifnot(identical(source_hashes, tools::md5sum(source_paths)),
  sum(monthly$attendance_records, na.rm = TRUE) == nrow(a),
  sum(monthly$question_items, na.rm = TRUE) == nrow(questions),
  sum(monthly$extraction_dates, na.rm = TRUE) == n_distinct(q$date),
  isTRUE(all.equal(monthly$mean_questions,
                   monthly$question_items / monthly$extraction_dates)),
  all(is.na(monthly$mean_questions[monthly$month >= question_end])),
  all(is.finite(monthly$mean_questions[monthly$month == as.Date("2021-11-01")])),
  sum(annual$question_items, na.rm = TRUE) == nrow(questions))
print(summary |> select(metric, value, start, end), n = Inf)
print(annual, n = Inf, width = Inf)
message("Saved ", pdf_path)
