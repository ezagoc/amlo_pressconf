# Kevin: explicit next-batch successor

`scripts/run_tiempo_successor.py` prepares a new isolated successor from a
completed, reviewed bounded capsule. The source capsule, original campaign,
halt, current pointer and earlier published files remain immutable. No shared
scheduler or automatic expansion is enabled.

The configuration explicitly binds `source_capsule`, `source_closure`,
`source_closure_sha256`, `capsule`, `isolated_media`, `new_child`,
`expected_active_saved`, `expected_batch_id`, `expected_sample_ids`, and
`max_additional_transport_calls`. A source closure must have a PASS status,
`native_successor_records`, `no_automatic_expansion: true`, and
`article_acceptance: false`, and bind its actual completed runtime. It may use
`source_binding` with `capsule_file_sha256`, `saved_active_rows`,
`transport_ledger_sha256`, and `native_databases` (path/sha256 entries), or the
first live14 closure's hash-bound `review/Final_Cloud_Review.json` evidence.

```text
python scripts/run_tiempo_successor.py prepare --config /absolute/new_config.json
python scripts/run_tiempo_successor.py inspect --capsule /absolute/new_capsule
```

Both commands are offline. Preparation requires empty, disjoint destinations,
an exact completed original-batch prefix, no donor halt or unfinished attempt,
unchanged source controls and hashes, and the exact next batch's ordered IDs.
The full original child queue and batch inputs are preserved. Native saved
prefix files are copied byte for byte; transport receipts are rebound to the
new frozen plan with explicit original provenance and unchanged charges.
The initial pre-child history index and risk seed are reused, then all saved
active records are replayed once to recover the effective last 79 records.
The last 79 records are not also inserted into the initial seed. Existing
review obligations are embedded with their original hashes; new sampling does
not erase them or establish a new source reading or human approval.
An interrupted or failed preparation is preserved as evidence and is not
adopted automatically. Investigate it and use a separate empty destination;
do not delete or reuse the partial capsule to make its checks pass.

For the authorized successor after the first 14-URL trial: keep the saved 160
rows, target original child 23 batch 3 (`queue[160:240]`), and allow at most 240
new calls including retries. The absolute child cap is 400, with 44,038 prior
completed-child calls plus 160 inherited calls still charged (44,198 initially,
at most 44,438 after this stage). The source bridge's old 188-call cap is not
reused as this newly authorized plan's budget. All original safety thresholds,
timing, disk checks, date/identity/media checks and retry rules remain intact.

Only after explicit authorization for that new bounded stage:

```text
python scripts/run_tiempo_successor.py trial --capsule /absolute/new_capsule --allow-network
```

The entrypoint allows only the frozen next batch and invokes one unfinished
batch. It rejects any initialized later batch, stops at the original boundary,
and makes zero requests when the completed capsule is invoked again. A saved
terminal response interrupted before native commit can be recovered without a
second fetch. An uncertain transport window or a safety halt is not cleared.
Never edit signed fields, raise thresholds, remove halts, or run the general
scheduler on this capsule. Further batches require separate authorization,
reviewed closure evidence, and another independent successor.

Inspectability is not portability: execution still requires the preserved
absolute source paths, original queue and exclusions, history index, registry,
and Python environment. This stage does not infer article acceptance, manual
approval, complete newspaper coverage, or a new title/video transcript.
