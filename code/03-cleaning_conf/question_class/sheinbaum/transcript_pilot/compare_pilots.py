"""Compare preserved GitHub and official pilot exports; no model calls."""
import json
from pathlib import Path
import pandas as pd
from pipeline import DEFAULT_ROOT, atomic_json


def compare(base=DEFAULT_ROOT):
    old=base/'transcript_analysis/pilot-10'
    new=base/'transcript_analysis/official-pilot-10'
    columns=['date','source_rows','source_words','president_words',
             'n_other_speaking_officials_provisional','n_questions_and_requests','n_opinions',
             'n_questions_linked_to_president','n_no_response_found']
    a=pd.read_parquet(old/'auxiliar/conference_measures.parquet')[columns]
    b=pd.read_parquet(new/'auxiliar/conference_measures.parquet')[columns]
    merged=a.merge(b,on='date',suffixes=('_github','_official'),validate='one_to_one')
    assert len(merged)==10
    for c in columns[1:]:merged[c+'_change']=merged[c+'_official']-merged[c+'_github']
    merged.to_csv(new/'auxiliar/pilot_before_after.csv',index=False)
    merged.to_parquet(new/'auxiliar/pilot_before_after.parquet',index=False)
    totals=pd.DataFrame([{'measure':c,'github':int(a[c].sum()),'official':int(b[c].sum()),
                         'change':int(b[c].sum()-a[c].sum())} for c in columns[1:]])
    old_ev=pd.read_parquet(base/'api_extraction/full/auxiliar/journalist_media_evidence.parquet')
    old_ev=old_ev[old_ev.date.isin(pd.to_datetime(a.date))]
    new_ev=pd.read_parquet(new/'auxiliar/journalist_media_evidence.parquet')
    identity_counts={
        'github_introduction_passages':len(old_ev[['date','source_row']].drop_duplicates()),
        'official_introduction_passages':len(new_ev[['date','source_row']].drop_duplicates()),
        'github_introduction_outlet_records':len(old_ev),
        'official_introduction_outlet_records':len(new_ev)}
    report={'conference_dates':a.date.tolist(), 'totals':totals.to_dict('records'),
            'identity_counts':identity_counts,
            'interpretation':'Source text changes are deterministic. Changes in model-derived counts can also reflect annotation variability; neither run is a gold standard. Official-source follow-up 2025-03-04:q025 is retained as an opinion with an item-kind review flag.'}
    atomic_json(new/'auxiliar/pilot_before_after.json',report)
    focus=['date','n_questions_and_requests_github','n_questions_and_requests_official',
           'president_words_github','president_words_official',
           'n_other_speaking_officials_provisional_github','n_other_speaking_officials_provisional_official']
    text=['<!doctype html><meta charset="utf-8"><title>Official pilot comparison</title>',
          '<style>body{font:16px/1.5 system-ui;max-width:1250px;margin:40px auto;padding:0 20px}table{border-collapse:collapse;font-size:13px}th,td{border:1px solid #ccc;padding:8px;text-align:left}</style>',
          '<h1>Sheinbaum pilot: official source replacement</h1>',
          '<p>Same ten dates and model. Original GitHub outputs are preserved. The official source restores text and full speaker headings; journalist introductions are freshly extracted.</p>',
          '<p><a href="index.html">Review all questions and answers</a> · <a href="../../../official_source/pilot-10/review/index.html">Inspect source-text differences</a> · <a href="../../pilot-10/review/index.html">Original pilot</a></p>',
          totals.assign(measure=totals.measure.str.replace('_',' ')).to_html(index=False),
          '<h2>By conference</h2>',merged[focus].rename(columns={c:c.replace('_',' ') for c in focus}).to_html(index=False),
          '<h2>Journalist introductions</h2>',pd.DataFrame([identity_counts]).rename(columns={c:c.replace('_',' ') for c in identity_counts}).to_html(index=False),
          '<p>A passage can declare multiple outlets; outlet records are not distinct reporters or questions. Officials are counted within each conference, not deduplicated across dates.</p>',
          '<p>'+report['interpretation']+'</p>',
          '<p>Collection is complete for all 221 dates in the existing subset (October 2, 2024–August 22, 2025). Full collection has 98,154 text rows, including four document-metadata rows; only this ten-date pilot has been reanalyzed by the model. July 14 has an inconsistent internal date header, retained in document_metadata.csv.</p>']
    (new/'review/comparison.html').write_text('\n'.join(text))
    index=new/'review/index.html'
    content=index.read_text()
    if 'comparison.html' not in content:
        content=content.replace('<h1>Sheinbaum transcript pilot</h1>', '<h1>Sheinbaum transcript pilot</h1><p><a href="comparison.html">Compare with the original GitHub pilot</a></p>')
        index.write_text(content)
    print(totals.to_string(index=False))
    print(json.dumps(identity_counts,indent=2))

if __name__=='__main__':compare()
