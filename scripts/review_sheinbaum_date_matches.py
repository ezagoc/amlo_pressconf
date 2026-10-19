"""Review same-date outlet evidence; never expand the physical attendance data.

Run after audit_sheinbaum_outlet_dates.R. The rules below are deliberately scoped
to this audit's identified question dates, not global outlet-name substitutions.
"""
import csv
import html
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'info_newspapers_gpt/outlet_review_20261016/sheinbaum_date_matches'

def read(name):
    with (OUT / name).open() as f:
        return list(csv.DictReader(f))

def write(name, rows, fields=None):
    with (OUT / name).open('w') as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()

events = read('question_date_evidence.csv')
rosters = read('full_same_day_attendance.csv')
by_event = defaultdict(list)
for r in rosters:
    if r['attendance_row']:
        by_event[r['event_id']].append(r)

# Exact roster labels corroborated by the stated affiliation on that date.
patterns = {
    'animales con derechos': r'^noticias del movimiento consciencia',
    'ecosfera': r'^cultura colectiva$',
    'grupo tribu': r'^cultura colectiva$',
    'el politico en las redes': r'^sin linea mx$',
    'empuje migrante': r'^oro solido$',
    'enlace mesoamerica': r'^diario plaza juarez$',
    'la pancarta de quintana roo': r'^la pancarta de quintana roo y saber p$',
    'maxima fm': r'^maxima fm cuarto poder$',
    'red periodistica de puerto vallarta': r'^radio universidad de guadalajara en p',
    'revista posdata': r'^aguaquemada$',
    'rotativo de queretaro': r'^meganoticias queretaro$',
    'the human hoy': r'^el centinela informa$',
    'tiempo y espacio': r'^canal 10$',
}
notes = {
    'animales con derechos': 'Elideth Fernandez explicitly names Movimiento Consciencia and Animales con Derechos together. This is a dated co-affiliation, not common ownership.',
    'ecosfera': 'Cristian Galarza names Cultura Colectiva, Ecosfera and El Fildeo / Grupo Tribu together. ECOS MEDIA MX is a different simultaneous roster label and is not selected.',
    'grupo tribu': 'Cristian Galarza names Cultura Colectiva, Ecosfera and El Fildeo / Grupo Tribu together. TRIBU POLITICA is not established as an alias.',
    'el politico en las redes': 'The introduction names Sin Linea and El Politico together. Reporter-name transcription variants are preserved as written.',
    'empuje migrante': 'Nancy Rodriguez explicitly names Oro Solido and Empuje Migrante together.',
    'enlace mesoamerica': 'Saul Santana Hernandez uses Enlace Mesoamerica on 2025-06-04 and Enlace Mexamerica on 2025-08-11, both with Plaza Juarez; Alejandro Aleman uses Enlace Mexamerica with the same newspaper. This supports a transcription variant, not a merger with Plaza Juarez.',
    'la pancarta de quintana roo': 'Diana Garcia names La Pancarta; its name occurs explicitly in the combined roster label with Saber P.',
    'maxima fm': 'Jonathan/Jhonatan Lozada identifies Maxima FM of Chiapas; roster consistently uses MAXIMA FM/ CUARTO PODER. Keep the combined physical attendance record intact.',
    'red periodistica de puerto vallarta': 'The introduction names Radio Universidad de Guadalajara, Puerto Vallarta and the network together. INTERMEDIA CANAL 44 is not the UDG station and is not selected.',
    'revista posdata': 'User reconfirmed Posdata as PostData News (postdata.news) on 2026-10-16 after the identity conflict was presented. The speaker names Agua Quemada together with Revista Posdata/Postdata.com. Accept the same-date Aguaquemada co-affiliation under stable ID revista posdata; preserve the literal transcript wording. Identity is user-confirmed, not independently established by this roster.',
    'rotativo de queretaro': 'Thelma Herrera explicitly names Meganoticias Queretaro and El Rotativo de Queretaro together.',
    'the human hoy': 'Ramon Flores explicitly names El Centinela Informa and The Human Hoy together.',
    'tiempo y espacio': 'Zujey Luna introduces herself as a reporter from Durango. The existing rule assigns Tiempo y Espacio; Canal 10 lists her as its Tiempo y Espacio presenter. This supports the date-specific CANAL 10 match, not every CANAL 10 record.',
}
program_source = 'https://canal10.com.mx/sitio/zujey-luna/'
review = []
links = []
for e in events:
    e = dict(e)
    outlet, date = e['outlet_id'], e['event_date']
    rows = by_event[e['event_id']]
    e['review_status'] = 'unmatched'
    e['matched_attendance_labels'] = ''
    e['matched_attendance_rows'] = ''
    e['additional_source'] = ''
    e['review_reason'] = notes.get(outlet, '')
    # Exclude a postscript and a third-party citation, which literal search found.
    if (outlet, date) in {('revista posdata', '2025-04-11'), ('diario red latinoamerica', '2025-06-18')}:
        e['review_status'] = 'not_outlet_identification'
        e['review_reason'] = ('Posdata means the postscript of a letter here, not a publication.'
                              if outlet == 'revista posdata' else
                              'A question cites an article by Diario Red; it does not identify the speaker as representing Diario Red.')
        review.append(e)
        continue
    pattern = patterns.get(outlet)
    if outlet == 'diario red latinoamerica':
        pattern = r'^diario red piedepagina mx$' if date == '2024-10-03' else r'^luces del siglo$'
        e['review_reason'] = ('Daniela Pastrana names Pie de Pagina and Diario Red; both names occur in the combined roster label. This predates the Latin America edition launch.'
                              if date == '2024-10-03' else
                              'Zosimo Camacho introduces Luces del Siglo at source row 186, then says "En Diario Red tuvimos" at row 189 in the same uninterrupted question. Match Luces del Siglo, not Pie de Pagina merely present on that date.')
        if date == '2025-03-17':
            assert 'Zósimo Camacho' in e['context']
            e['reporter'] = 'zosimo camacho (introduction at source row 186)'
    if outlet == 'asi lo dice la mont':
        pattern = r'^abc radio 760 am$'
        e['review_reason'] = 'ABC RADIO 760 AM is present on all four question dates; EL SOL DE MEXICO on two. These are candidates only: no reporter name exists in attendance, and the 2025-05-30 introduction says 1530. A historical ABC association does not prove current roster identity.'
    hits = [r for r in rows if pattern and re.search(pattern, norm(r['medios'])) and r['eligible_role'] == 'TRUE']
    if hits:
        status = 'matched_stated_affiliation'
        if outlet == 'asi lo dice la mont':
            status = 'candidate_only'
        elif outlet == 'revista posdata':
            status = 'matched_user_confirmed_identity'
        elif outlet == 'tiempo y espacio':
            status = 'matched_reporter_program'
            e['additional_source'] = program_source
        elif outlet == 'maxima fm' and date == '2025-06-02':
            status = 'matched_repeated_reporter_affiliation'
            e['review_reason'] += ' On this date the introduction gives only the reporter and Chiapas; the existing reporter rule and repeated explicit introductions support the association.'
        e['review_status'] = status
        e['matched_attendance_labels'] = ' | '.join(dict.fromkeys(r['medios'] for r in hits))
        e['matched_attendance_rows'] = ' | '.join(r['attendance_row'] for r in hits)
        for r in hits:
            links.append({'question_outlet_id': outlet, 'event_date': date,
                          'attendance_row': r['attendance_row'], 'attendance_label': r['medios'],
                          'role': r['cargo'], 'status': status,
                          'usable_without_identity_conflict': str(status.startswith('matched_') and status != 'matched_label_with_identity_conflict').lower(),
                          'question_event_ids': e['event_id'], 'reporter_as_transcribed': e['reporter'],
                          'evidence_text': e['evidence_text'], 'question_source_url': e['source_url'],
                          'question_source_path': e['source_path'], 'attendance_source_file': r['source_file'],
                          'reason': e['review_reason'], 'additional_source': e['additional_source']})
    elif not rows:
        e['review_status'] = 'no_attendance_roster_for_date'
        e['review_reason'] += ' No rows for this date in merged attendance; the original 2024 workbook was checked as well.'
    elif len(rows) == 1:
        e['review_status'] = 'roster_coverage_gap'
        e['review_reason'] += ' Only ADN 40 appears for 2025-03-04 in both the merged dataset and original 2025 workbook; the roster is too sparse for this match.'
    else:
        e['review_status'] = 'no_corresponding_attendance_label'
        e['review_reason'] += ' No supported counterpart found in the full same-day roster.'
    review.append(e)

