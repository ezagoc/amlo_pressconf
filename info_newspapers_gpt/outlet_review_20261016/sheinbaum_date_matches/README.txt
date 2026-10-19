Reproduce from repository root:
  Rscript scripts/audit_sheinbaum_outlet_dates.R
  python3 scripts/review_sheinbaum_date_matches.py

Inputs: official-full journalist_media_evidence.parquet; official_source/full
transcript rows plus extension dates through attendance coverage; current
Sheinbaum manual harmonization (read-only); merged attendance XLSX.
The legacy 606-row extraction is not the primary source for this audit.
The official-full evidence file contains 1,995 extraction rows.

Units: raw question evidence rows are not unique questions. Summary counts
distinct outlet/date pairs; the crosswalk deduplicates outlet/date/attendance-row.
attendance_row is the Excel row in attendance_merged_dedup.xlsx including header.
Date and raw label are retained so links can be revalidated if that file changes.
Multiple question outlets may point to one attendance row. Never add these rows
to the attendance table or sum them as people. These are date-specific affiliation
links, not instructions to replace every occurrence of the attendance label.

usable_without_identity_conflict excludes candidate-only and unresolved-conflict
links. The five Postdata links are accepted following user confirmation on
2026-10-16; their matched_user_confirmed_identity status records that provenance. Missing rosters are distinguished from absent matching names. Roles remain
as recorded and the existing eligible-role filter is preserved. Reporter spellings
from official transcripts are kept, including possible Galeazzi transcription errors.
No production datasets, manual deduplication rules or workbook identities changed.
