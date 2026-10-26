Outlet review — 2026-10-16

Workbooks were updated in Dropbox/data/00-newspaper_data with backups in
backups/2026-10-16-outlet-expansion. Forty rows were appended to each workbook.
Existing metadata row IDs and unrelated workbook contents were preserved.
Source URLs, review notes and missing fields are recorded in verification.reason.

Attendance and questions
  src/reviewed_outlet_linkage.R applies normalized exact aliases AFTER broad legacy
  rules, using original labels. Needs-review attendance labels receive no outlet
  ID and remain in the clean/audit data, outside outlet panels. Roles and n>4
  eligibility are unchanged. Mixed affiliations are not split into extra people.
  Full attendance cleaner ran in memory; production datasets were not rewritten.
  AMLO question code was updated; the AMLO question dataset was not regenerated.
  Asking IDs and attendance IDs may differ; each is stored in the correct field.
  Twenty-eight of forty new outlets have reviewed raw-label matches; twenty-one pass
  n>4. Existing outlet totals can exceed counts in the exact-alias review table.

ComSoc
  Run from repository root:
    Rscript scripts/audit_outlet_expansion.R info_newspapers_gpt/outlet_review_20261016
  Exact normalized legal names and verified RFCs only; no fuzzy auto-linking.
  A trailing 0 on an RFC is explicitly marked as the historical export convention.
  Counts refer to source dataset rows, not unique contracts or advertising value.
  Related-entity and inherited-metadata matches are not confirmed outlet ownership.
  Multiple beneficiaries remain separate crosswalk rows; do not duplicate spending
  when combining outlets that share an entity. No exact match does not mean no ads.

YouTube
  All 72 reviewed records have a status, including unresolved/no-match records.
  Public-page checks resolved 53 channels/candidates; 40 are accepted for extraction.
  22 records have existing saved video data: 20 accepted, 2 related/unresolved.
  Public subscriber/video counts are rounded text. Saved API statistics are older
  snapshots with no guaranteed current accuracy. Observed date coverage is not
  guaranteed completeness. Channel-created dates are not outlet-founded dates.
  The manifest uses a unique outlet record ID; linkage_id retains the attendance
  key and question_id the asking key. Exported channel data includes both.

  Audit saved data:
    Rscript scripts/audit_reviewed_youtube.R
  Dry run (no API requests, no output writes):
    python3 code/06-outcomes/youtube/07-extract_reviewed_outlets.py
  Configure YOUTUBE_API_KEY or YOUTUBE_API_KEYS through the local environment/.env.
  Keys are never logged. No key was configured during this review.
  Fetch channel metadata only:
    python3 code/06-outcomes/youtube/07-extract_reviewed_outlets.py --execute --channels-only
  Fetch up to 10 upload pages per channel, resuming on subsequent runs:
    python3 code/06-outcomes/youtube/07-extract_reviewed_outlets.py --execute --max-pages 10
  --outlet selects an exact record ID from the manifest (repeatable).
  --refresh restarts the scan; --since/--until filter exports, not enumeration.
  --parquet needs pandas and pyarrow. CSV and SQLite require only Python stdlib.
  Default output: MEDIA_ROOT/data/06-outcomes/youtube/reviewed_outlets.
  SQLite commits page data and cursor together, deduplicates by video ID, retains
  unavailable-video status, and stops on quota exhaustion without rotating keys.
  uploads_complete reports whether all pages were traversed. Refresh retains
  historical records; it does not prove an older video is still publicly available.

Checks performed
  Rscript tests/test_reviewed_outlet_linkage.R
  Rscript tests/test_outlet_aliases.R
  python3 tests/test_reviewed_youtube.py
  Full attendance cleaner in memory through final_dedup, stopping before writes.
  Workbook join preserved all previous metadata IDs/order and added 40 records.
  Artifact-authored cells were verified against the originals. Unrelated cells,
  worksheets, formulas and styles were preserved; added rows wrap long labels.

