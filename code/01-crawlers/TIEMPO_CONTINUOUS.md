# Tiempo continuous collection v4 — still pending real source review

Kevin's separate mode collects a new, explicitly authorized new_urls plan. It
does not replace validation400, production808, May27 or 2019 protocols. Those
plans retain their actual-source-review gates. No shared-data merge, tracker
completion, implicit run-all, old error retry or automatic operator approval is
provided. This implementation separates collection from article acceptance.

## Frozen scope

The CLI scripts/run_tiempo_continuous.py has registry, freeze and run commands.
Registry and freeze are offline. Run needs --max-batches and --allow-network;
a separate operator authorization is still required. Offline tests inject fake
responses. Plan schema tiempo-continuous-bounded-risk-v4 freezes the v4 policy,
code/input/registry hashes, explicit 2018–2025 date window, request budget,
timeout, disk threshold and pause. A changed policy requires a new plan.

Only the dedicated Media/data/00-newspaper_data/crawler/pilots/Kevin/
tiempo_continuous/<new-name> namespace and new TC_ IDs are accepted. Each plan
has at most 2,000 URLs and each batch at most 80. Inputs must be consistent
new_urls, unprotected by the old baseline. --queue-db and --queue-db-sha256
bind every original candidate column against read-only original queue rows
at freeze and resume. Empty discovery-date evidence is rejected. Discovery
metadata never fills missing article fields.

Freeze requires exclusion inputs for validation400 (400), production808 (808),
may27 (62), historical20190304 (1000), as {role,path,sha256} JSON records.
Additional prior planned inputs must also be supplied when applicable.
Canonical/body duplicate detection is within this plan; cross-stage aliases
and bodies still need separate selection/acceptance checks. Requested-URL
exclusion is not a claim of global article deduplication.

## Automatic diagnosis and continuation

Every saved page is independently compared against raw HTML: title, summary,
body, author, publication evidence, canonical, media and structure. Full flags
are retained. Joint route/layout/media-host/title-mode signatures and header,
lead and body tag paths come only from currently hash-bound actual reviewed
eligible article examples. Repeated paragraph count is ignored. Unreviewed
rows never enlarge the registry.

Raw-body comparison independently recognizes the evidenced Instagram UI leaves:
the styled view-post prompt, a styled same-post attribution, and the narrow
attribution plus direct time template. It checks DOM/style/link identity and
the displayed timestamp, retains real captions, and records recognized text in
independently_recognized_template_ui. It does not trust the parser's removal
list or ignore arbitrary footer text. Unrecognized variants remain visible to
the source comparison and can produce an explicit difference.

Critical failures stop before another request: HTTP/transport failures,
soft error pages, unsupported origins or established identity conflicts,
snapshot/database/export integrity failure, budget/clock/locking/disk failures.
The current response is saved if possible; storage failure itself stops work.

Unexplained field or structure differences put the row into
quarantined_pending_source_review. Collection may continue after one such row.
It stops before the next request when either:

- Two adjacent saved rows share publication_date, body_or_media or
  article_structure anomaly families.
- The latest 80 saved rows include three rows with any unexplained anomaly.

One row counts once toward the 80-row threshold even with multiple flags.
A normal row breaks consecutive-family adjacency. The window crosses batches
and is deterministically replayed from saved evidence on explicit restart.
Other metadata anomalies count toward the window but do not invent a same-family
rule outside the three named families.

A previously unseen joint signature alone is novelty, not an extraction failure.
It remains flagged for source sampling, does not count toward anomaly thresholds,
never trains the registry, and does not confer manual approval. Genuine source
missing titles keep null title and missing_title; they are not fabricated successes.

## Storage, output and checks

Each row has a snapshot/fields-bound row_checks receipt. After each batch,
native CSV/Parquet and all derived views are compared cell by cell. The views are:

- all_results: every row with original fields/error and automatic flags.
- core_fields_complete: native qa_status=success, which can include quarantine.
- usable_candidates: field-complete rows with no automatic anomaly; still
  not_reviewed and pending stage review, never accepted articles.
- quarantined_results: rows with unexplained or critical automatic findings.
- source_gaps, failed_or_incomplete_urls and novel_types: explicit potentially
  overlapping subsets, with counts/definitions in the manifest.

Partial source-risk halts also preserve raw/native results and, where readback
succeeds, partial all-results and quarantine views. Integrity failure cannot be
turned into a successful check just to produce a summary.

Every 400 rows and the final boundary produce statistics and a pending reading
list: fixed SHA samples (10 first batch, 3 later batches), fixed representatives
of novel signatures, and quarantines. Reasons are retained and IDs deduplicated.
Every new row stays not_reviewed with a null manual result. Outputs always
article_acceptance=false. No manual PASS, operator approval or newspaper-complete
state is produced. Source semantic contradictions still require actual reading.

Unresolved source gaps, duplicate identities, attribution conflicts and research
judgments belong in the handoff list for Joaquín's further human review. They
must retain their original values and source locations. Kevin is the project
file owner; a Kevin label on earlier assistant review evidence does not mean
that Kevin or Joaquín personally reviewed a page. A pending sample list does
not block collection by itself; only the frozen automatic safety rules do.

## Safe restart and limits

The namespace and plan each have a lock. Legacy worker coordination remains an
operator responsibility; they must not run alongside this worker. Each actual
transport call is reserved durably using a hash-chained ledger and high-watermark,
then linked to pilot attempts and snapshots. Missing/truncated/mismatched state
fails closed. The budget counts transport calls, including uncertain interrupted
reservations; redirects can add HTTP exchanges. No retry is automatic.

At least one second separates calls, checked after sleeping and across resumes.
Nonfinite/backwards clocks and invalid/low disk readings stop collection. A
received response without a complete saved snapshot is ambiguous and halts;
exactly-once network behavior is not promised across that window. Safety halts
are permanent for that plan; investigate and create a new remaining-URL plan.
Completed snapshots can recover without another request. Saved rows and risk
counters are replayed before any new call. Adding manual sidecars to an active
collection batch stops it; actual review belongs to a separate stage.

This bounded implementation rechecks its small ledger on each request. It is
not an unlimited 100,000-URL controller. Offline replay or passing tests alone
does not authorize an actual new plan or prove multi-day unattended throughput.
