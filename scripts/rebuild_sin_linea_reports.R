# Reuse the staging runner without rerunning its completed data builds.
expressions <- parse("scripts/stage_sin_linea.R")
for (expr in expressions) {
  if (is.call(expr) && identical(expr[[1]],as.name("<-")) && identical(expr[[2]],as.name("q"))) break
  eval(expr)
}
scripts <- if ("--ratios-only" %in% commandArgs(TRUE)) {
  "27-ratio-distributions-top10-changes.R"
} else if ("--source-only" %in% commandArgs(TRUE)) {
  c("25-full-period-conference-descriptives.R","26-outlet-rankings-lottery.R",
    "27-ratio-distributions-top10-changes.R")
} else c("01-summary_stats_plots.R","02-monthly_attendance_questions.R")
for (script in scripts) {
  run(file.path("code/07-final_panel",script),function(x) {
    x[grepl("^script_arg <-",x)] <- "script_arg <- character()"
    x <- gsub('file.path(root, "output", "desc_stats")',
              paste0('file.path("',stage,'", "repo/output/desc_stats")'),x,fixed=TRUE)
    x <- gsub('file.path(root, "output/desc_stats")',
              paste0('file.path("',stage,'", "repo/output/desc_stats")'),x,fixed=TRUE)
    x
  },overrides=TRUE)
  gc()
}
cat("Affected descriptive tables and figures rebuilt.\n")
