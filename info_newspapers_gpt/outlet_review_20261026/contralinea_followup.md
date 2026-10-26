# Contralínea source reconciliation — October 26, 2026

The participation flag concerns **January 7, 2025**. Nancy Flores identifies
herself as Contralínea in the official transcript, but Contralínea is absent
from the original official attendance roster for that date. No name-cleaning
or import correction resolves this discrepancy.

## Independent source checks

- Scanned the original 2024 and January–September 2025 attendance PDFs, not
  only the cleaned panel. In the October 2024–September 2025 window they contain
  43 Contralínea rows on **40 distinct dates**. The date set exactly matches
  the merged attendance input. Three dates have repeated entries: August 5,
  August 12, and August 19, 2025; these do not add distinct attendance dates.
- Inspected pages 4–5 of the 2025 PDF visually. January 7 occupies numbered
  records 183–243: 50 reporter rows plus 11 photographer rows. There is no
  Contralínea entry. The merged input has the same 50 reporter rows and nine
  distinct photographer rows; the two duplicate photographer entries do not
  affect the reporter-based analysis or the Contralínea finding.
- The original XLSX also has no Contralínea on January 7. Contralínea is listed
  on January 6; the saved January 6 transcript contains no Nancy Flores or
  Contralínea mention. This does not establish that either date should be moved.
- The archived official January 7 HTML has the matching date in its title.
  Parsed source row 230 is: “Buenos días a todas y a todos. Nancy Flores, de la
  revista Contralínea.” Her subsequent question concerns security and customs.

Official transcript:
https://www.gob.mx/presidencia/articulos/version-estenografica-conferencia-de-prensa-de-la-presidenta-claudia-sheinbaum-pardo-del-7-de-enero-de-2025?idiom=es

Source files under `MEDIA_ROOT/data/02-conferences/raw/attendance/`:

- `LISTADO_DE_ASISTENCIA_DE_MEDIOS_ENERO-DICIEMBRE_2024_30-10-2025_19-08-51.PDF`
- `LISTADO_DE_ASISTENCIA_DE_MEDIOS_ENERO-SEPTIEMBRE_2025_30-10-2025_19-09-03.PDF`
- The corresponding 2025 `.xlsx`, plus `merged/attendance_merged_dedup.xlsx`.

## Counts and disposition

Within the common coverage sample, Contralínea has 40 recorded attendance
dates and 33 transcript-identification dates: 32 overlap, one is transcript-only
(January 7), and eight are attendance-only. Across all 503 transcripts it has
72 identified dates, including 39 after attendance coverage ends.

Retain the official recorded attendance count of 40 and preserve January 7 as
an explicit transcript/roster discrepancy. No new alias or global outlet merge
is supported, and no attendance row was added or moved. The current 32/40 rate
continues to mean identified participation conditional on recorded attendance;
it does not include the unmatched January 7 identification in its numerator.
