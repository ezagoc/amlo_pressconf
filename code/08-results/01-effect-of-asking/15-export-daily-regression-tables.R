# Publication tables from saved DAILY fits and validated wild-bootstrap tests.
# Run 11-wild-cluster-bootstrap.R --pooled first. No models are estimated here.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages(library(fixest))
winsor99 <- "--winsor99" %in% commandArgs(TRUE)
if (winsor99) out <- file.path(out, paste0("daily_winsor99_six_outcomes", DAILY_TRANSFORMATION_SUFFIX))
suffix <- if (winsor99) paste0("_winsor99", DAILY_TRANSFORMATION_SUFFIX) else ""
dest <- file.path(root, "overleaf/tables/effect_of_asking")
dir.create(dest, recursive = TRUE, showWarnings = FALSE)
num <- function(x) sprintf("%.3f", x)
count <- function(x) format(x, big.mark = ",", scientific = FALSE, trim = TRUE)
row <- function(label, values) paste0(paste(c(label, values), collapse = " & "), " \\\\")

export_table <- function(interaction = FALSE, outcomes = OUTCOMES, panel_label = NULL) {
  columns <- expand.grid(model = c("Baseline", "History adjusted"),
                         outcome = outcomes, stringsAsFactors = FALSE)
  labels <- c(likes = "Likes", comments = "Comments", views = "Views",
              videos = "Total videos", interactions = "Total interactions",
              mean_interactions = "Mean int./video")
  location <- if (interaction) file.path(out, "pooled_interactions_combined") else out
  fit_path <- file.path(location, if (interaction) "fits.rds" else "regression_fits.rds")
  fits <- readRDS(fit_path)
  boot_dir <- file.path(location, "wild_cluster_9999")
  manifest <- read.csv(file.path(boot_dir, "input_manifest.csv"))
  stopifnot(identical(unname(tools::md5sum(manifest$path)), manifest$md5))
  boot <- read.csv(file.path(boot_dir, "results.csv"))
  stopifnot(all(boot$B == 9999L), all(boot$valid_draws == 9999L), all(boot$impose_null))
  selected <- lapply(seq_len(nrow(columns)), function(j) {
    z <- columns[j, ]
    f <- fits[[paste(z$outcome, z$model, sep = ":")]]
    b <- boot[boot$outcome == z$outcome & boot$model == z$model, ]
    stopifnot(nobs(f) == unique(b$n), length(f$fixef_id$unit_id) == nobs(f))
    list(f = f, b = b)
  })
  lines <- c("% Requires \\usepackage{booktabs}; generated from saved daily fits.",
    if (winsor99) "\\begingroup\\centering\\scriptsize" else "\\begingroup\\centering\\small",
    "\\setlength{\\tabcolsep}{2.5pt}", "\\renewcommand{\\arraystretch}{1.02}",
    if (winsor99) "\\begin{tabular*}{0.94\\linewidth}{@{\\extracolsep{\\fill}}lcccccc@{}}" else
      "\\begin{tabular*}{\\linewidth}{@{\\extracolsep{\\fill}}lcccccc@{}}",
    "\\toprule",
    if (!is.null(panel_label)) c(paste0("\\multicolumn{7}{@{}l}{\\textit{", panel_label, "}} \\\\"), "\\addlinespace[4pt]"),
    paste0(" & ", paste(paste0("\\multicolumn{2}{c}{", labels[outcomes], "}"), collapse = " & "), " \\\\") ,
    "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\\cmidrule(l){6-7}",
    row("", paste0("(", 1:6, ")")), "\\midrule")
  terms <- if (interaction) c("ask", "ask_aligned") else "ask"
  p_rows <- character()
  for (term in terms) {
    label <- if (term == "ask") "Asked a question" else "Asked $\\times$ Aligned"
    boot_label <- if (!interaction) "Asked a question" else if (term == "ask")
      "Opp. + Independent" else "Aligned - (Opp. + Independent)"
    vals <- lapply(selected, function(z) {
      ct <- coeftable(z$f)[term, ]
      b <- z$b[z$b$label == boot_label, ]
      stopifnot(nrow(b) == 1, abs(ct[1] - b$estimate) < 1e-9,
                abs(ct[2] - b$conventional_se) < 1e-9,
                abs(ct[4] - b$conventional_p) < 1e-9)
      c(estimate = ct[1], se = ct[2], p = ct[4], wild = b$wild_p)
    })
    # Select positions because coeftable entries carry their own names.
    lines <- c(lines, row(label, vapply(vals, function(v) num(v[1]), "")),
      row("", vapply(vals, function(v) paste0("(", num(v[2]), ")"), "")),
      if (term != tail(terms, 1)) "\\addlinespace[5pt]")
    p_prefix <- if (!interaction) "" else if (term == "ask") "Asked: " else "Asked $\\times$ Aligned: "
    p_rows <- c(p_rows,
      row(paste0(p_prefix, "Clustered $p$"), vapply(vals, function(v) paste0("[", num(v[3]), "]"), "")),
      row(paste0(p_prefix, "Wild-bootstrap $p$"), vapply(vals, function(v) paste0("[", num(v[4]), "]"), "")),
      if (term != tail(terms, 1)) "\\addlinespace[3pt]")
  }
  metric <- function(fun) vapply(selected, fun, "")
  lines <- c(lines, "\\midrule", p_rows, "\\midrule",
    row("Outlet fixed effects", rep("Yes", 6)),
    row("Date fixed effects", rep("Yes", 6)),
    row("Prior history $\\times$ quarter", rep(c("No", "Yes"), 3)),
    "\\addlinespace[3pt]",
    row("Observations", metric(function(z) count(nobs(z$f)))),
    row("Outlets (clusters)", metric(function(z) count(unique(z$b$clusters)))),
    row("Conference dates", metric(function(z) count(unique(z$b$dates)))),
    row("Within $R^2$", metric(function(z) sprintf("%.4f", as.numeric(fitstat(z$f, "wr2")[[1]])))),
    row("Bootstrap replications", rep("9,999", 6)),
    "\\bottomrule", "\\end{tabular*}\\par\\endgroup")
  lines
}
for (interaction in c(FALSE, TRUE)) {
  lines <- if (!winsor99) export_table(interaction) else c(
    export_table(interaction, c("videos", "interactions", "mean_interactions"),
                 "Panel A. Publishing and interactions"),
    "\\vspace{10pt}",
    export_table(interaction, OUTCOMES, "Panel B. Likes, comments, and views"))
  name <- paste0(if (interaction) "daily_interaction_regression" else "daily_main_regression", suffix, ".tex")
  writeLines(lines, file.path(dest, name))
  cat("Validated and exported", name, "\n")
}

