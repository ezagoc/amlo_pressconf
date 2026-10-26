"""Export raw subgroup p-values only; keep diagnostics in separate CSV/RDS audits."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SECOND_YEAR = "--second-year" in sys.argv[1:]
FROM_2023 = "--from-2023" in sys.argv[1:]
assert not (SECOND_YEAR and FROM_2023)
VARIANT = "from_2023" if FROM_2023 else "second_year" if SECOND_YEAR else "subgroups"
SOURCE = ROOT / "output/balance" / VARIANT
DEST = ROOT / "overleaf/tables/balance" / VARIANT
TEX_PATH = DEST.relative_to(ROOT).as_posix()
REPORT_NAME = "balance_from_2023" if FROM_2023 else "balance_second_year" if SECOND_YEAR else "balance_subgroup_pvalues"
DEST.mkdir(parents=True, exist_ok=True)


def read(name):
    with (SOURCE / name).open(newline="") as f:
        return list(csv.DictReader(f))


iv = read("individual_pvalues.csv")
jv = read("joint_pvalues.csv")
windows = ["ratio_12m", "ratio_18m", "ratio_24m", "ratio_full"]
groups = {"print": "Print / newspapers", "digital": "Digital", "aligned": "Aligned",
          "opposition": "Opposition", "independent": "Independent"}
if SECOND_YEAR or FROM_2023:
    groups = {"pooled": "All outlets", **groups}
labels = {"question_attendance_ratio": "Questions / recorded attendance", "contract_value": "Contract value (MXN)",
          "contract_count": "Contracts received", "videos": "Videos published", "views": "Total views",
          "likes": "Total likes", "comments": "Total comments", "interactions": "Total interactions",
          "views_per_video": "Views per video", "likes_per_video": "Likes per video",
          "comments_per_video": "Comments per video", "interactions_per_video": "Interactions per video"}


def pp(r):
    if r["status"] != "ok":
        return "NE"
    x = float(r["p_value"])
    return r"$<0.001$" if x < .001 else f"{x:.3f}"


def row(x):
    return " & ".join(x) + r" \\"


def start(label):
    return ["% Requires booktabs. Raw p-values; no caption or table notes.",
            r"\begingroup\small", r"\setlength{\tabcolsep}{3pt}",
            r"\renewcommand{\arraystretch}{1.25}", r"\noindent%",
            r"\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lcccc@{}}", r"\toprule",
            row([label, "12 months", "18 months", "24 months", "Full history"]), r"\midrule"]


end = [r"\bottomrule", r"\end{tabular*}\par\endgroup", ""]
summary = start("Subgroup")
for g, label in groups.items():
    rr = {r["window"]: r for r in jv if r["group"] == g}
    summary.append(row([label] + [pp(rr[w]) for w in windows]))
(DEST / "joint_pvalues.tex").write_text("\n".join(summary + end))
for g, label in groups.items():
    lines = start("Historical characteristic")
    for metric, nice in labels.items():
        rr = {r["window"]: r for r in iv if r["group"] == g and r["metric"] == metric}
        assert len(rr) == 4
        lines.append(row([nice] + [pp(rr[w]) for w in windows]))
        if metric in ("question_attendance_ratio", "contract_count"):
            lines.append(r"\addlinespace")
    rr = {r["window"]: r for r in jv if r["group"] == g}
    lines += [r"\midrule", row(["Joint: all historical measures"] + [pp(rr[w]) for w in windows])]
    (DEST / f"{g}_pvalues.tex").write_text("\n".join(lines + end))

period_description = ("January 1, 2023--September 30, 2024" if FROM_2023 else
                      "April 18, 2023--April 17, 2024" if SECOND_YEAR else
                      "April 18, 2022--September 27, 2024")
title = "Balance: January 2023 to end of tenure" if FROM_2023 else "Balance: second year after the lottery" if SECOND_YEAR else "Subgroup balance: joint-test p-values"
wrapper = [r"\documentclass[11pt]{article}", r"\usepackage[T1]{fontenc}", r"\usepackage{lmodern}",
           r"\usepackage[letterpaper,margin=0.8in]{geometry}", r"\usepackage{booktabs}",
           r"\begin{document}", rf"\section*{{{title}}}",
           rf"\noindent Post period: {period_description}.\par\medskip",
           rf"\input{{{TEX_PATH}/joint_pvalues.tex}}", r"\bigskip",
           "Each joint test concerns all twelve historical coefficients in one window, conditional on "
           "the relevant missingness indicators and conference-day fixed effects. The sample contains only "
           "recorded attendees, on dates with both asking and nonasking outlets within the subgroup. "
           "Standard errors cluster by outlet source unit.", r"\par\medskip",
           "NE means the full test is not estimable or fails numerical checks. Opposition has too few "
           "outlet clusters for the twelve-restriction clustered test. No reduced test is substituted.", r"\par\medskip",
           "Print and digital are overlapping metadata flags. Independent denotes the existing neutral/unclear "
           "category, not verified independence. Two source units with conflicting political classifications "
           "are excluded from political subgroups.", r"\par\medskip",
           "P-values are unadjusted and exploratory. Small subgroup samples and highly correlated YouTube "
           "measures warrant caution even when numerical checks pass. YouTube engagement is a saved "
           "snapshot for earlier videos, not verified engagement measured before the lottery. "
           "Nonrejection does not establish balance or random question access.", r"\par\medskip",
           "The following pages report individual-variable p-values and repeat the joint p-values. "
           "Individual tests use available-history samples; joint tests retain missing histories with indicators. "
           "All four historical windows still end April 17, 2022; the covariates have not been rolled forward. "
           "The individual and joint tests use different samples and specifications, so their p-values "
           "are not individual and omnibus tests from the same regression."]
if FROM_2023:
    wrapper += [r"\par\medskip",
                "September 27, 2024 is the last usable source date. Attendance and questions are "
                "unobserved on September 28--30; these dates are excluded, not coded as zeros."]
if SECOND_YEAR or FROM_2023:
    pooled = [r for r in jv if r["group"] == "pooled"]
    assert len({(r["n"], r["units"], r["dates"]) for r in pooled}) == 1
    sample = pooled[0]
    wrapper += [r"\par\medskip",
                f"Pooled joint sample: {int(sample['n']):,} outlet-days, {sample['units']} outlet units "
                f"and {sample['dates']} informative conference dates. Earlier full-period outputs are preserved."]
for g, label in groups.items():
    wrapper += [r"\clearpage", rf"\section*{{{label}}}",
                rf"\input{{{TEX_PATH}/{g}_pvalues.tex}}"]
wrapper.append(r"\end{document}")
(SOURCE / f"{REPORT_NAME}.tex").write_text("\n".join(wrapper))
print(SOURCE / f"{REPORT_NAME}.tex")
