"""Check that the publication fragments reproduce the saved balance results."""
import csv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
dest = root / "overleaf/tables/balance"
individual = (dest / "balance_individual_histories.tex").read_text()
joint = (dest / "balance_joint_histories.tex").read_text()
with (root / "output/balance/historical_outcomes/individual_balance.csv").open() as f:
    rows = list(csv.DictReader(f))
assert len(rows) == 48
for r in rows:
    expected = (rf"\shortstack{{${float(r['estimate']):.3f}$\\{{\scriptsize "
                rf"$[{float(r['ci_low']):.3f},\ {float(r['ci_high']):.3f}]$}}}}")
    assert expected in individual, (r["metric"], r["window"])
with (root / "output/balance/joint_by_window/joint_tests.csv").open() as f:
    tests = [r for r in csv.DictReader(f) if r["test"] == "histories"]
assert len(tests) == 4
for r in tests:
    assert f"{float(r['F']):.3f}" in joint
    assert f"F({r['df1']},{r['df2']})={float(r['F']):.3f}" in joint
    assert f"F({r['df1']},{r['df2']})={float(r['F']):.3f}" in individual
for text in (individual, joint):
    assert r"\caption" not in text and "Notes:" not in text
    assert r"\begin{table}" not in text
    assert text.count(r"\begin{tabular*}") == text.count(r"\end{tabular*}") == 1
log = (root / "tmp/pdfs/balance_latex_tables_preview.log").read_text()
assert "Overfull" not in log and "Underfull" not in log and "! LaTeX Error" not in log
print("PASS: 48 individual estimates/CIs, four historical-only joint tests, caption/note-free fragments, clean LaTeX compile.")
