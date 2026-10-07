# Kevin: bounded continuation of the current child

The separate `scripts/run_tiempo_bounded_stage.py` entry preserves the closed
next80 capsule and every older module. It imports the reviewed 240-row native
prefix, original history seed, review obligations and charged transport ledger
into one new runtime. It does not call the full campaign scheduler.

The explicit configuration binds `source_capsule`, `source_closure`,
`source_closure_sha256`, `capsule`, `isolated_media`, `new_child`,
`expected_active_saved`, `expected_batch_ids`, `expected_sample_ids`,
`checkpoint_saved_rows` and `max_additional_transport_calls`.
For the authorized child23 remainder these are rows241-2000, batches4-25,
1,760 URLs, checkpoints400/800/1200/1600/2000 and at most5,280 new calls.
The imported240 calls remain charged; the absolute child ceiling is5,520,
plus44,038 calls from previous children. The full original child queue stays
bound. The original spacing, retries, quality checks and10GiB disk floor remain.

Use a new empty capsule and a separate empty Media namespace under one shared
principal directory. Existing source directories must not overlap either.
The240 native rows are copied only because recovery and native checks need
them; there is no report bundle or extra history archive.

```text
python scripts/run_tiempo_bounded_stage.py prepare --config /absolute/stage_config.json
python scripts/run_tiempo_bounded_stage.py inspect --capsule /absolute/capsule
python scripts/run_tiempo_bounded_stage.py run-checkpoint --capsule /absolute/capsule --allow-network
```

Prepare and inspect are offline. Each run command stops at the next frozen
checkpoint, saving and checking each original80-row batch along the way.
The caller performs lightweight technical/source checks before invoking the
next segment under the existing user authorization; the adapter does not
create human approval. All saved and unreviewed news stays not_reviewed.
A partial batch resumes to the same checkpoint. A durable terminal response
is adopted without a duplicate fetch. An uncertain transport window or genuine
halt remains stopped; do not clear or alter its evidence. Below10GiB free space,
stop collecting; do not delete old files to make room.

If a crash occurs after the final saved row of a checkpoint but before its
summary or run receipt, inspect reports that same boundary as pending. The
next run invocation only replays saved evidence, closes the checkpoint offline
and returns with zero new fetches. It cannot skip directly to the next segment.
Check the completed boundary before invoking the next authorized segment.
Numbered, signed run receipts are appended without overwriting numbering gaps.

At2,000 saved current-child rows the command is a zero-request no-op. It does
not start child24. Keep the original halt, previous capsules, pointers, fixed
2,670-row package and prior reports unchanged. The light runtime receipts bind
transport counts, database files and checkpoint summaries; they are technical
records rather than article acceptance or full newspaper completion. The code
branch is not merged or deployed merely because it was pushed.
