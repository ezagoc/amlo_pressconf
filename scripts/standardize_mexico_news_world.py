"""Apply the 2026-10-24 user-approved outlet linkage to reviewed registries.

Only this outlet's records change; source extraction IDs and raw labels remain.
Workbook/data migration is staged separately before replacing live files.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = 'mexico news world'
ALIASES = ['HIDALGO NEWS', 'MEXICO NEWS WORLD', 'MARCO OLVERA OFICIAL',
           'MARCO ANTONIO OLVERA OFICIAL', 'MEXICO NETWORK', 'MEXICONETWORK', 'NEWS WORLD']
SOURCE = 'https://www.gob.mx/presidencia/articulos/version-estenografica-conferencia-de-prensa-de-la-presidenta-claudia-sheinbaum-pardo-del-22-de-octubre-de-2024?idiom=es'
NOTE = ('User approved one analysis outlet on 2026-10-24: Mexico News World / '
        'Marco Olvera Oficial / Hidalgo News. Olvera explicitly names the newspaper '
        'and channel in all 22 in-period introductions; HIDALGO NEWS matches 21 dates. '
        '2025-03-04 has only one attendance-source entry and remains unresolved. '
        'This analytic grouping does not establish legal ownership. Do not merge '
        'The Mexico News (Meme Yamel), Mexico News Daily, Enfasis, or Bajo Palabra.')

for kind in ['attendance', 'question']:
    path = ROOT / f'info_newspapers_gpt/{kind}_aliases_20261016.tsv'
    with path.open(newline='') as handle:
        reader = csv.DictReader(handle, delimiter='\t')
        fields, rows = reader.fieldnames, list(reader)
    for alias in ALIASES:
        matches = [r for r in rows if r['alias'].upper() == alias]
        assert len(matches) <= 1
        row = matches[0] if matches else {'alias': alias}
        row['canonical_id'] = CANONICAL
        if kind == 'attendance':
            row.update(status='reviewed', reason=NOTE, source=SOURCE)
        if not matches:
            rows.append(row)
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fields, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)

for relative in ['info_newspapers_gpt/outlet_expansion_20261016.json',
                 'info_newspapers_gpt/outlet_review_20261016/youtube_extraction_manifest.json']:
    path = ROOT / relative
    payload = json.loads(path.read_text())
    for entry in payload['entries']:
        if entry['id'] not in ['hidalgo news', 'marco olvera oficial', CANONICAL]:
            continue
        entry.update(linkage_id=CANONICAL, question_id=CANONICAL,
                     reviewed_at='2026-10-24', review_note=NOTE)
        entry['aliases'] = ALIASES
        if entry['id'] == 'hidalgo news':
            entry['analysis_merged_into'] = CANONICAL
            # Keep the historic review entry, but never extract its shared
            # channel again as a second outlet.
            entry['youtube_check_status'] = 'merged_alias'
            if 'youtube' in entry:
                entry['youtube']['status'] = 'merged_alias'
        else:
            entry['name'] = 'Mexico News World'
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')

print('Updated exact aliases and review manifests for Mexico News World.')
