"""Prepare changes to the existing review workbook; authoring is done in JS."""
import json,csv
from pathlib import Path
from openpyxl import load_workbook
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/flagged-outlets-20261026'
rows=json.loads((OUT/'review_results.json').read_text())
patches=json.loads((OUT/'workbook_patches.json').read_text())
book=load_workbook(ROOT/'recovery/flagged-outlets-20261026/sheinbaum_outlet_attendance_review.xlsx')
edits={s.title:[] for s in book}
def put(s,r,c,v):edits[s].append([r,c,v])
for r in rows:
 if r.get('attendance_row'):
  n=r['attendance_row'];s='Attendance check'
  for c,v in enumerate([r['in_period'],r['recorded_attendance_dates'],r['matches'],len(r['unmatched']),r['after_coverage'],'; '.join(r['attendance_labels']),'; '.join(r['unmatched']),r['canonical_id'],r['status'],'; '.join(r['coverage_gaps']),r['note']],2):put(s,n,c,v)
 if r.get('roster_row'):
  n=r['roster_row'];s='Outlet review'
  roster='Existing entry / alias' if r['metadata_names'] else 'Added to source roster'
  vals={1:r['outlet'],2:r['transcript_dates'],3:roster,4:r['recorded_attendance_dates'],5:r['all_attendance_dates'],6:r['status'],8:'; '.join(r['attendance_labels']),10:r['note'],11:'; '.join(r['reporters']),12:r['first_date'],13:r['last_date'],14:r['in_period']-len(r['coverage_gaps']),15:r['matches'],16:'Yes',17:r['canonical_id'],18:'; '.join(r['coverage_gaps'])}
  for c,v in vals.items():put(s,n,c,v)
# Refresh the five focus rows as well as their copies in the flagged section.
for n in range(9,14):
 outlet=book['Attendance check'].cell(n,1).value
 found=next((r for r in rows if r['outlet']==outlet),None)
 if found:
  r=found
  for c,v in enumerate([r['in_period'],r['recorded_attendance_dates'],r['matches'],len(r['unmatched']),r['after_coverage'],'; '.join(r['attendance_labels']),'; '.join(r['unmatched']),r['canonical_id'],r['status'],'; '.join(r['coverage_gaps']),r['note']],2):put('Attendance check',n,c,v)
 else:
  for c,v in enumerate([outlet,'Resolved',None,'Earlier verified exact attendance labels retained; see raw labels in column G.'],9):put('Attendance check',n,c,v)
for n in [8,21]:
 for c,v in enumerate(['Conference ID','Review status','Missing / sparse roster dates','Review decision and remaining issues'],9):put('Attendance check',n,c,v)
put('Attendance check',3,1,'Comparison: October 1, 2024–September 30, 2025. Counts are distinct dates per conference ID; rows sharing an ID must not be summed.')
put('Attendance check',4,1,'Later transcripts are outside attendance coverage. Dated affiliation links use actual roster rows; no physical attendance rows are added.')
put('Attendance check',5,1,'Updated October 26, 2026: approved identity groups, exact spelling fixes and source metadata entries applied. Panels remain unchanged.')
put('Attendance check',6,1,'Evidence: preserved Introductions tab plus reviewed_question_dates.csv and dated_question_attendance_links.csv in outputs/flagged-outlets-20261026.')
put('Attendance check',16,1,'* Unmatched means no verified label in a usable roster. Missing or sparse rosters are shown separately. Neither establishes absence.')
put('Attendance check',18,1,'Flagged cases — decisions and remaining date checks')
put('Attendance check',19,1,'Original flagged rows retained for traceability. See Conference ID before combining records. Date-specific links do not globally merge brands.')
put('Outlet review',8,17,'Conference ID');put('Outlet review',8,18,'Missing / sparse roster dates')
put('Outlet review',5,1,'Updated October 26, 2026. Flagged rows use current conference IDs; do not sum rows sharing an ID. Ownership fields remain unverified where indicated.')
# The original introductions remain unchanged. Every edited cell is explicitly listed.
patches['sheinbaum_outlet_attendance_review.xlsx']={'sheets':{s:{'edits':v} for s,v in edits.items()}}
(OUT/'workbook_patches.json').write_text(json.dumps(patches,ensure_ascii=False,indent=2)+'\n')
print('Review workbook:',{s:len(v) for s,v in edits.items()})
