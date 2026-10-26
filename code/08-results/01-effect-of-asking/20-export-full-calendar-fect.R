# Compact publication table for the NEW full-calendar FEct history comparison.
# Requires all twelve validated, 1,000-bootstrap fits from script 19.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages(library(dplyr))
out <- file.path(out, "legacy_full_calendar_asinh_winsor99_history")
fd <- file.path(out, "fect_1000")
x <- readRDS(file.path(out, "panel.rds"))
files <- file.path(fd, paste0("results_", rep(x$outcomes, each = 2), "_", c("baseline", "adjusted"), ".csv"))
stopifnot(all(file.exists(files)))
res <- bind_rows(lapply(files, read.csv))
stopifnot(nrow(res) == 12, !anyDuplicated(res[c("outcome", "model")]),
  all(res$bootstrap_replications == 1000), all(res$valid_bootstraps == 1000),
  all(res$n == 163185), all(res$units == 165), all(res$dates == 989), all(res$asking == 499))
manifest <- read.csv(file.path(out, "input_manifest.csv"))
stopifnot(identical(unname(tools::md5sum(manifest$path)), manifest$md5))

# Verify every displayed scalar against the saved FEct fit and the bootstrap SD.
for (i in seq_len(nrow(res))) {
  z <- res[i, ]; tag <- paste(z$outcome, if (z$model == "Baseline") "baseline" else "adjusted", sep = "_")
  saved <- readRDS(file.path(fd, paste0(tag, ".rds")))
  stopifnot(identical(saved$input$panel_md5, unname(tools::md5sum(file.path(out, "panel.rds")))))
  f <- saved$fit
  a <- as.numeric(f$est.avg[1, 1:5])
  stopifnot(length(f$att.avg.boot) == 1000, all(is.finite(f$att.avg.boot)),
    max(abs(a - unlist(z[c("estimate", "se", "ci_low", "ci_high", "p_value")], use.names = FALSE))) < 1e-10,
    abs(sd(as.numeric(f$att.avg.boot)) - z$se) < 1e-8,
    abs(z$p_value - 2 * pnorm(-abs(z$estimate / z$se))) < 1e-10,
    max(abs(c(z$ci_low, z$ci_high) - (z$estimate + c(-1, 1) * qnorm(.975) * z$se))) < 1e-8,
    abs(z$estimate - z$manual_imputation_att) < 1e-4,
    all(saved$input$data$attendance_dummy == x$data$attendance_dummy),
    all(saved$input$data$ask == x$data$ask),
    identical(saved$input$data$Y, asinh(pmin(x$data[[z$outcome]], x$cutoffs$upper[x$cutoffs$outcome == z$outcome]))))
}

