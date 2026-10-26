"""Read exported pilot, check evidence/counts, and write a compact audit. No API calls."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from pipeline import DEFAULT_ROOT, OFFICIALS, spoken_text, atomic_json


def audit(root, source):
    out=root/'auxiliar'
    official=(source/'manifest.json').exists() and 'official_source' in str(source)
    load=lambda name:pd.read_parquet(out/f'{name}.parquet')
    t,s,q,r,l,m,a=[load(name) for name in ['speaking_turns','speaker_registry','questions','responses',
        'question_response_links','conference_measures','adjacent_response_turns']]
    raw=pd.read_parquet(source/'auxiliar/transcript_rows.parquet').set_index(['date','source_row'])
    for frame,key in [(t,'turn_id'),(s,'speaker_id'),(q,'question_id'),(r,'response_id')]:
        assert not frame[key].duplicated().any(), f'Duplicate {key}'
    assert not l.duplicated(['question_id','response_id']).any()
    assert set(l.question_id)<=set(q.question_id) and set(l.response_id)<=set(r.response_id)
    assert set(a.question_id)<=set(q.question_id) and set(a.turn_id)<=set(t.turn_id)
    for record in q.itertuples():
        parts=[]
        for span in json.loads(record.spans_json):
            full=raw.loc[(pd.Timestamp(record.date),span['row']),'text']
            text=full[span['char_start']:span['char_end']]
            assert text==span['quote'];parts.append(text)
        text='\n'.join(parts)
        assert text==record.text and hashlib.sha256(text.encode()).hexdigest()==record.text_sha256
    for frame in [t,r]:
        for record in frame.itertuples():
            texts=[raw.loc[(pd.Timestamp(record.date),i),'text'] for i in range(record.start,record.end+1)]
            text='\n'.join(texts)
            assert text==record.text and hashlib.sha256(text.encode()).hexdigest()==record.text_sha256
            assert sum(0 if raw.loc[(pd.Timestamp(record.date),i)].get('row_kind')=='document_metadata'
                       else len(spoken_text(raw.loc[(pd.Timestamp(record.date),i),'text']).split())
                       for i in range(record.start,record.end+1))==record.word_count
    for record in m.itertuples():
        turns=t[t.date==record.date]
        covered=[i for x in turns.itertuples() for i in range(x.start,x.end+1)]
        assert covered==raw.loc[pd.Timestamp(record.date)].index.tolist()
        assert record.live_words+record.recorded_words+record.unresolved_delivery_words==record.transcribed_speech_words
        assert record.source_words-record.stage_direction_words_excluded==record.transcribed_speech_words
        live=s[(s.date==record.date)&(s.live_words>0)]
        assert len(live[live.role.isin(OFFICIALS)])==record.n_other_speaking_officials_provisional
        assert live[live.role=='president'].live_words.sum()==record.president_words
        assert len(q[(q.date==record.date)&q.kind.ne('opinion')])==record.n_questions_and_requests
    flags=load('review_flags')
    # Deterministic spot-check list, not an independent gold-standard evaluation.
    sample=[]
    for date,group in q.groupby('date'):
        for n in sorted({1,len(group)//2+1,len(group)}):
            x=group[group.item_number==n].iloc[0]
            sample.append({'date':date,'question_id':x.question_id,'selection':'first/middle/last',
                'kind':x.kind,'text':x.text,'link_status':x.link_status,
                'review_scope':'Selected for assistant inspection; selection alone does not establish semantic correctness.'})
    pd.DataFrame(sample).to_csv(out/'assistant_spotcheck_sample.csv',index=False)
    review_path=out/'assistant_semantic_review.csv'
    reviewed=pd.read_csv(review_path) if review_path.exists() else pd.DataFrame()
    if len(reviewed):
        assert reviewed.question_id.is_unique
        hashes=q.set_index('question_id').text_sha256.to_dict()
        assert all(hashes.get(x.question_id)==x.question_text_sha256 for x in reviewed.itertuples()), 'Stale semantic-review record'
    report={
        'n_conferences':len(m),'n_source_rows':int(m.source_rows.sum()),
        'n_questions_and_requests':int(m.n_questions_and_requests.sum()),
        'n_opinions':int(m.n_opinions.sum()),'n_followups':int(m.n_followups.sum()),
        'n_questions_thematically_linked_to_president':int(m.n_questions_linked_to_president.sum()),
        'n_questions_followed_by_presidential_turn':int(m.n_questions_followed_by_presidential_turn.sum()),
        'n_no_thematic_response_found':int(m.n_no_response_found.sum()),
        'n_uncertain_links':int(m.n_uncertain_links.sum()),'presidential_words':int(m.president_words.sum()),
        'n_conferences_without_presidential_speech_in_source':int((~m.president_observed_speaking).sum()),
        'n_review_flags':len(flags),'review_flag_categories':flags.category.value_counts().to_dict(),
        'n_spotcheck_items':len(sample),
        'n_assistant_semantic_excerpt_checks':len(reviewed),
        'n_official_source_registry_corrections':int(s.get('review_status',pd.Series(dtype=str)).eq('assistant_verified_official_transcript').sum()),
        'automated_checks':'PASS: exact question character spans; source text and hashes; turn coverage; word partitions; table keys/links; official-speaker and presidential totals.',
        'interpretation':('Provisional model-assisted pilot on archived official HTML. No video completeness audit or gold-standard accuracy estimate is available.' if official else 'Provisional model-assisted pilot. Source omissions and speaker-label errors prevent exhaustive event-level counts; no gold-standard accuracy estimate is available.')}
    atomic_json(out/'pilot_audit.json',report)
    print(json.dumps(report,indent=2,ensure_ascii=False))
    print(m[['date','president_words','n_other_speaking_officials_provisional','n_questions_and_requests',
        'n_questions_linked_to_president']].to_string(index=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=DEFAULT_ROOT)
    parser.add_argument('--root',type=Path,default=DEFAULT_ROOT/'transcript_analysis/pilot-10')
    parser.add_argument('--official',action='store_true')
    args=parser.parse_args()
    if args.official:
        if args.source==DEFAULT_ROOT:args.source=DEFAULT_ROOT/'official_source/pilot-10'
        if args.root==DEFAULT_ROOT/'transcript_analysis/pilot-10':args.root=DEFAULT_ROOT/'transcript_analysis/official-pilot-10'
    audit(args.root,args.source)
