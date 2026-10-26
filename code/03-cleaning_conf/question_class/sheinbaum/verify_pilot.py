"""Reproduce integrity checks and the assistant's 10-conference pilot audit.

Manual review decisions below apply only to the inspected pilot snapshot.
Raw API outputs/checkpoints remain unchanged. This script makes no API calls.
"""
from pathlib import Path
import hashlib
import html
import json
import pandas as pd
from prepare import DEFAULT_ROOT, atomic_json
from run_models import normalize

root = DEFAULT_ROOT
pilot = root / 'api_extraction/pilot-10'
output = pilot / 'auxiliar'
d = pd.read_parquet(output / 'periodistas_v2_all_years.parquet')
cov = pd.read_csv(output / 'journalist_media_coverage.csv')
transcripts = pd.read_parquet(root / 'auxiliar/transcript_rows.parquet').set_index(['date', 'source_row'])
old = pd.read_parquet(root / 'auxiliar/journalist_media_evidence.parquet')
old = old[old.date.isin(pd.to_datetime(cov.date))]
assert len(cov) == 10 and len(d) == 36, 'Pilot changed: manual review must be repeated.'
assert not d.duplicated(['date', 'reporter_aux', 'outlet_aux']).any()
assert d.no_reporter_flag.eq(d.reporter.isna()).all()
assert d.no_outlet_flag.eq(d.outlet.isna()).all()
assert not (d.no_reporter_flag & d.no_outlet_flag).any()
for row in d.itertuples():
    ids = [int(n) for n in row.source_rows.split(';')]
    evidence = '\n'.join(transcripts.loc[(row.date, n), 'text'] for n in ids)
    assert evidence == row.evidence_text
    assert hashlib.sha256(evidence.encode()).hexdigest() == row.evidence_sha256

# Reviewed all 21 passages / 36 records in this exact pilot on 2026-10-13.
# Preserve model wording and original columns, adding a transparent correction.
reviewed = d.copy()
reviewed['outlet_api'] = reviewed.outlet
reviewed['outlet_aux_api'] = reviewed.outlet_aux
reviewed['review_status'] = 'supported_by_transcript'
reviewed['review_note'] = 'Reviewed explicit self-identification or own affiliation; missing names remain blank.'
fix = (reviewed.date.eq(pd.Timestamp('2025-06-17')) & reviewed.source_row.eq(344) &
       reviewed.outlet.eq('Animales con derechos, uniendo causas, conectando derechos'))
assert fix.sum() == 1
reviewed.loc[fix, 'outlet'] = 'Animales con derechos'
reviewed.loc[fix, 'outlet_aux'] = normalize('Animales con derechos', True)
reviewed.loc[fix, 'review_status'] = 'outlet_label_trimmed_after_review'
reviewed.loc[fix, 'review_note'] = 'Removed trailing slogan: uniendo causas, conectando derechos. API label retained in outlet_api.'
reviewed.to_csv(output / 'journalists_and_media_reviewed.csv', index=False)
reviewed.to_parquet(output / 'journalists_and_media_reviewed.parquet', index=False)

candidates = []
for date, row, status, decision in [
    ('2025-04-07', 219, 'ambiguous_affiliation_not_added',
     'Speaker offers promotion by Telesur but does not explicitly say they work for/represent it. Keep for manual review; no journalist name inferred.'),
    ('2025-08-22', 341, 'same_intervention_repeated_affiliation',
     'Radio Tepoztlan repeats the affiliation in row 340. Not returned as additional evidence by the API; no missing daily affiliation record.'),
    ('2024-10-02', 44, 'correctly_excluded_third_party_or_video',
     'The Guardian is mentioned in historical video narration, not as a journalist affiliation.'),
    ('2025-08-22', 404, 'correctly_excluded_third_party',
     'El publica en La Jornada refers to another person, not the question speaker.')]:
    evidence = transcripts.loc[(pd.Timestamp(date), row), 'text']
    candidates.append({'date': date, 'source_row': row, 'status': status,
                       'decision': decision, 'evidence_text': evidence})
pd.DataFrame(candidates).to_csv(output / 'pilot_review_candidates.csv', index=False)

