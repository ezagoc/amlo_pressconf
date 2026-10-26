# Summarize completed log1p models; this script never re-estimates a model.
# Outputs one standalone LaTeX document and machine-readable results.
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1]]) else
  file.path(getwd(), "code/07-final_panel/22-export-log1p-att-latex.R")
root <- normalizePath(file.path(dirname(script_path), "../.."), mustWork = TRUE)
suppressPackageStartupMessages({library(dplyr); library(readr)})
base <- file.path(root, "output/fect_youtube")
n_boots <- 1000L
raw_only <- "--raw-only" %in% commandArgs(TRUE)
variants <- if (raw_only) "raw" else c("raw", "winsorized")
groups <- c(Pooled = "pooled", Aligned = "aligned", "Opp." = "opp", Independent = "independent")
outcomes <- c(Likes = "likes", Comments = "comments", Views = "views")
scalar <- function(x) if (is.null(x) || length(x) != 1L) NA_real_ else as.numeric(x)
rows <- list()
for (variant in variants) for (outcome in names(outcomes)) {
  folder <- file.path(base, paste0("daily_question_day_log1p_events_1000",
    if (variant == "raw") "_unwinsorized" else "", "_pre14_post6_", outcomes[[outcome]], "_split_independent"))
  metadata <- read_csv(file.path(folder, "model_diagnostics.csv"), show_col_types = FALSE)
  for (group in names(groups)) for (kind in c("Onset", "Carryover")) {
    f <- readRDS(file.path(folder, paste0(groups[[group]], "_", tolower(kind), "_fit.rds")))
    m <- metadata |> filter(sample_group == group, model == kind)
    stopifnot(nrow(m) == 1L, length(f$att.avg.boot) == n_boots,
              all(is.finite(f$att.avg.boot)), f$N == m$n_outlets,
              f$method == "fe", f$force %in% c(3, "two-way"))
    if (kind == "Carryover") stopifnot(
      length(f$att.carryover.boot) == n_boots,
      all(is.finite(f$att.carryover.boot)))
    tab <- if (kind == "Onset") f$est.avg else f$est.carryover
    coef <- as.numeric(tab[1, 1:5])
    stopifnot(all(is.finite(coef)))
    # Recompute native diagnostics on the displayed pre-window only. This
    # uses existing bootstrap draws and never refits/restricts the ATT model.
    displayed_test <- if (kind == "Onset") {
      get("diagtest", asNamespace("fect"))(f, pre.periods = c(-13L, 0L),
                                         tost.threshold = f$test.out$tost.threshold)
    } else list()
    rows[[paste(variant, outcome, group, kind)]] <- tibble(
      variant, outcome, sample_group = group, model = kind,
      estimate = coef[1], standard_error = coef[2], conf95_low = coef[3],
      conf95_high = coef[4], p_value = coef[5],
      conf90_low = coef[1] - qnorm(.95) * coef[2], conf90_high = coef[1] + qnorm(.95) * coef[2],
      outlet_days = m$n_outlet_days, outlets = f$N, days = f$T,
      treated_outlets = f$Ntr, never_treated_outlets = f$Nco,
      question_days = m$n_treated_days, rmse = scalar(f$rmse),
      attendance_estimate = f$est.beta[1, 1], attendance_se = f$est.beta[1, 2],
      attendance_p = f$est.beta[1, 5], f_statistic = scalar(f$test.out$f.stat),
      f_p = scalar(f$test.out$f.p), tost_p = scalar(f$test.out$tost.equiv.p),
      tost_threshold = scalar(f$test.out$tost.threshold),
      displayed_f_p = scalar(displayed_test$f.p),
      displayed_tost_p = scalar(displayed_test$tost.equiv.p),
      displayed_tost_threshold = scalar(displayed_test$tost.threshold),
      carryover_test_p = scalar(f$test.out$carryover.p),
      carryover_equivalence_p = scalar(f$test.out$carryover.equiv.p),
      pre_day_min = if (length(f$pre.periods)) min(f$pre.periods) - 1L else NA_real_,
      pre_day_max = if (length(f$pre.periods)) max(f$pre.periods) - 1L else NA_real_,
      winsor_p1 = m$winsor_p1, winsor_p99 = m$winsor_p99,
      bootstrap_replications = n_boots, start = m$start, end = m$end)
  }
}
results <- bind_rows(rows)
stopifnot(nrow(results) == 24L * length(variants), !anyDuplicated(results[c("variant", "outcome", "sample_group", "model")]))
out_dir <- file.path(base, "log1p_comparison_1000")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
write_csv(results, file.path(out_dir, if (raw_only) "att_and_diagnostics_raw.csv" else "att_and_diagnostics.csv"))
tex_dir <- file.path(root, "output/latex")
dir.create(tex_dir, recursive = TRUE, showWarnings = FALSE)
fmt <- function(x) ifelse(is.finite(x), sprintf("%.3f", x), "---")
pv <- function(x) ifelse(!is.finite(x), "---", ifelse(x < .001, "$<0.001$", sprintf("%.3f", x)))
ci <- function(lo, hi) paste0("[", fmt(lo), ", ", fmt(hi), "]")
line <- function(x) paste0(paste(x, collapse = " & "), " ", strrep(intToUtf8(92), 2))
lines <- c("\\documentclass[a4paper,10pt]{article}",
  "\\usepackage[landscape,margin=1.4cm]{geometry}",
  "\\usepackage{booktabs,array,amsmath}",
  "\\usepackage[T1]{fontenc}",
  "\\usepackage[colorlinks=true,urlcolor=blue]{hyperref}",
  "\\setlength{\\parindent}{0pt}", "\\setlength{\\tabcolsep}{5pt}",
  "\\renewcommand{\\arraystretch}{1.14}", "\\begin{document}")