Alias follow-up — 2026-10-16
  Updated 15 existing review records, with no workbook rows appended.
  Workbook follow-up originals: backups/2026-10-16-outlet-alias-followup.
  User confirmed Diario Red and postdata.news. Two frequency-specific Maxima
  labels are corroborated by Jonathan Lozada's own site. Total: 28/40 newly
  added records now have accepted attendance aliases; 21/40 pass n>4.
  Exact question aliases cover The Human/The Humane/The Humanoid, Postdata,
  Revista El Politico and Red de Periodistas de Puerto Vallarta. These changes
  affect the next AMLO cleaner run; production question data was not overwritten.
  affiliation_transcript_evidence.csv stores literal official introductions.
  Sheinbaum dates are taken from source filenames, avoiding the existing
  parquet's timezone display offset. Local source paths are retained where a
  public source URL was not independently opened. It is an evidence table,
  not an expanded attendance dataset; rows must not be counted as attendees.
  El Politico's published legal name produced no exact ComSoc match in the
  2012-2024 dataset. Its Sin Linea affiliation does not transfer all contracts.
  PostData's official website links channel UCHZSNk1Bps8aVlL3pfSu_kw.
  The old revistaposdata.com cultural-magazine channel is explicitly rejected.
  Unknown founding years, legal entities and uncertain aliases remain flagged.
  Follow-up workbook verification: 25 registry cells and 30 metadata cells
  updated; no rows added or reordered. Changed text cells wrap, and the El
  Politico address row was enlarged to fit. Original styles elsewhere and all
  other package parts were preserved. Three pre-existing #NAME? values in
  metadata E12/E13/E15 were left unchanged. Backups and published hashes verified.

Sheinbaum same-date review
  See sheinbaum_date_matches/review.html and its reviewed_date_crosswalk.csv.
  This review uses the fuller 1,995-row official extraction and source HTML,
  with supplemental transcript dates through September 2025. It supersedes
  earlier absence-of-evidence statements based on the smaller extraction.
  No global outlet IDs, workbook identities or production datasets changed.

Postdata confirmation (2026-10-16): user reconfirmed PostData News; five dated
Aguaquemada links are now usable with explicit user-confirmed identity provenance.
Stable ID remains revista posdata. Global attendance aliases are unchanged.

YouTube extraction and older-video backfill — 2026-10-19
  Public metadata collected for all 40 accepted channels. The uploads API scan
  saved 232,195 unique video records. Four large uploads playlists reported only
  20,000 items and ended at 400 pages despite higher channel video counts.
  uploads_complete means pagination ended, NOT full historical coverage;
  inspect coverage_status for api_limit_suspected. This flag remains set after
  supplemental playlist videos are added.

  Initial oldest videos (UTC): Uno TV 2025-03-13; ABC Australia 2025-02-21;
  Canal Universidad de Guadalajara 2025-01-23; Sin Embargo 2023-06-24.
  Adapted the existing curated-playlist approach with page checkpoints,
  verified video ownership, video-ID deduplication, and older-playlist priority.
  Playlist backfill added 9,526 videos: total 241,721. It recovered 5,652 videos
  dated 2021–2022. Oldest recovered dates: Uno TV 2022-01-28; ABC Australia
  2022-04-26; UDG 2021-01-04; Sin Embargo 2020-05-21. These endpoints do not
  establish continuous or exhaustive coverage. All four backfills remain partial.
  The first configured key reached quota; no automatic key rotation occurred.

  Saved under MEDIA_ROOT/data/06-outcomes/youtube/reviewed_outlets:
    youtube_channels.csv / .parquet (40 rows)
    youtube_videos.csv / .parquet (241,721 rows)
    checkpoint.sqlite3 (raw API payloads, upload and curated-playlist cursors)
    youtube_outlet_coverage.csv, playlist_backfill_coverage.csv
    extraction_status.json, playlist_backfill_status.json
    api_limit_diagnostics.json, extraction_manifest.json, README.txt
  Existing historical video datasets were not overwritten or merged.

  Resume curated playlists after quota is available:
    python3 code/06-outcomes/youtube/08-backfill_reviewed_playlists.py --execute
  Omitting --execute is read-only. It selects the four capped channels by
  default; --outlet can select a saved reviewed identity explicitly.
  After extraction, refresh Parquet with the installed R arrow package:
    Rscript scripts/export_reviewed_youtube_parquet.R
  The older 02-getYB_videoinfo_large.py also contains date-window search, but
  it was inspected rather than run: it needs reviewed-channel selection and
  quota-aware adaptation. Its >=30,000-video threshold would miss Sin Embargo.

  Verified: SQLite integrity; unique video IDs; CSV/checkpoint counts; Parquet
  row-count round trips; 7 extractor/backfill unit tests. No API keys printed.