old_ids = set(zip(old.date, old.source_row))
new_ids = set(zip(d.date, d.source_row))
assert old_ids <= new_ids
assert new_ids - old_ids == {(pd.Timestamp('2024-10-02'), 95)}
usage = [json.loads(f.read_text())['usage'] for f in (pilot / 'checkpoints/journalists').glob('*.json')]
assert len(usage) == 10
inputs = sum(u['input_tokens'] for u in usage)
outputs = sum(u['output_tokens'] for u in usage)
cached = sum(u['input_tokens_details'].get('cached_tokens', 0) for u in usage)
writes = sum(u['input_tokens_details'].get('cache_write_tokens', 0) for u in usage)
# Standard short-context GPT-6.1 Sol rates checked 2026-10-13.
# Cache writes are priced at $2.50/M; ordinary input $2/M; output $10/M.
cost = ((inputs-cached-writes)*2 + cached*.1 + writes*2.5 + outputs*10) / 1e6
report = {
    'review_date': '2026-10-13', 'model': 'gpt-6.1-sol',
    'completed_conferences': len(cov), 'raw_api_records': len(d),
    'introduction_passages_reviewed': len(new_ids), 'outlet_only_records': int(d.no_reporter_flag.sum()),
    'named_records_without_outlet': int(d.no_outlet_flag.sum()),
    'earlier_reviewed_passages': len(old_ids), 'earlier_passages_recovered': len(old_ids & new_ids),
    'new_confirmed_passages': [{'date': '2024-10-02', 'source_row': 95, 'outlet': 'Telemax', 'name': None}],
    'label_corrections': int(fix.sum()), 'ambiguous_affiliations_not_added': 1,
    'input_tokens': inputs, 'output_tokens_including_reasoning': outputs,
    'cache_write_tokens': writes, 'cached_input_tokens': cached,
    'estimated_successful_response_cost_usd': round(cost, 5),
    'price_source': 'https://developers.openai.com/api/docs/models/gpt-6.1-sol',
    'verification_scope': 'Reviewed every returned identification against its full cited text; compared with 20 prior reviewed passages; scanned 696 eligible paragraphs for known media and first-person identity/affiliation cues and inspected candidate context.',
    'limitations': [
        'This is not an exhaustive independently hand-coded gold standard or a general recall/precision estimate.',
        'The 20 prior passages were themselves candidate-based; recovering them does not establish full coverage.',
        'The API omitted a repeated affiliation at 2025-08-22 row 341; row 340 already captures that daily affiliation.',
        'Aliases and parent-group vs title groupings remain to be reviewed.',
        'Cost is an estimate from successful response usage, including cache writes, not a billing invoice or failed-attempt total.',
        'Question counts and attribution to individual speakers were not evaluated.'
    ]}
atomic_json(output / 'pilot_verification_report.json', report)

style = '''body{font:16px/1.5 system-ui,sans-serif;color:#173347;max-width:1200px;margin:40px auto;padding:0 24px}h1,h2{color:#008577}table{border-collapse:collapse;width:100%;font-size:13px;margin:18px 0}td,th{padding:10px;text-align:left;border-bottom:1px solid #d6e4e5;vertical-align:top}th{background:#eaf2f3}p{max-width:950px}.note{background:#eaf2f3;padding:16px}'''
parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>Sheinbaum pilot verification</title>',
         f'<style>{style}</style><body><h1>10-conference pilot: verification</h1>',
         '<p>Reviewed 13 October 2026. Model: GPT-6.1 Sol. API results and checkpoints are preserved separately from the reviewed copy.</p>',
         f'<p class="note"><b>10/10 conferences completed; 36 records; 13 outlet-only records.</b> All 20 previously reviewed introduction passages were recovered, plus Telemax on 2 October 2024. One outlet label was trimmed to remove a slogan. Estimated successful-response cost: <b>${cost:.2f}</b>.</p>',
         '<h2>Coverage</h2>', cov.to_html(index=False, escape=True),
         '<h2>Verification findings</h2>', pd.DataFrame(candidates).to_html(index=False, escape=True),
         '<h2>Scope and limitations</h2>', f'<p>{html.escape(report["verification_scope"])}</p><ul>',
         *[f'<li>{html.escape(s)}</li>' for s in report['limitations']], '</ul>',
         '<h2>Reviewed records and exact evidence</h2>',
         reviewed[['date','reporter','outlet_api','outlet','source_rows','review_status','evidence_text']].fillna('').to_html(index=False,escape=True),
         '<p>Source: NOSTRODATA/conferencias_matutinas_sheinbaum; CC BY-SA 4.0. Full source references and evidence hashes are retained in the data.</p></body></html>']
(output / 'pilot_verification.html').write_text('\n'.join(parts), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
