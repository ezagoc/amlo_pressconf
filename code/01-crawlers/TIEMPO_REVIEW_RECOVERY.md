# Investigated child47 review-format recovery

Author: Kevin

This adapter covers only the October 9, 2026 child47/400 stop whose signed master halt and correction receipts are listed in `crawler_core/tiempo_review_recovery.py`. The donor stays stopped and immutable. This does not authorize resuming future technical stops.

The preserved, unaccepted receipt used the string `none` for TC5_209522's research status. The corrected receipt changes that field to JSON null and adds provenance linking the original. All original notes, source/check hashes, reading IDs, and the separate NEEDS_JOAQUIN_REVIEW item must remain identical. The four existing readings are validated and first sealed into coverage in the successor. Recovery itself adds zero source rereads and no human or article approval.

Preparation validates the original native exports, request ledger, raw response correspondence, exact 400-row prefix, all selected readings, prior completed-child lineage and inherited review obligations before writing. It copies only the current child working state into a new root, closes that saved boundary offline, and writes a formal checkpoint400 gate in the new event chain before any request401. Failure or interruption during preparation leaves the pending namespace blocked; inspect it and preserve its evidence rather than deleting markers or using it as a runnable root.

Run the adapter offline with `python -m crawler_core.tiempo_review_recovery --config <bound JSON config>`. The config explicitly identifies the separate target root, immutable donor root/code, current child/counts, next frozen ID, signed stop hash/event, selection, original and corrected receipt hashes, and all required receipt paths. Production values must match the exact case constants. `synthetic_fixture` is only for generated test data; the campaign refuses real news transport for a synthetic namespace.

After independent verification, use the unchanged `run_tiempo_remaining.py inspect --root <new root>` and the explicitly network-enabled `run --root <new root> --allow-network --resume`. The recovery control root never waives new stops. Keep the original pacing,80-row saves,400-row actual-source gates, remaining request budget and10GiB free-space floor. The first post-recovery80-row save must be checked against the imported400 and the gate-before-request401 event ordering. The old shared tracker and fixed2,670-row package stay unchanged.

For future actual reading receipts, prepare a complete draft outside the live `receipts` directory and use `publish_tiempo_review_receipt.py`. Its existing gate validation runs before exclusive atomic publication; a partial reader contribution may remain pending other mandatory readings, while genuine technical blockers remain visible and stop collection.