# The bridge may associate several outlets with one observed attendance row.
# It must never be summed to count attendees, and never applied on other dates.
dedup = {}
for row in links:
    k = (row['question_outlet_id'], row['event_date'], row['attendance_row'])
    if k in dedup:
        old = dedup[k]
        old['question_event_ids'] += ' | ' + row['question_event_ids']
        old['evidence_text'] += '\n' + row['evidence_text']
    else:
        dedup[k] = row
links = list(dedup.values())
write('reviewed_question_dates.csv', review)
write('reviewed_date_crosswalk.csv', links)

summary = []
names = {e['id']: e['name'] for e in json.loads((ROOT/'info_newspapers_gpt/outlet_expansion_20261016.json').read_text())['entries']}
for id in dict.fromkeys(r['outlet_id'] for r in read('coverage.csv')):
    es = [r for r in review if r['outlet_id'] == id and r['review_status'] != 'not_outlet_identification']
    ls = [r for r in links if r['question_outlet_id'] == id]
    usable = {r['event_date'] for r in ls if r['usable_without_identity_conflict'] == 'true'}
    summary.append({'outlet': names[id], 'outlet_id': id,
                    'question_dates_reviewed': len({r['event_date'] for r in es}),
                    'supported_match_dates': len(usable),
                    'identity_conflict_dates': len({r['event_date'] for r in ls if r['status']=='matched_label_with_identity_conflict'}),
                    'candidate_only_dates': len({r['event_date'] for r in ls if r['status']=='candidate_only'}),
                    'attendance_labels': ' | '.join(dict.fromkeys(r['attendance_label'] for r in ls)),
                    'dates': ' | '.join(sorted({r['event_date'] for r in es}))})