tex_dir <- file.path(root, "overleaf/tables/effect_of_asking")
stem <- "fect_full_calendar_asinh_winsor99_histories"
row <- function(label, values) paste0(paste(c(label, values), collapse = " & "), " \\\\")
fmt <- function(v) sprintf("%.3f", v)
integer_fmt <- function(v) format(v, big.mark = ",", scientific = FALSE, trim = TRUE)
panel <- function(outcomes, title) {
  grid <- expand.grid(model = c("Baseline", "History adjusted"), outcome = outcomes, stringsAsFactors = FALSE)
  r <- bind_rows(lapply(seq_len(nrow(grid)), function(i) {
    z <- filter(res, outcome == grid$outcome[i], model == grid$model[i])
    stopifnot(nrow(z) == 1); z
  }))
  labels <- c(videos = "Total videos", interactions = "Total interactions", mean_interactions = "Mean int./video",
              likes = "Likes", comments = "Comments", views = "Views")
  c("\\begingroup\\centering\\scriptsize", "\\setlength{\\tabcolsep}{2.5pt}",
    "\\renewcommand{\\arraystretch}{1.02}",
    "\\begin{tabular*}{0.96\\linewidth}{@{\\extracolsep{\\fill}}lcccccc@{}}",
    "\\toprule", paste0("\\multicolumn{7}{@{}l}{\\textit{", title, "}} \\\\") ,
    "\\addlinespace[4pt]",
    paste0(" & ", paste(paste0("\\multicolumn{2}{c}{", labels[outcomes], "}"), collapse = " & "), " \\\\") ,
    "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\\cmidrule(l){6-7}",
    row("", paste0("(", 1:6, ")")), "\\midrule",
    row("Same-day asking ATT", fmt(r$estimate)),
    row("", paste0("(", fmt(r$se), ")")), "\\midrule",
    row("FEct $p$-value", paste0("[", fmt(r$p_value), "]")), "\\midrule",
    row("Outlet fixed effects", rep("Yes", 6)), row("Date fixed effects", rep("Yes", 6)),
    row("Attendance dummy", rep("Yes", 6)),
    row("Prior history $\\times$ quarter", rep(c("No", "Yes"), 3)), "\\addlinespace[3pt]",
    row("Observations", integer_fmt(r$n)), row("Outlets/channels", integer_fmt(r$units)),
    row("Calendar days", integer_fmt(r$dates)), row("Question-days", integer_fmt(r$asking)),
    row("Ever-treated outlets", integer_fmt(r$ever_treated)), row("RMSE", fmt(r$rmse)),
    row("Outlet bootstrap replications", integer_fmt(r$bootstrap_replications)),
    "\\bottomrule\\end{tabular*}\\par\\endgroup")
}
body <- c("% Requires booktabs. Estimates and bootstrap SEs from FEct, not wild-bootstrap inference.",
  panel(c("videos", "interactions", "mean_interactions"), "Panel A. Publishing and interactions"),
  "\\vspace{12pt}", panel(c("likes", "comments", "views"), "Panel B. Likes, comments, and views"))
writeLines(body, file.path(tex_dir, paste0(stem, ".tex")))
wrapper <- c("\\documentclass[10pt,letterpaper]{article}",
  "\\usepackage[margin=0.7in]{geometry}", "\\usepackage[T1]{fontenc}",
  "\\usepackage{lmodern,booktabs}", "\\pagestyle{empty}\\setlength{\\parindent}{0pt}",
  "\\begin{document}",
  "{\\normalsize\\bfseries Full-calendar FEct: baseline and historical adjustment}\\par\\vspace{8pt}",
  paste0("\\input{", stem, ".tex}"), "\\vspace{7pt}",
  "{\\scriptsize Outlet-bootstrap standard errors in parentheses; FEct $p$-values in square brackets. Each raw outcome is capped at its pooled full-calendar 99th percentile before applying asinh. The lower tail is unchanged. Total interactions = likes + comments; mean interactions per video uses the raw ratio, coded zero on no-video days, before capping.}\\par\\vspace{5pt}",
  "{\\scriptsize Full calendar: April 18, 2022--December 31, 2024, using the earlier panel's treatment, attendance, and zero-coding rules. Treatment is at least one question on that day. All models use two-way fixed-effect imputation and an attendance dummy. Even-numbered columns add the prior-year questions/recorded-attendance ratio and its missingness indicator, each interacted with calendar quarter (first quarter omitted). History covers April 18, 2021--April 17, 2022, excluding November 2021 on both sides of the ratio. Histories are observed for 71 of 165 entities; missing histories do not remove entities.}\\par\\vspace{5pt}",
  "{\\scriptsize Inference uses 1,000 entity/outlet bootstrap replications, not wild bootstrap; $p$-values and intervals follow FEct's default normal approximation using bootstrap SEs, without multiplicity adjustment. ATT averages treated outlet-days, including consecutive question days. These are static same-day estimates; no carryover holdout is imposed. Engagement is measured at the saved snapshot for videos published that day, not as engagement received that day. Earlier full-calendar coding treats unrecorded question dates as zero and allows question-implied attendance; this is not the newer recorded-attendee-only sample.}",
  "\\end{document}")
writeLines(wrapper, file.path(tex_dir, paste0(stem, "_preview.tex")))
cat("PASS: all 12 final fits, transformations, samples, 12,000 finite draws and table scalars checked.\n")
print(res |> select(outcome, model, estimate, se, p_value), width = 120)
