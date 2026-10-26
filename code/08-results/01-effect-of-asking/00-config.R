# Shared configuration. Run the numbered scripts with Rscript from any directory.
arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
entry <- if (length(arg)) sub("^--file=", "", arg[[1]]) else
  file.path(getwd(), "code/08-results/01-effect-of-asking/00-config.R")
root <- normalizePath(file.path(dirname(entry), "../../.."), mustWork = TRUE)
source(file.path(root, "project_paths.R"))
out <- media_path("results", "effect_of_asking")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
source_dir <- media_path("data", "06-outcomes", "deduplicated_source_panels")
FROM <- as.Date("2022-04-18")
TO <- as.Date("2024-09-27") # Last conference in the established AMLO balance sample.
OUTCOMES <- c("likes", "comments", "views")
SEED <- 20261012L
# Optional alternative transformations for the six-outcome daily sensitivity.
transform_arg <- grep("^--transform=", commandArgs(TRUE), value = TRUE)
DAILY_TRANSFORMATION <- if (length(transform_arg)) sub("^--transform=", "", transform_arg[1]) else "log1p"
stopifnot(DAILY_TRANSFORMATION %in% c("log1p", "asinh", "chen_roth_x0"))
DAILY_TRANSFORMATION_SUFFIX <- if (DAILY_TRANSFORMATION == "log1p") "" else paste0("_", DAILY_TRANSFORMATION)
save_csv <- function(x, name) write.csv(x, file.path(out, name), row.names = FALSE)
informative <- function(x) dplyr::ungroup(dplyr::filter(dplyr::group_by(x, date),
                                                       any(ask == 1), any(ask == 0)))
flow_row <- function(x, stage) data.frame(stage, n = nrow(x),
  units = dplyr::n_distinct(x$unit_id), dates = dplyr::n_distinct(x$date),
  asking = sum(x$ask), from = min(x$date), to = max(x$date))