write('reviewed_summary.csv', summary)

# Verify all published bridge rows refer to actual, same-day eligible records.
raw_keys = {(r['event_date'], r['attendance_row'], r['medios']) for r in rosters if r['eligible_role']=='TRUE'}
assert all((r['event_date'],r['attendance_row'],r['attendance_label']) in raw_keys for r in links)
assert len(links) == len({(r['question_outlet_id'],r['event_date'],r['attendance_row']) for r in links})
assert all(r['attendance_label']!='ECOS MEDIA MX' for r in links if r['question_outlet_id']=='ecosfera')
assert all(r['attendance_label']!='INTERMEDIA CANAL 44' for r in links if r['question_outlet_id']=='red periodistica de puerto vallarta')
posdata_links = [r for r in links if r['question_outlet_id']=='revista posdata']
assert len(posdata_links) == 5
assert all(r['status']=='matched_user_confirmed_identity' and r['usable_without_identity_conflict']=='true' for r in posdata_links)

esc = lambda x: html.escape(str(x or ''))
summary_html = ''.join('<tr>'+''.join(f'<td>{esc(r[k])}</td>' for k in ['outlet','question_dates_reviewed','supported_match_dates','identity_conflict_dates','candidate_only_dates','attendance_labels'])+'</tr>' for r in summary)
detail = []
for r in review:
    labels = sorted({x['medios'] + (' [role excluded]' if x['eligible_role']!='TRUE' else '') for x in by_event[r['event_id']]})
    detail.append(f'''<tr><td>{esc(names[r['outlet_id']])}<br>{esc(r['event_date'])}</td><td>{esc(r['reporter'] or 'Not stated in this evidence row')}<br><small>{esc(r['selection_basis'])}</small></td><td>{esc(r['matched_attendance_labels'] or '—')}<br><b>{esc(r['review_status'].replace('_',' '))}</b></td><td>{esc(r['review_reason'])}<details><summary>Question evidence and full roster ({len(labels)} labels)</summary><p>{esc(r['evidence_text'])}</p><a href="{esc(r['source_url'])}">Official transcript</a><p>{esc(' | '.join(labels))}</p><small>Source row {esc(r['source_row'])}; attendance workbook rows {esc(r['matched_attendance_rows'])}.</small></details></td></tr>''')
