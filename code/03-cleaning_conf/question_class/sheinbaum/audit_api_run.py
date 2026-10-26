"""Audit a completed API extraction against source evidence and prior review.

These are integrity/coverage checks, not an exhaustive semantic quality score.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from prepare import DEFAULT_ROOT, atomic_json


def audit(source, run):
    output = run / 'auxiliar'
    d = pd.read_parquet(output / 'periodistas_v2_all_years.parquet')
    e = pd.read_parquet(output / 'journalist_media_evidence.parquet')
    cov = pd.read_csv(output / 'journalist_media_coverage.csv', parse_dates=['date'])
    transcripts = pd.read_parquet(source / 'auxiliar/transcript_rows.parquet').set_index(['date','source_row'])
    manifest = pd.read_csv(source / 'auxiliar/conference_manifest.csv', parse_dates=['date'])
    old = pd.read_parquet(source / 'auxiliar/journalist_media_evidence.parquet')
    old = old[old.date.isin(cov.date)]
    assert not cov.date.duplicated().any()
    assert set(cov.date) <= set(manifest.date)
    assert not d.duplicated(['date','reporter_aux','outlet_aux']).any()
    assert d.no_reporter_flag.eq(d.reporter.isna()).all()
    assert d.no_outlet_flag.eq(d.outlet.isna()).all()
    assert not (d.no_reporter_flag & d.no_outlet_flag).any()
    assert set(d.date) <= set(cov.date)
    for row in e.itertuples():
        ids = [int(n) for n in row.source_rows.split(';')]
        original = '\n'.join(transcripts.loc[(row.date,n),'text'] for n in ids)
        assert original == row.evidence_text
        assert hashlib.sha256(original.encode()).hexdigest() == row.evidence_sha256
    def passages(frame):
        return frame.groupby(['date','source_row'], dropna=False).agg(
            reporter=('reporter','first'),
            outlets=('outlet',lambda s: ' | '.join(s.dropna())),
            evidence_text=('evidence_text','first'), source_rows=('source_rows','first')).reset_index()
    before, after = passages(old), passages(e)
    before_keys = set(zip(before.date,before.source_row))
    after_keys = set(zip(after.date,after.source_row))
    added = after[[key not in before_keys for key in zip(after.date,after.source_row)]]
    missing = before[[key not in after_keys for key in zip(before.date,before.source_row)]]
    # Source anchors can differ when a model joins a multi-row introduction.
    # Mark these cases rather than automatically treating them as omissions.
    after_evidence = set()
    for row in after.itertuples():
        after_evidence.update((row.date,int(n)) for n in str(row.source_rows).split(';'))
    missing = missing.copy()
    missing['anchor_in_api_evidence'] = [(r.date,r.source_row) in after_evidence for r in missing.itertuples()]
    added.to_csv(output / 'introductions_added_vs_review.csv',index=False)
    missing.to_csv(output / 'introductions_missing_vs_review.csv',index=False)
    comparisons = cov.merge(before.groupby('date').size().rename('previous_introduction_passages'),
        on='date',how='left').fillna({'previous_introduction_passages':0})
    comparisons['previous_introduction_passages'] = comparisons.previous_introduction_passages.astype(int)
    comparisons.to_csv(output / 'api_vs_review_coverage.csv',index=False)
    # These are recorded human/assistant inspection notes, not model verdicts.
    # Preserve the raw extraction; expose decisions for the manual R workflow.
    notes = pd.read_csv(Path(__file__).with_name('full_run_review_notes.csv'), parse_dates=['date'])
    flags = []
    for note in notes.itertuples():
        matches = e[(e.date == note.date) & (e.source_row == note.source_row)]
        source_text = transcripts.loc[(note.date, note.source_row), 'text']
        context_rows = transcripts.loc[note.date]
        context = context_rows.loc[
            (context_rows.index >= note.source_row - 2) &
            (context_rows.index <= note.source_row + 2)]
        flags.append({
            'date': note.date, 'source_row': note.source_row,
            'in_api_extraction': not matches.empty,
            'reporter': ' | '.join(matches.reporter.dropna().unique()),
            'outlets': ' | '.join(matches.outlet.dropna().unique()),
            'review_status': note.review_status, 'note': note.note,
            'source_text': source_text,
            'nearby_context': '\n'.join(f'{i} [{r.participant}] {r.text}' for i, r in context.iterrows())})
    pd.DataFrame(flags).to_csv(output / 'full_run_review_flags.csv', index=False)
    usage=[]
    for path in (run / 'checkpoints/journalists').glob('*.json'):
        record=json.loads(path.read_text())
        if record['request']['model'] != 'gpt-6.1-sol':
            raise ValueError('Cost calculation only defined here for gpt-6.1-sol')
        usage.append(record['usage'])
    inputs=sum(u['input_tokens'] for u in usage)
    outputs=sum(u['output_tokens'] for u in usage)
    cached=sum(u['input_tokens_details'].get('cached_tokens',0) for u in usage)
    writes=sum(u['input_tokens_details'].get('cache_write_tokens',0) for u in usage)
    cost=((inputs-cached-writes)*2+cached*.1+writes*2.5+outputs*10)/1e6
    report={'n_source_conferences':len(manifest),'n_run_conferences':len(cov),
        'n_api_processed_conferences':int(cov.status.eq('processed').sum()),
        'n_without_eligible_rows':int(cov.status.eq('no_eligible_rows_not_sent').sum()),
        'n_records':len(d),'n_evidence_records':len(e),'n_identification_passages':len(after),
        'n_outlet_only_records':int(d.no_reporter_flag.sum()),
        'n_named_records_without_outlet':int(d.no_outlet_flag.sum()),
        'n_reporter_name_forms':int(d.reporter_aux.nunique()),'n_outlet_labels':int(d.outlet_aux.nunique()),
        'n_dates_with_identification':int(d.date.nunique()),
        'n_manual_review_flags':len(flags),
        'n_previous_passages':len(before),'n_matching_intro_anchors':len(before_keys & after_keys),
        'n_added_intro_anchors':len(added),'n_missing_intro_anchors':len(missing),
        'n_missing_anchors_present_in_api_evidence':int(missing.anchor_in_api_evidence.sum()),
        'successful_checkpoint_count':len(usage),'input_tokens':inputs,
        'output_tokens_including_reasoning':outputs,'cached_tokens':cached,'cache_write_tokens':writes,
        'estimated_successful_response_cost_usd':round(cost,5),
        'price_source':'https://developers.openai.com/api/docs/models/gpt-6.1-sol',
        'checks':'All stored evidence exactly matches source rows and SHA-256 hashes; daily keys unique; missing-value flags consistent.',
        'limitations':['Anchor differences require review and are not automatically true additions/omissions.',
            'Counts are explicit identifications, not questions or distinct attendees.',
            'Name variants, outlet labels, slogans and parent-group/title groupings need manual harmonization.',
            'Automated evidence checks do not establish semantic accuracy or completeness.',
            'Usage estimate covers successful saved responses, not failed/retried requests or an invoice.']}
    atomic_json(output / 'api_run_audit.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root',type=Path,default=DEFAULT_ROOT)
    parser.add_argument('--run-root',type=Path,default=DEFAULT_ROOT/'api_extraction/full')
    args=parser.parse_args()
    audit(args.input_root,args.run_root)
