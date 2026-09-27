"""Offline queue-policy, read-only integration and sampling regressions."""
import csv
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from crawler_core import tiempo_queue as q
from crawler_core import tiempo_discovery as discovery
from crawler_core import tiempo_pilot as pilot
from crawler_core.tiempo_review import fields_digest


def candidate(url='https://www.tiempo.com.mx/local/new-story/', day='2025-03-02'):
    return {'url':url,'url_key':q.normalize_url(url),'candidate_id':1,'url_issue':None,
            'discovery_day':day,'discovery_date_status':'consistent',
            'discovery_scope':q.discovery_scope(day),'queue_class':'new_urls'}


class QueuePolicyTests(unittest.TestCase):
    def test_light_identity_keeps_case_query_and_route(self):
        a=q.normalize_url('http://www.tiempo.com.mx/noticia/Abc/#fragment')
        self.assertEqual(a,'https://tiempo.com.mx/noticia/Abc')
        self.assertNotEqual(a,q.normalize_url('https://tiempo.com.mx/noticia/abc/'))
        self.assertNotEqual(a,q.normalize_url('https://tiempo.com.mx/local/Abc/'))
        self.assertTrue(q.normalize_url('https://tiempo.com.mx/noticia/Abc/?id=1').endswith('?id=1'))

    def test_origin_credentials_path_and_unknown_routes_quarantined(self):
        for url in ['https://evil.example/local/a','https://user:secret@tiempo.com.mx/local/a',
                    'https://tiempo.com.mx:123/local/a',None,'https://tiempo.com.mx:broken/a']:
            self.assertEqual(q.url_evidence(url)[2],'invalid_url_review')
        self.assertEqual(q.url_evidence('https://tiempo.com.mx/new-section/a/')[2],'unknown_route_review')
        self.assertEqual(q.url_evidence('https://tiempo.com.mx/local//')[2],'unrecognized_article_path')
        self.assertEqual(q.url_evidence('https://tiempo.com.mx/local/a/?x=1')[2],'query_url_review')
        self.assertIsNone(q.valid_identity('https://tiempo.com.mx/local//'))

    def test_all_historical_sections_accepted_without_politics_filter(self):
        self.assertEqual(len(q.ROUTES),14)
        for route in q.ROUTES:
            self.assertIsNone(q.url_evidence(f'https://tiempo.com.mx/{route}/article/')[2])
        for route in ['internacional','videos','seguridad','crealo','deportes']:
            self.assertIn(route,q.ROUTES)

    def test_conflicting_dates_do_not_pick_a_day(self):
        for values in [['2025-02-01','2025-02-02'],['2025-02-01T12:00:00','2025-02-01T13:00:00'],
                       ['2025-02-01T12:00:00','2025-02-01T12:00:00Z']]:
            result=q.date_evidence(values)
            self.assertEqual(result['discovery_date_status'],'conflict')
            self.assertIsNone(result['discovery_day'])

    def test_common_date_precision_and_equivalent_offsets(self):
        for values in [['2025-02-01','2025-02-01T12:00:00'],['2025-02-01T12:00:00Z','2025-02-01T07:00:00-05:00']]:
            self.assertEqual(q.date_evidence(values)['discovery_day'],'2025-02-01')

    def test_missing_invalid_evidence_not_replaced_with_valid_other_occurrence(self):
        for values,status in [([None,'2025-02-01'],'missing'),(['2025-02-31','2025-02-01'],'invalid'),(['2025junk'],'invalid')]:
            result=q.date_evidence(values)
            self.assertEqual(result['discovery_date_status'],status)
            self.assertIsNone(result['discovery_day'])

    def test_old_classes_keep_missing_title_and_short_records(self):
        for old,expected in [('old_structural_pass_unreviewed','old_structural_pass_retained'),
                             ('old_short_no_error','old_short_review'),('old_error','old_error_review'),
                             ('old_missing_required_field','old_missing_fields_review')]:
            out=q.classify(candidate(),[old],protected=True)
            self.assertEqual(out['identity_class'],expected)
            self.assertEqual(out['baseline_protected'],1)
        self.assertEqual(q.classify(candidate())['queue_class'],'new_urls')

    def test_pilot_warning_error_and_failed_review_remain_distinct(self):
        ref={'fields_sha256':'a','qa_status':'success','manual_review_status':'reviewed','manual_review_result':'PASS','source_quality_issue':None}
        self.assertEqual(q.classify(candidate(),reviews=[ref])['identity_class'],'reuse_reviewed_pilot')
        flagged={**ref,'source_quality_issue':'source_fragment_suspected','manual_review_result':'PASS_SOURCE_GAP_RECORDED'}
        result=q.classify(candidate(),reviews=[flagged])
        self.assertEqual(result['identity_class'],'reuse_reviewed_pilot_with_source_warning')
        self.assertIn('source_fragment_suspected',result['source_quality_issues_json'])
        self.assertEqual(q.classify(candidate(),reviews=[{**flagged,'qa_status':'error'}])['identity_class'],'known_reviewed_pilot_error')
        for changed in [{'manual_review_result':'FAIL'},{'manual_review_status':'stale'},{'manual_review_result':'REQUIRES_REVIEW'}]:
            self.assertEqual(q.classify(candidate(),reviews=[{**ref,**changed}])['identity_class'],'known_pilot_review_required')
        self.assertEqual(q.classify(candidate(),reviews=[ref,{**ref,'fields_sha256':'b'}])['identity_class'],'known_pilot_review_required')

    def test_priority_is_independent_of_known_identity(self):
        for day,scope in [('2017-12-31','deferred_2015_2017'),('2026-01-01','outside_2026'),('2014-12-31','outside_target_other')]:
            result=q.classify(candidate(day=day),['old_structural_pass_unreviewed'])
            self.assertEqual(result['queue_class'],scope)
            self.assertEqual(result['identity_class'],'old_structural_pass_retained')
        row={**candidate(),'discovery_date_status':'conflict','discovery_day':None}
        self.assertEqual(q.classify(row,['old_structural_pass_unreviewed'])['queue_class'],'discovery_date_conflict')

    def test_fixed_rank_400_has_twenty_months_in_each_eighty_batch(self):
        rows=[]
        for month in q.MONTHS:
            day=month+('-28' if month=='2024-05' else '-01')
            for i in range(25):
                rows.append(candidate(f'https://tiempo.com.mx/local/{month}-{i}/',day))
        selected,short=q.select_validation(rows)
        reversed_selected,_=q.select_validation(reversed(rows))
        self.assertEqual(selected,reversed_selected)
        self.assertEqual(len(selected),400)
        self.assertEqual(len({r['url_key'] for r in selected}),400)
        for batch in range(1,6):
            chosen=[r for r in selected if r['validation_batch']==batch]
            self.assertEqual(len(chosen),80)
            self.assertEqual({month:sum(r['discovery_day'].startswith(month) for r in chosen) for month in q.MONTHS},dict.fromkeys(q.MONTHS,4))
        self.assertTrue(all(x['shortfall']==0 for x in short))
        different,_=q.select_validation(rows,seed='a different prespecified seed')
        self.assertNotEqual([r['url_key'] for r in selected],[r['url_key'] for r in different])

    def test_shortages_are_not_replaced_and_date_boundaries_are_exact(self):
        rows=[candidate('https://tiempo.com.mx/local/may27/','2024-05-27'),candidate('https://tiempo.com.mx/local/may28/','2024-05-28'),
              candidate('https://tiempo.com.mx/local/dec31/','2025-12-31'),candidate('https://tiempo.com.mx/local/jan1/','2026-01-01'),
              {**candidate('https://tiempo.com.mx/local/old/','2025-12-31'),'queue_class':'old_error_review'}]
        selected,short=q.select_validation(rows)
        self.assertEqual({r['url'].split('/')[-2] for r in selected},{'may28','dec31'})
        self.assertEqual(sum(r['shortfall'] for r in short),398)
        with self.assertRaises(q.QueueError):q.select_validation([rows[0],rows[0]])


class QueueIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.baseline=self.root/'baseline.sqlite';self.discovery=self.root/'discovery';self.out=self.root/'final'
        c=sqlite3.connect(self.baseline)
        c.executescript('''CREATE TABLE files(file_id INTEGER PRIMARY KEY,kind TEXT);
          CREATE TABLE urls(url_id INTEGER PRIMARY KEY,url TEXT,url_key TEXT,host TEXT,slug_candidate TEXT);
          CREATE TABLE records(record_id INTEGER PRIMARY KEY,file_id INTEGER,url_id INTEGER,canonical_id INTEGER,final_id INTEGER,old_class TEXT);
          INSERT INTO files VALUES(1,'database');INSERT INTO files VALUES(2,'export');''')
        c.close()

    def old(self,original,canonical,old_class='old_structural_pass_unreviewed',export=True):
        c=sqlite3.connect(self.baseline)
        ids=[]
        for url in [original,canonical]:
            parts=[p for p in q.urlsplit(url).path.split('/') if p]
            cur=c.execute('INSERT INTO urls(url,url_key,host,slug_candidate) VALUES(?,?,?,?)',(url,q.normalize_url(url),'tiempo.com.mx',parts[-1] if len(parts)>=2 else None));ids.append(cur.lastrowid)
        c.execute('INSERT INTO records(file_id,url_id,canonical_id,final_id,old_class) VALUES(?,?,?,?,?)',(1,ids[0],ids[1],ids[0],old_class))
        if export:c.execute('INSERT INTO records(file_id,url_id,canonical_id,final_id,old_class) VALUES(?,?,?,?,?)',(2,ids[0],ids[1],ids[0],old_class))
        c.commit();c.close()

    def discover(self,rows,complete=True):
        location='https://www.tiempo.com.mx/sitemaps/sitemap_1.xml'
        index=self.root/'index.xml';index.write_text(f'<sitemapindex xmlns="{discovery.SM}"><sitemap><loc>{location}</loc></sitemap></sitemapindex>')
        discovery.freeze(index,self.discovery)
        if complete:
            text=f'<urlset xmlns="{discovery.SM}" xmlns:news="{discovery.NEWS}">'+''.join(f'<url><loc>{escape(url)}</loc><news:news><news:publication_date>{escape(day)}</news:publication_date><news:title>{escape(title)}</news:title></news:news></url>' for url,day,title in rows)+'</urlset>'
            snap=self.discovery/'map.xml';snap.write_text(text)
            c=sqlite3.connect(self.discovery/'discovery.sqlite')
            c.execute("UPDATE maps SET state='complete',snapshot_path='map.xml',snapshot_sha256=?,row_count=?",(q.sha_file(snap),len(rows)))
            for r in discovery.parse_urlset(text):
                c.execute('INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?)',(location,*[r[k] for k in ['ordinal','url','discovery_publication_date','discovery_day','discovery_title','sitemap_lastmod','route','candidate_article','discovery_issue']]))
            c.commit();c.close()

    def run_queue(self,**kwargs):
        return q.build_queue(self.discovery,self.baseline,[],self.out,expected_maps=1,**kwargs)

    def test_closed_queue_matches_canonical_and_preserves_conflict_occurrences(self):
        self.old('https://tiempo.com.mx/noticia/existing/','https://tiempo.com.mx/deportes/existing/')
        self.old('https://tiempo.com.mx/noticia/short/','https://tiempo.com.mx/local/short/','old_short_no_error',False)
        rows=[('https://tiempo.com.mx/deportes/existing/','2025-01-02','Stored'),('https://tiempo.com.mx/local/short/','2025-01-03','Short'),
              ('https://tiempo.com.mx/crealo/new/','2025-01-04','New title only in discovery'),
              ('https://tiempo.com.mx/local/conflict/','2025-01-01','A'),('http://www.tiempo.com.mx/local/conflict','2025-01-02','B')]
        self.discover(rows)
        before={p:q.sha_file(p) for p in [self.baseline,self.discovery/'discovery.sqlite']}
        result=self.run_queue()
        self.assertEqual(result['candidate_urls'],4);self.assertEqual(result['discovery_occurrences'],5)
        self.assertEqual(result['queue_classes'],{'discovery_date_conflict':1,'new_urls':1,'old_short_review':1,'old_structural_pass_retained':1})
        with sqlite3.connect(self.out/'queue.sqlite') as c:
            self.assertEqual(c.execute('SELECT count(*) FROM discovery_occurrences').fetchone()[0],5)
            self.assertGreater(c.execute('SELECT count(*) FROM baseline_matches WHERE relation_bits & 2').fetchone()[0],0)
            cols={r[1] for r in c.execute('PRAGMA table_info(candidates)')}
            self.assertNotIn('title',cols);self.assertNotIn('date_published',cols)
        self.assertEqual(before,{p:q.sha_file(p) for p in before})
        import pyarrow.parquet as pq
        with (self.out/'candidates.csv').open(encoding='utf-8-sig') as f:self.assertEqual(len(list(csv.DictReader(f))),4)
        self.assertEqual(pq.ParquetFile(self.out/'candidates.parquet').metadata.num_rows,4)
        self.assertEqual(json.loads((self.out/'queue_manifest.json').read_text())['network_requests'],0)

    def test_pending_discovery_stops_without_publishing_directory(self):
        self.discover([],complete=False)
        with self.assertRaisesRegex(q.QueueError,'has not closed'):self.run_queue()
        self.assertFalse(self.out.exists())

    def test_repaired_xml_title_does_not_exclude_valid_url_and_date(self):
        self.discover([('https://tiempo.com.mx/local/a/','2025-01-01','A\x1a title')])
        result=self.run_queue()
        self.assertEqual(result['queue_classes'],{'new_urls':1})
        with sqlite3.connect(self.out/'queue.sqlite') as c:
            issue=c.execute('SELECT discovery_issue FROM discovery_occurrences').fetchone()[0]
        self.assertIn('illegal_xml_controls_removed_from_news_title',issue)

    def test_requested_canonical_and_final_identifiers_are_all_matched(self):
        original='https://tiempo.com.mx/noticia/old/'
        canonical='https://tiempo.com.mx/local/old/'
        final='https://tiempo.com.mx/crealo/redirected/'
        self.old(original,canonical)
        c=sqlite3.connect(self.baseline)
        cursor=c.execute('INSERT INTO urls(url,url_key,host,slug_candidate) VALUES(?,?,?,?)',
                         (final,q.normalize_url(final),'tiempo.com.mx','redirected'))
        c.execute('UPDATE records SET final_id=?',(cursor.lastrowid,));c.commit();c.close()
        self.discover([(url,'2025-01-01','Known') for url in [original,canonical,final]])
        result=self.run_queue()
        self.assertEqual(result['queue_classes'],{'old_structural_pass_retained':3})
        with sqlite3.connect(self.out/'queue.sqlite') as c:
            self.assertEqual(c.execute('SELECT count(*) FROM baseline_matches').fetchone()[0],6)
            self.assertEqual({r[0] for r in c.execute('SELECT relation_bits FROM baseline_matches')},{1,2,4})
        for counts in result['baseline_record_coverage_by_container'].values():
            self.assertEqual(counts['matched_records'],1)
            self.assertEqual(counts['unmatched_records_preserved'],0)

    def test_no_slug_only_merge_and_soft_error_canonical_not_identity(self):
        self.old('https://tiempo.com.mx/noticia/same-slug/','https://tiempo.com.mx/local//','old_error',False)
        self.discover([('https://tiempo.com.mx/crealo/same-slug/','2025-01-02','Different path'),('https://tiempo.com.mx/local//','2025-01-02','Error')])
        result=self.run_queue();self.assertEqual(result['queue_classes']['new_urls'],1)
        with sqlite3.connect(self.out/'queue.sqlite') as c:self.assertEqual(c.execute('SELECT count(*) FROM baseline_matches').fetchone()[0],0)

    def test_old_records_absent_from_current_directory_remain_visible_not_new(self):
        self.old('https://tiempo.com.mx/noticia/retired/','https://tiempo.com.mx/local/retired/')
        self.discover([('https://tiempo.com.mx/local/new/','2025-01-01','New')])
        result=self.run_queue()
        self.assertEqual(result['queue_classes'],{'new_urls':1})
        for kind in ['database','export']:
            self.assertEqual(result['baseline_record_coverage_by_container'][kind],
                             {'records':1,'matched_records':0,'unmatched_records_preserved':1})
        with (self.out/'baseline_unmatched_records.csv').open(encoding='utf-8-sig') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),2)
        self.assertEqual({row['kind'] for row in rows},{'database','export'})
        self.assertEqual({row['url_key'] for row in rows},{q.normalize_url('https://tiempo.com.mx/noticia/retired/')})

    def test_existing_output_and_repository_output_rejected(self):
        self.out.mkdir()
        with self.assertRaises(q.QueueError):self.run_queue()
        with self.assertRaises(q.QueueError):q.build_queue(self.discovery,self.baseline,[],ROOT/'must-not-create',expected_maps=1)

    def test_snapshot_mutation_and_nonempty_wal_rejected(self):
        self.discover([('https://tiempo.com.mx/local/a/','2025-01-01','A')])
        (self.discovery/'map.xml').write_text('changed')
        with self.assertRaises(ValueError):self.run_queue()
        self.assertFalse(self.out.exists())
        self.baseline.with_name(self.baseline.name+'-wal').write_bytes(b'pending')
        with self.assertRaises(q.QueueError):
            with q.read_only(self.baseline):pass

    def test_pilot_loader_reuses_current_reviews_keeps_warning_and_rejects_stale(self):
        media=self.root/'Media';run=media/'data/00-newspaper_data/crawler/pilots/unit-test';run.mkdir(parents=True)
        (run/'Kevin_NOTE.md').write_text('Kevin offline unit test')
        inputs=self.root/'pilot.csv'
        with inputs.open('w',newline='') as stream:
            w=csv.DictWriter(stream,fieldnames=['sample_id','url','expected_year','selection_reason','expected_kind']);w.writeheader();w.writerow({'sample_id':'P001','url':'https://tiempo.com.mx/local/pilot/','expected_year':'2025','selection_reason':'test','expected_kind':'article_candidate'})
        (run/'inputs').mkdir();(run/'inputs/pilot.csv').write_bytes(inputs.read_bytes())
        fetch=lambda *args,**kw: {'status':200,'final_url':'https://tiempo.com.mx/local/pilot/','content_type':'text/html','error':None,'text':'<html>saved source</html>'}
        parser=lambda *args,**kw: {'title':'Title','summary':'Short','main_text':'Short\nBody','authors':None,'date_published':'2025-01-01','publication_date_source':'jsonld.datePublished','publication_date_evidence':'2025-01-01','canonical_url':'https://tiempo.com.mx/local/pilot/','media_embeds':'[]'}
        pilot.run_pilot(inputs,run,media,pause_seconds=0,fetcher=fetch,parser=parser)
        with sqlite3.connect(run/'pilot.sqlite') as c:row=json.loads(c.execute('SELECT payload_json FROM articles').fetchone()[0])
        annotation={'sample_id':'P001','snapshot_sha256':row['snapshot_sha256'],'fields_sha256':fields_digest(row),'reviewer':'Kevin','reviewed_at':'2026-09-26T20:00:00+00:00','review_result':'PASS_SOURCE_GAP_RECORDED','source_quality_issue':'source_fragment_suspected','review_note':'Synthetic QA'}
        (run/'review_annotations.json').write_text(json.dumps({'format_version':1,'annotations':[annotation]}))
        pilot.run_pilot(inputs,run,media,pause_seconds=0,fetcher=fetch,parser=parser,export_only=True)
        by_key,evidence,_=q.pilot_reuse([run]);self.assertEqual(len(evidence),1)
        self.assertEqual(by_key[q.normalize_url(row['url'])][0]['source_quality_issue'],'source_fragment_suspected')
        annotation['fields_sha256']='b'*64
        (run/'review_annotations.json').write_text(json.dumps({'format_version':1,'annotations':[annotation]}))
        with self.assertRaisesRegex(q.QueueError,'missing/stale'):q.pilot_reuse([run])

    def test_source_change_prevents_final_publication(self):
        self.discover([('https://tiempo.com.mx/local/a/','2025-01-01','A')])
        original=q._export_candidates
        def changed_source(con,output):
            original(con,output)
            with self.baseline.open('ab') as stream:stream.write(b'changed')
        with patch.object(q,'_export_candidates',side_effect=changed_source):
            with self.assertRaisesRegex(q.QueueError,'Input changed'):self.run_queue()
        self.assertFalse(self.out.exists())
        incomplete=list(self.root.glob('.final.incomplete-*/INCOMPLETE.json'))
        self.assertEqual(len(incomplete),1)
        self.assertTrue(json.loads(incomplete[0].read_text())['not_a_final_queue'])


if __name__=='__main__':unittest.main()