inputs = json.loads((OUT/'audit_inputs.json').read_text())
page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Sheinbaum question dates and attendance</title><style>
body{{font:15px/1.5 system-ui;max-width:1450px;margin:30px auto;padding:0 24px;color:#193644}}table{{border-collapse:collapse;width:100%;margin:20px 0}}td,th{{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #ccd8dd}}th{{background:#173e50;color:white}}small{{color:#536976}}a{{color:#096f88}}details{{margin-top:10px}}input{{padding:10px;width:350px}}.note{{padding:15px;background:#fff1cf}}summary{{cursor:pointer}}h1{{font-size:28px}}
</style><h1>Sheinbaum question dates × attendance records</h1>
<p>Checked all 15 requested identities using the fuller official extraction, existing Sheinbaum harmonization rules and original transcripts through {esc(inputs['question_max'])}, the end of attendance coverage. Later transcripts exist but have no attendance data to compare. Conference dates come from source filenames, checked against UTC dates.</p>
<p>The attendance files do not contain reporter names. A supported match connects the outlet named in a question with a corresponding roster label on that date. Shared affiliations are preserved; this bridge does not establish that different brands are identical and must not be summed as an attendee count.</p>
<p class="note"><b>Postdata identity confirmed by user (2026-10-16):</b> the five Revista Posdata/Postdata.com introductions are assigned to PostData News (postdata.news), with date-specific Aguaquemada roster links. The original transcript wording is preserved. This identity decision relies on user confirmation; the roster establishes the dated co-affiliation. Así lo dice La Mont → ABC Radio remains a candidate, despite appearing on all four dates.</p>
<p><a href="reviewed_date_crosswalk.csv">Date-specific crosswalk</a> · <a href="reviewed_question_dates.csv">Every reviewed question row</a> · <a href="full_same_day_attendance.csv">Full same-day attendance</a> · <a href="reviewed_summary.csv">Summary</a></p>
<table><thead><tr><th>Outlet</th><th>Question dates</th><th>Supported dates</th><th>Identity conflict</th><th>Candidate only</th><th>Roster names</th></tr></thead><tbody>{summary_html}</tbody></table>
<p>Two literal-search hits were rejected: a letter's “Posdata” (2025-04-11) and a third-party Diario Red citation (2025-06-18). November 4, 2024 has no roster; March 4, 2025 has only one row. Both gaps were checked against the original attendance workbooks.</p>
<label>Filter details <input id="filter" placeholder="Outlet, date, reporter or status"></label>
<table id="detail"><thead><tr><th>Outlet / date</th><th>Reporter</th><th>Attendance counterpart</th><th>Decision and evidence</th></tr></thead><tbody>{''.join(detail)}</tbody></table>
<script>document.querySelector('#filter').addEventListener('input',e=>{{for(const r of document.querySelectorAll('#detail tbody tr'))r.hidden=!r.textContent.toLowerCase().includes(e.target.value.toLowerCase())}})</script></html>'''
(OUT/'review.html').write_text(page)
(OUT/'README.txt').write_text('''Reproduce from repository root:
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
''')
for r in summary:
    print(f"{r['outlet']}: {r['supported_match_dates']}/{r['question_dates_reviewed']} supported; conflict {r['identity_conflict_dates']}; candidate {r['candidate_only_dates']}; {r['attendance_labels']}")
print(f'Validated {len(links)} dated links; report: {OUT / "review.html"}')
