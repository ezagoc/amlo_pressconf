# Tiempo: frozen queues and bounded batches

Author: Kevin. This layer does not discover URLs, change the validated pilot's
80-URL cap, merge research data, or certify historical completeness. Each batch
uses the existing `run_pilot`, with separate SQLite, snapshots, exports and
bound manual-review history. No shared crawler files or tracker are outputs.

## Freeze before requesting

Use the Python environment and MEDIA_ROOT described in `TIEMPO_PILOT.md`.
Create a new independent directory below
`MEDIA_ROOT/data/00-newspaper_data/crawler/pilots/`, containing `Kevin_NOTE.md`.
The input CSV requires unique `sample_id,url,expected_year,selection_reason,
expected_kind` columns; extra discovery/baseline metadata is preserved. Each
row must have the correct number of CSV cells. The entire queue is checked for
duplicate IDs and normalized request URLs before any batch is created.
Canonical aliases that cannot be known until extraction remain distinct requests.

```sh
.venv/bin/python code/01-crawlers/scripts/run_tiempo_batches.py freeze \
  --input '/absolute/path/to/frozen_candidate_queue.csv' \
  --run-dir '/absolute/Media/data/00-newspaper_data/crawler/pilots/Kevin/task3-plan' \
  --batch-size 40 --pause-seconds 1 --min-reviewed-per-batch 3
```

This saves the exact source queue, normalized queue, frozen plan/hash, hashes of
the six execution/parser/review source modules, and
`batches/batch_000001/inputs/sample_manifest.csv`, etc. Plan/settings/input changes
require a new independent plan. Changed frozen program files likewise require
restoring the exact version or a new plan; do not mix extraction versions silently.
Initialization writes the plan last; if interrupted
before that commit, preserve the incomplete directory and use a fresh directory.
Freezing does not fetch pages. The default disk reserve is 10 GiB; each network
request checks actual free space again. The pilot's default one-second pause
after each saved response normally satisfies the gap. A persistent request clock
adds only any remaining interval at process/batch transitions or after a safety
halt; there is no routine second pause. Never use concurrency to evade limits.
`transport_calls_started` counts entries into the real/injected transport;
`pilot_fetch_entries` also includes a wrapper entry stopped by low disk before
transport. Neither count is a count of underlying redirect HTTP exchanges.

## Run only a bounded amount

```sh
.venv/bin/python code/01-crawlers/scripts/run_tiempo_batches.py run \
  --run-dir '/absolute/Media/data/00-newspaper_data/crawler/pilots/Kevin/task3-plan' \
  --max-batches 1
```

There is no run-all mode. `max_batches` counts batches executed in this invocation,
not preceding already-completed batches; the hard maximum is 10. It does not bypass
any batch gate, including the first batch. `state.json` separates execution status,
automated counts, manual-review coverage and operator approval. A fetch/extraction
success never creates manual PASS. Every following batch requires an explicit
operator record accepting the prior batch, after automatic checks and at least
the configured number of current bound manual spot checks. The operator may be
the agent carrying out the authorized task, recording Kevin's review; a new user
approval is not inherently required for every batch. Do not manufacture review.

HTTP 403/429/5xx stops after preserving that response/result, before the next URL.
Low free space stops before a request. Unknown layouts, invalid/conflicting or
unverified publication dates, parser exceptions and non-HTML responses stop
immediately after the offending result is saved. Other default quality limits stop at 3 consecutive
system/transport failures or a 25% system-failure fraction after 8 results within
the batch since its last explicit halt resolution. Restarting does not reset
these counters: committed results are rechecked before requesting another URL,
including a crash between the database commit and its safety callback.
`soft_error_page` is classified as `source_gap`: preserved and counted separately,
not included in this system-error fraction. A `missing_title` result is also a
source gap only when the parser records an actually present empty title in the
recognized source template, every title channel is empty, and the remaining
article fields and verified date are intact. The original `missing_title` error
and null title remain; it does not become a success or a manual PASS. Evidence
is stored in `source_title_status` and `source_title_evidence`. Missing/invalid
evidence, other errors and unexplained missing titles remain system quality
failures. Every error group still needs explicit acknowledgement at the operator
gate, and new source-gap types require source-page examination before scale.

