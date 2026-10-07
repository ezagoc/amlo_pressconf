# Tiempo: frozen remaining queue

Kevin authorized the separately validated continuation of the original remaining
84,531 request URLs: original plans 24–66, with 531 URLs in the final plan.
The reconciled starting point is 46,000 saved request URLs and 46,038 charged
transport calls. These are request counts, not accepted or distinct articles.
Completion of this queue does not establish complete Tiempo/year coverage.

The new supervisor reuses the existing parser, source checks, native storage,
one-second minimum spacing, timeout and three-attempt retry policy. It keeps one
collector/writer, saves/checks each 80-URL batch and requires an actual AI source
reading gate every 400 rows and at each child's final boundary. Cross-child
identity history, the latest 79 source-risk records and charged calls carry
forward. Existing campaigns, capsules, raw sources, their halts, earlier
deliverables and the paused automation remain unchanged.

## Local commands

Use these exact locations after the new campaign has been frozen and prepared:

```sh
TIEMPO_PY='/Users/kevinfu/Documents/GitHub/amlo_pressconf/.venv/bin/python'
TIEMPO_REPO='/Users/kevinfu/Documents/GitHub/amlo_pressconf-continuation-20261007'
TIEMPO_RUN='/Users/kevinfu/Library/CloudStorage/Dropbox/Media/data/00-newspaper_data/crawler/pilots/Kevin/Continuations/Remaining_Frozen_20261007'
TIEMPO_CLI="$TIEMPO_REPO/code/01-crawlers/scripts/run_tiempo_remaining.py"
```

Inspect the existing run without making article requests:

```sh
"$TIEMPO_PY" "$TIEMPO_CLI" inspect --root "$TIEMPO_RUN"
```

Add `--full` to recheck the bound predecessor and protected source files.
First authorized launch:

```sh
"$TIEMPO_PY" "$TIEMPO_CLI" run --root "$TIEMPO_RUN" --allow-network
```

Request a normal pause from another terminal:

```sh
"$TIEMPO_PY" "$TIEMPO_CLI" pause --root "$TIEMPO_RUN"
```

The command records intent. Wait for `paused_safe` and the collector to exit
before closing the laptop or disconnecting it. The active logical URL finishes
its existing bounded retries, durable response, native commit and checks; no
next URL starts. Ctrl-C/SIGINT and SIGTERM request this same graceful stop.
An uncertain transport/save window cannot be certified as a normal pause.

Resume a normal pause explicitly:

```sh
"$TIEMPO_PY" "$TIEMPO_CLI" run --root "$TIEMPO_RUN" --allow-network --resume
```

Resume checks the frozen code/input bindings, pause evidence, local request
state, storage and connectivity before continuing. Completed responses and
committed rows are reused. It acknowledges existing pause tokens while keeping
their original files; a newer pause request still stops the run. Do not delete
locks, request tokens, halt files, receipts or checkpoints to force progress.

## Status and review

| Status | Meaning and next action |
| --- | --- |
| `collecting` | The single worker is collecting the frozen queue. |
| `waiting_for_required_AI_review` | The worker waits at a saved checkpoint. The indicated frozen selection needs genuine source-reading receipts; no next URL is fetched meanwhile. |
| `paused_safe` | The pause has balanced transport and committed/checked native evidence. Use explicit `--resume` when ready. |
| `waiting_for_network_not_started` | Connectivity preflight failed; no article request started in that invocation. Restore connectivity, then invoke resume. |
| `resource_pause_low_disk` / `resource_pause_storage_forecast` | The 10 GiB floor or forecast of remaining growth prevents continuation. Resolve storage externally and retry; no automatic deletion occurs. |
| `technical_stop_requires_investigation` | A genuine integrity, source, transport or review block is preserved. Ordinary resume cannot clear it. Investigate and use a separately validated successor if necessary. |
| `frozen_queue_processed_pending_coverage_review` | Every authorized input has a retained outcome. Researcher review and overall coverage assessment remain open. |

`reviews/` contains frozen selections, explicit AI reading receipts and compact
coverage seals. The collector never generates an AI reading attestation. AI
checks/readings do not create human approval, article acceptance or native
manual PASS. Original `not_reviewed` rows and inherited pending obligations stay
visible. A waiting process can continue after valid receipts arrive; a process
that has exited at `paused_safe` requires explicit resume.

## Finder launchers and operating limits

After freeze, the operator will place three small launchers in the new run's
main directory: `Status_Tiempo.command`, `Pause_Tiempo.command` and
`Resume_Tiempo.command`. They should call the exact commands above with quoted
absolute paths, show the resulting state and keep the Terminal result readable.
The pause launcher must distinguish “requested” from confirmed `paused_safe`;
the resume launcher must include both `--allow-network` and `--resume`. These
launchers are convenience controls, not another scheduler or collector.

Offline tests cover request-time pause, retries, partial batches, interrupted
exports, checkpoint/completion recovery and refusal to overwrite suspect
evidence. Actual laptop sleep/wake and real network disconnection have not been
tested. A DNS/TLS preflight does not certify future article responses. Keep the
laptop awake and connected while collecting; pause and confirm the saved state
before an intentional interruption. No additional report bundle, ZIP, copied
old corpus or delivery package is required by this runbook.