if (raw_only) lines <- c(lines, "\\textit{Interim report: the raw specification is complete; winsorized results are still being estimated.}")
for (variant in variants) {
  title <- if (variant == "raw") "Raw outcomes: $\\log(1+y)$" else "Winsorized outcomes: $\\log(1+y^{W})$"
  d <- results |> filter(.data$variant == .env$variant)
  lines <- c(lines, paste0("\\section*{", title, "}"),
    "\\textbf{Daily FEct estimates, 18 April 2022--31 December 2024.} Question-day-only treatment; 1,000 outlet bootstrap replications.",
    "\\medskip", "\\begin{center}\\small", "\\begin{tabular}{llrrrrrrrr}", "\\toprule",
    line(c("", "", "\\multicolumn{4}{c}{Question-day ATT}", "\\multicolumn{4}{c}{Mean carryover, days +1 to +6}")),
    "\\cmidrule(lr){3-6}\\cmidrule(lr){7-10}",
    line(c("Group", "Outcome", "ATT", "SE", "95\\% CI", "$p$", "Effect", "SE", "95\\% CI", "$p$")),
    "\\midrule")
  for (group in names(groups)) {
    for (outcome in names(outcomes)) {
      a <- d |> filter(sample_group == group, .data$outcome == .env$outcome, model == "Onset")
      b <- d |> filter(sample_group == group, .data$outcome == .env$outcome, model == "Carryover")
      lines <- c(lines, line(c(if (outcome == "Likes") group else "", outcome,
        fmt(a$estimate), fmt(a$standard_error), ci(a$conf95_low, a$conf95_high), pv(a$p_value),
        fmt(b$estimate), fmt(b$standard_error), ci(b$conf95_low, b$conf95_high), pv(b$p_value))))
    }
    lines <- c(lines, "\\addlinespace")
  }
  lines <- c(lines, "\\bottomrule\\end{tabular}\\end{center}",
    "\\textbf{Sample and specification} (identical across outcomes and transformations)",
    "\\begin{center}\\small\\begin{tabular}{lrrrrrr}\\toprule",
    line(c("Group", "Outlet-days", "Outlets", "Ever-treated", "Never-treated", "Question-days", "Calendar days")), "\\midrule")
  for (group in names(groups)) {
    a <- d |> filter(sample_group == group, outcome == "Likes", model == "Onset")
    lines <- c(lines, line(c(group, format(a$outlet_days, big.mark = ","), a$outlets,
                            a$treated_outlets, a$never_treated_outlets, a$question_days, a$days)))
  }
  lines <- c(lines, "\\bottomrule\\end{tabular}\\end{center}",
    "\\footnotesize\\textit{Notes.} All models include outlet and date fixed effects and a same-day attendance dummy. Independent denotes the metadata's unclear category. Opp. has only six ever-treated outlets; inference should be treated cautiously. Standard errors, 95\\% intervals and two-sided $p$-values are taken directly from FEct; intervals are pointwise and $p$-values are unadjusted for multiple comparisons. Bootstrap resampling is by outlet, not a permutation test.",
    "\\par\\smallskip The ATT averages all treated outlet-days, including consecutive question days. In the event-study figure, day 0 denotes the first treated day of an episode; these estimands need not be identical. Carryover is estimated with a separate fit excluding days +1 through +6 from counterfactual estimation; follow-up stops upon re-treatment.",
    if (variant == "raw") "\\par\\smallskip No winsorization. Outcomes are $\\log(1+y)$, including zeros; coefficients are not automatically percentage effects in raw outcomes." else
      "\\par\\smallskip Raw counts are capped at the pooled 1st and 99th percentiles, separately by outcome, before applying $\\log(1+y^{W})$. Cutoffs are fixed across groups and bootstrap draws. Coefficients are not automatically percentage effects in raw outcomes.",
    "\\par\\smallskip Views, likes and comments are collected video metrics attributed to publication date, not engagement events received on that calendar date.",
    "\\newpage", paste0("\\section*{Model diagnostics: ", title, "}"),
    "\\begin{center}\\small\\begin{tabular}{llrrrrrrr}\\toprule",
    line(c("Group", "Outcome", "RMSE", "Attendance (SE)", "Default $F$ $p$", "$F$ $p$: 14 days", "TOST $p$: 14 days", "TOST bound", "Default pre-days")), "\\midrule")
  for (group in names(groups)) {
    for (outcome in names(outcomes)) {
      a <- d |> filter(sample_group == group, .data$outcome == .env$outcome, model == "Onset")
      lines <- c(lines, line(c(if (outcome == "Likes") group else "", outcome, fmt(a$rmse),
        paste0(fmt(a$attendance_estimate), " (", fmt(a$attendance_se), ")"), pv(a$f_p),
        pv(a$displayed_f_p), pv(a$displayed_tost_p), fmt(a$displayed_tost_threshold),
        paste0(a$pre_day_min, " to ", a$pre_day_max))))
    }
    lines <- c(lines, "\\addlinespace")
  }
  lines <- c(lines, "\\bottomrule\\end{tabular}\\end{center}",
    "\\footnotesize\\textit{Notes.} These are the onset fit's native FEct diagnostics (version 2.4.5). RMSE is on the transformed-outcome scale. The attendance coefficient is a control-variable association, not the ATT. A dash means the statistic is unavailable, not zero or evidence that the model passes the test.",
    "\\par\\smallskip The $F$-test checks joint zero pre-treatment discrepancies. TOST tests whether pre-treatment discrepancies fall inside the reported symmetric equivalence bound. A small TOST $p$-value supports equivalence to within that bound; a large value does not establish a violation. Default windows follow FEct's support rule (\\texttt{proportion=0.3}). The 14-day columns recompute native diagnostics on plotted days $-14$ to $-1$ (FEct raw periods $-13$ to 0), using the same fitted model and bootstrap draws. Default windows are also listed in plotted-day units. These are in-sample diagnostics (\\texttt{loo=FALSE}), not leave-one-period-out or randomized placebo tests.",
    "\\par\\smallskip The models and diagnostics rely on identifying assumptions; none of these tests proves causality. Full onset and carryover diagnostics, including carryover equivalence tests, are included in the accompanying CSV.",
    "\\par\\smallskip Package reference: \\url{https://yiqingxu.org/packages/fect/}.")
  if (variant == "winsorized") {
    lines <- c(lines, "\\medskip\\normalsize\\textbf{Pooled winsorization cutoffs, before taking logs}",
      "\\begin{center}\\small\\begin{tabular}{lrr}\\toprule", line(c("Outcome", "1st percentile", "99th percentile")), "\\midrule")
    for (outcome in names(outcomes)) {
      a <- d |> filter(sample_group == "Pooled", .data$outcome == .env$outcome, model == "Onset")
      lines <- c(lines, line(c(outcome, fmt(a$winsor_p1), fmt(a$winsor_p99))))
    }
    lines <- c(lines, "\\bottomrule\\end{tabular}\\end{center}")
  } else if (variant != tail(variants, 1)) lines <- c(lines, "\\newpage")
}
lines <- c(lines, "\\end{document}")
tex_path <- file.path(tex_dir, "fect_likes_comments_views_log1p_1000.tex")
writeLines(lines, tex_path)
message("Saved ", tex_path)