preview <- c(
  "\\documentclass[10pt,letterpaper]{article}",
  "\\usepackage[margin=0.7in]{geometry}",
  "\\usepackage{booktabs,lmodern}",
  "\\usepackage[T1]{fontenc}",
  "\\pagestyle{empty}\\setlength{\\parindent}{0pt}",
  "\\begin{document}",
  "{\\large\\bfseries Table 1. Daily effect of asking a question}\\par\\vspace{8pt}",
  "\\input{daily_main_regression.tex}",
  "\\vspace{5pt}{\\footnotesize Outlet-clustered standard errors in parentheses. Outcomes are $\\log(1+y)$ of total likes, comments, and views on videos published that day, without winsorization. The sample contains directly recorded attendees from April 19, 2022 to September 27, 2024.}\\par",
  "\\vspace{18pt}",
  "{\\large\\bfseries Table 2. Daily effects by outlet alignment}\\par\\vspace{8pt}",
  "\\input{daily_interaction_regression.tex}",
  "\\vspace{5pt}{\\footnotesize The reference group is Opp. + Independent. Asked $\\times$ Aligned reports the difference between Aligned and the reference group, not the total Aligned effect. La Jornada's shared source ID is excluded because its metadata affiliations conflict; dates without remaining treatment variation and singletons are removed.}\\par",
  "\\vspace{7pt}{\\footnotesize Both tables use outlet and shared date fixed effects. Even-numbered columns add the pre-lottery 12-month questions/recorded-attendance ratio and its missingness indicator, each interacted with quarter. Clustered $p$-values use outlet-clustered inference; wild $p$-values use two-sided, null-imposed outlet WCR11 bootstrap-$t$ tests with 9,999 Rademacher draws. No multiplicity adjustment. Engagement is measured at the saved snapshot, not as same-day engagement received.}",
  "\\end{document}")
if (winsor99) {
  transform_description <- switch(DAILY_TRANSFORMATION,
    log1p = "$\\log(1+y)$",
    asinh = "$\\mathrm{asinh}(y)$",
    chen_roth_x0 = "the Chen--Roth $x=0$ calibration: $\\log(y)$ for $y>0$ and $\\log(m)$ for $y=0$, where $m$ is the pooled estimation-sample minimum positive value for that outcome")
  transform_title <- switch(DAILY_TRANSFORMATION, log1p = "Log(1+y)", asinh = "Asinh", chen_roth_x0 = "Chen--Roth (x=0)")
  notes <- paste0("\\vspace{7pt}{\\scriptsize Outlet-clustered standard errors in parentheses; $p$-values in square brackets below the coefficient-block rule. ",
    "Each raw daily outcome is capped at its pooled-sample 99th percentile, then transformed using ", transform_description, ". ",
    "Common cutoffs apply to both tables; the lower tail is unchanged. Total interactions = likes + comments; ",
    "mean interactions per video = raw interactions/raw video count (zero for no-video days), computed before capping. ",
    "Even-numbered columns add the pre-lottery 12-month questions/recorded-attendance ratio and its missingness indicator, ",
    "each interacted with quarter. Wild $p$-values: two-sided null-imposed outlet WCR11 bootstrap-$t$, ",
    "9,999 Rademacher draws; no multiplicity adjustment.}\\par")
  preview <- c(preview[1:6],
    paste0("{\\normalsize\\bfseries Table 1. Daily effect of asking a question --- ", transform_title, "}\\par\\vspace{8pt}"),
    paste0("\\input{daily_main_regression", suffix, ".tex}"), notes,
    "\\vspace{5pt}{\\scriptsize Directly recorded attendees, April 19, 2022--September 27, 2024. Outcomes refer to videos published that day; engagement is measured at the saved snapshot, not as engagement received that day.}\\par",
    "\\newpage",
    paste0("{\\normalsize\\bfseries Table 2. Daily effects by outlet alignment --- ", transform_title, "}\\par\\vspace{8pt}"),
    paste0("\\input{daily_interaction_regression", suffix, ".tex}"), notes,
    "\\vspace{5pt}{\\scriptsize Reference group: Opp. + Independent. Asked $\\times$ Aligned is the Aligned-minus-reference difference, not the total Aligned effect. The sample excludes La Jornada's conflicting metadata affiliation and dates without remaining treatment variation; fixed-effect singletons are removed.}\\par",
    "\\end{document}")
}
writeLines(preview, file.path(dest, paste0("daily_regression_tables_preview", suffix, ".tex")))