## Current evidence and review gate

`status --run-dir ...` reads current states, verifies frozen input, database and
snapshots, and checks export hashes without network or writes. Review selected
saved pages independently and add native `review_annotations.json` using the
schema in `TIEMPO_PILOT.md`. Review can record source gaps; it does not fill missing
news fields. Then run the existing pilot's `--export-only` for that batch so its
four exports contain those annotations. `status` reports `evidence_sha256` for
the current exported data and annotations. Write, only after the checks, e.g.
`approvals/batch_000001.json`:

```json
{
  "format_version": 1,
  "plan_sha256": "<64 lowercase hex from plan.json>",
  "batch_id": "batch_000001",
  "input_sha256": "<batch input hash from plan.json>",
  "evidence_sha256": "<current batch evidence hash from status>",
  "decision": "proceed",
  "reviewer": "Kevin",
  "reviewed_at": "2026-09-26T18:00:00-04:00",
  "reviewed_sample_ids": ["T000001", "T000012", "T000034"],
  "accepted_error_groups": [],
  "note": "Describe spot-check selection, findings and any accepted source gaps."
}
```

Use actual IDs and time, not the example. `accepted_error_groups` must match all
observed groups exactly, e.g. `["source_gap"]`. Every declared checked ID must
have a current bound PASS or PASS_SOURCE_GAP_RECORDED; known FAIL,
REQUIRES_REVIEW or stale annotations block the gate. Unchecked rows remain
`not_reviewed`. The gate documents batch acceptance based on sampling, not a
claim that all articles were manually read. Review more than the minimum for
new layouts, dates/sections or anomalies. The final batch also needs a gate
before the plan can be labeled `all_batches_operator_accepted`.

## Resume and retry groups

Normal resume keeps already-committed results, including errors. It never silently
retries them. An interrupted uncommitted complete response can be reused by the
pilot; a response not completely saved may need another request. A safety halt is
recorded in `halts/<hash>.json`. Before continuing, investigate the reason and
write `resume_authorizations/<hash>.json` with `plan_sha256`, `halt_sha256`,
`decision: "resume"`, `reviewer`, timezone-aware `reviewed_at`, and explanatory
`note`. The resolved result prefix is recorded with its last sample/ordinal and
per-row snapshot/extracted-field hashes; changed resolved evidence stops resume.
This acknowledges resumption only; errors remain errors and require their
own batch acceptance or a separate retry plan. Space is rechecked on resume.

```sh
.venv/bin/python code/01-crawlers/scripts/run_tiempo_batches.py retry-queue \
  --run-dir '/absolute/Media/data/00-newspaper_data/crawler/pilots/Kevin/task3-plan' \
  --group server_error --group transport
```

This writes an immutable selected CSV in `retry_queues/`, with zero requests.
Freeze it into a **new** plan and preserve its parent-plan provenance in the Kevin
note. Available groups: access_denied, rate_limit, server_error, transport,
source_gap, system_quality, http_other. Keep repeated source-deleted/error-shell
URLs in their low-yield queue; don't cycle them automatically. Cross-batch or
baseline canonical deduplication and research-data merging are later audited
work, not implemented here. Summed per-batch article counts are not necessarily
globally unique articles. Discovery completeness, source recovery, total budget
and formal export decisions remain separate task-3 responsibilities.

## APIs and offline tests

`freeze_plan(input_path, run_dir, media_root, **settings) -> plan`,
`run_batches(run_dir, media_root, max_batches=1, fetcher=None, parser=None) -> state`,
`status(run_dir) -> current_summary`, `retry_queue(run_dir, groups) -> CSV_path`.
The optional fetcher/parser injection exists for offline tests; real execution
uses the existing transport/parser. No tests use shared Dropbox data or live sites.

```sh
.venv/bin/python -m unittest discover -s code/01-crawlers/tests -p test_tiempo_batches.py -v
```

Exit 0 means the requested bounded operation returned normally; inspect JSON status.
Exit 3 means awaiting review, safety halt or interruption; exit 2 is an invalid
configuration/evidence error. A clean exit is not a full-archive success claim.
