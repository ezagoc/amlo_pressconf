"""Integration: current manual decisions survive native export and resume."""
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_pilot import PilotError, run_pilot
from crawler_core.tiempo_review import fields_digest


class ReviewExportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.media = Path(temp.name)/'Media'
        self.run = self.media/'data/00-newspaper_data/crawler/pilots/review'
        self.run.mkdir(parents=True)
        (self.run/'Kevin_NOTE.md').write_text('Kevin: offline test\n')
        self.input = Path(temp.name)/'input.csv'
        with self.input.open('w',newline='') as f:
            writer=csv.writer(f)
            writer.writerow(['sample_id','url','expected_year','selection_reason','expected_kind'])
            for n in range(2):
                writer.writerow([f'T{n}',f'https://www.tiempo.com.mx/local/a{n}/','2024','test','synthetic'])
        self.annotations = self.run/'review_annotations.json'

    @staticmethod
    def parser(html, *, url, source_id):
        return {'title':'Title','main_text':'Current article body','summary':None,'authors':'Ana',
                'canonical_url':url,'date_published':'2024-01-01','publication_date_source':'article:published_time',
                'publication_date_evidence':'2024-01-01','media_embeds':'[]'}

    def execute(self, **kwargs):
        def response(url, *a, **k):
            return {'status':200,'content_type':'text/html','text':'<html>article</html>','error':None,'final_url':url}
        options={'parser':self.parser,'fetcher':Mock(side_effect=response),'pause_seconds':0}
        options.update(kwargs)
        return run_pilot(self.input,self.run,self.media,**options)

    def make_annotations(self, warning_id='T0'):
        with sqlite3.connect(self.run/'pilot.sqlite') as c:
            rows=[json.loads(x[0]) for x in c.execute('select payload_json from articles order by ordinal')]
        entries=[]
        for row in rows:
            entries.append({'sample_id':row['sample_id'],'url':row['url'],'snapshot_sha256':row['snapshot_sha256'],
                            'fields_sha256':fields_digest(row),'reviewer':'Kevin','reviewed_at':'2026-09-26T22:00:00+00:00',
                            'review_result':'PASS_SOURCE_GAP_RECORDED' if row['sample_id']==warning_id else 'PASS',
                            'source_quality_issue':'source_fragment_suspected' if row['sample_id']==warning_id else None,
                            'review_note':'Verified saved fields against page'})
        self.annotations.write_text(json.dumps({'format_version':1,'annotations':entries}))
        return entries

    def test_native_exports_and_resume_keep_manual_warning_without_fetch(self):
        self.execute()
        self.make_annotations()
        fetch=Mock(side_effect=AssertionError('must remain offline'))
        summary=self.execute(export_only=True,fetcher=fetch)
        fetch.assert_not_called()
        self.assertEqual(summary['manual_review']['status_counts'],{'reviewed':2,'stale':0,'not_reviewed':0})
        for filename in ('articles.csv','articles.parquet'):
            frame=pd.read_csv(self.run/filename) if filename.endswith('.csv') else pd.read_parquet(self.run/filename)
            row=frame.set_index('sample_id').loc['T0']
            self.assertEqual(row.source_quality_issue,'source_fragment_suspected')
            self.assertEqual(row.manual_review_status,'reviewed')
        before=(self.run/'articles.parquet').read_bytes()
        self.execute(fetcher=fetch)
        self.assertEqual(before,(self.run/'articles.parquet').read_bytes())

    def test_reparse_changed_fields_marks_old_review_stale_and_retains_warning(self):
        self.execute(); self.make_annotations()
        def changed(html,**kw):
            return {**self.parser(html,**kw),'main_text':'Different extraction requiring another review'}
        summary=self.execute(reparse_cache=True,parser=changed)
        self.assertEqual(summary['manual_review']['status_counts']['stale'],2)
        row=pd.read_parquet(self.run/'articles.parquet').iloc[0]
        self.assertEqual(row.source_quality_issue,'source_fragment_suspected')
        self.assertIsNone(row.manual_review_result)

    def test_invalid_sidecar_stops_before_fetch_or_database_creation(self):
        self.annotations.write_text('{bad json')
        fetch=Mock()
        with self.assertRaisesRegex(PilotError,'Invalid manual review'):
            self.execute(fetcher=fetch)
        fetch.assert_not_called()
        self.assertFalse((self.run/'pilot.sqlite').exists())

    def test_missing_previously_used_sidecar_stops_and_preserves_exports(self):
        self.execute(); self.make_annotations(); self.execute(export_only=True)
        before=(self.run/'articles.parquet').read_bytes()
        self.annotations.unlink()
        fetch=Mock()
        with self.assertRaisesRegex(PilotError,'annotations are missing'):
            self.execute(fetcher=fetch)
        fetch.assert_not_called()
        self.assertEqual(before,(self.run/'articles.parquet').read_bytes())

    def test_removed_previously_used_record_stops(self):
        self.execute(); entries=self.make_annotations(); self.execute(export_only=True)
        self.annotations.write_text(json.dumps({'format_version':1,'annotations':entries[1:]}))
        with self.assertRaisesRegex(PilotError,'records were removed'):
            self.execute(export_only=True)

    def test_alias_warning_and_member_review_are_not_lost(self):
        def same_article(html,**kw):
            return {**self.parser(html,**kw),'canonical_url':'https://www.tiempo.com.mx/local/canonical/'}
        self.execute(parser=same_article)
        self.make_annotations(warning_id='T1')
        self.execute(export_only=True)
        frame=pd.read_parquet(self.run/'articles.parquet')
        self.assertEqual(len(frame),1)
        self.assertEqual(frame.iloc[0].source_quality_issue,'source_fragment_suspected')
        alias=json.loads(frame.iloc[0].alias_review_annotations)[0]
        self.assertEqual(alias['sample_id'],'T1')
        self.assertEqual(alias['manual_review_status'],'reviewed')
        self.assertEqual(alias['source_quality_issue'],'source_fragment_suspected')

    def test_stale_null_replacement_retains_prior_warning_in_articles_and_attempts(self):
        self.execute(); entries=self.make_annotations(); self.execute(export_only=True)
        original=self.annotations.read_bytes()
        entries[0].update(snapshot_sha256='b'*64,source_quality_issue=None,review_result='PASS')
        self.annotations.write_text(json.dumps({'format_version':1,'annotations':entries}))
        summary=self.execute(export_only=True)
        for filename in ('articles.parquet','attempts.parquet'):
            row=pd.read_parquet(self.run/filename).set_index('sample_id').loc['T0']
            self.assertEqual(row.manual_review_status,'stale')
            self.assertEqual(row.source_quality_issue,'source_fragment_suspected')
            self.assertIsNone(row.manual_review_result)
        history=summary['manual_review']['annotation_history_sha256']
        self.assertEqual(len(history),2)
        self.assertEqual((self.run/'review_history'/f'{history[0]}.json').read_bytes(),original)

    def test_current_resolution_keeps_prior_warning_and_immutable_evidence(self):
        self.execute(); entries=self.make_annotations(); first=self.execute(export_only=True)
        entries[0].update(source_quality_issue=None,review_result='PASS',review_note='Current page and extraction checked; prior concern resolved.')
        self.annotations.write_text(json.dumps({'format_version':1,'annotations':entries}))
        self.execute(export_only=True)
        row=pd.read_parquet(self.run/'articles.parquet').set_index('sample_id').loc['T0']
        self.assertEqual(row.manual_review_status,'reviewed')
        self.assertIsNone(row.source_quality_issue)
        self.assertEqual(row.prior_source_quality_issue,'source_fragment_suspected')
        before=(self.run/'articles.parquet').read_bytes()
        self.execute(export_only=True)
        self.assertEqual(before,(self.run/'articles.parquet').read_bytes())
        self.assertTrue((self.run/'review_history'/f"{first['manual_review']['annotation_file_sha256']}.json").exists())

    def test_referenced_history_missing_or_changed_stops_before_mutation(self):
        self.execute(); self.make_annotations(); summary=self.execute(export_only=True)
        history=self.run/'review_history'/f"{summary['manual_review']['annotation_file_sha256']}.json"
        raw=history.read_bytes(); before=(self.run/'articles.parquet').read_bytes()
        for condition in ('missing','changed'):
            with self.subTest(condition=condition):
                history.unlink() if condition=='missing' else history.write_bytes(raw+b' ')
                fetch=Mock()
                with self.assertRaisesRegex(PilotError,'history'):
                    self.execute(fetcher=fetch)
                fetch.assert_not_called()
                self.assertEqual(before,(self.run/'articles.parquet').read_bytes())
                history.write_bytes(raw)

    def test_backups_preserve_all_referenced_review_history_hashes(self):
        self.execute(); entries=self.make_annotations(); self.execute(export_only=True)
        entries[0].update(snapshot_sha256='b'*64,source_quality_issue=None)
        self.annotations.write_text(json.dumps({'format_version':1,'annotations':entries}))
        summary=self.execute(export_only=True)
        versions=summary['manual_review']['annotation_history_sha256']
        candidates=[p for p in (self.run/'backups').iterdir() if all((p/'review_history'/f'{sha}.json').exists() for sha in versions)]
        self.assertTrue(candidates)
        for sha in versions:
            self.assertEqual(hashlib.sha256((candidates[0]/'review_history'/f'{sha}.json').read_bytes()).hexdigest(),sha)

    def test_legacy_review_export_only_bootstraps_exact_prior_sidecar(self):
        self.execute(); self.make_annotations(); self.execute(export_only=True)
        manifest=self.run/'export_manifest.json'
        value=json.loads(manifest.read_text()); value['manual_review'].pop('annotation_history_sha256')
        manifest.write_text(json.dumps(value))
        summary=self.execute(export_only=True)
        self.assertEqual(len(summary['manual_review']['annotation_history_sha256']),1)
        value=json.loads(manifest.read_text()); value['manual_review'].pop('annotation_history_sha256')
        manifest.write_text(json.dumps(value))
        entries=json.loads(self.annotations.read_text()); entries['annotations'][0]['review_note']='Changed legacy sidecar'
        self.annotations.write_text(json.dumps(entries))
        with self.assertRaisesRegex(PilotError,'exact prior sidecar'):
            self.execute(export_only=True)

    def test_alias_fail_overrides_primary_pass_but_preserves_each_decision(self):
        def same(html,**kw):return {**self.parser(html,**kw),'canonical_url':'https://www.tiempo.com.mx/local/canonical/'}
        self.execute(parser=same); entries=self.make_annotations(warning_id='unused')
        entries[1]['review_result']='FAIL'
        self.annotations.write_text(json.dumps({'format_version':1,'annotations':entries})); self.execute(export_only=True)
        row=pd.read_parquet(self.run/'articles.parquet').iloc[0]
        self.assertEqual(row.manual_review_status,'reviewed')
        self.assertEqual(row.manual_review_result,'FAIL')
        self.assertTrue(row.manual_review_disagreement)
        self.assertFalse(row.canonical_collision)
        self.assertEqual(json.loads(row.primary_review_annotation)['manual_review_result'],'PASS')
        self.assertEqual(json.loads(row.alias_review_annotations)[0]['manual_review_result'],'FAIL')

    def test_alias_stale_and_unreviewed_prevent_aggregate_acceptance(self):
        def same(html,**kw):return {**self.parser(html,**kw),'canonical_url':'https://www.tiempo.com.mx/local/canonical/'}
        self.execute(parser=same); entries=self.make_annotations(warning_id='unused')
        # Before any annotation export, omitting one member makes it unreviewed.
        self.annotations.write_text(json.dumps({'format_version':1,'annotations':entries[:1]})); self.execute(export_only=True)
        row=pd.read_parquet(self.run/'articles.parquet').iloc[0]
        self.assertEqual(row.manual_review_status,'not_reviewed')
        self.assertIsNone(row.manual_review_result)
        self.assertTrue(row.manual_review_disagreement)
        entries[1]['snapshot_sha256']='b'*64
        self.annotations.write_text(json.dumps({'format_version':1,'annotations':entries})); self.execute(export_only=True)
        row=pd.read_parquet(self.run/'articles.parquet').iloc[0]
        self.assertEqual(row.manual_review_status,'stale')
        self.assertIsNone(row.manual_review_result)
        self.assertTrue(row.manual_review_disagreement)

    def test_historical_attempt_keeps_its_bound_review_when_new_fields_change(self):
        self.execute(); self.make_annotations(); self.execute(export_only=True)
        def changed(html,**kw):return {**self.parser(html,**kw),'main_text':'Changed extracted body'}
        self.execute(reparse_cache=True,parser=changed)
        attempts=pd.read_parquet(self.run/'attempts.parquet')
        old=attempts[(attempts.sample_id=='T0') & (attempts.action=='fetch')].iloc[0]
        new=attempts[(attempts.sample_id=='T0') & (attempts.action=='reparse')].iloc[0]
        self.assertEqual(old.manual_review_status,'reviewed')
        self.assertEqual(old.manual_review_result,'PASS_SOURCE_GAP_RECORDED')
        self.assertEqual(new.manual_review_status,'stale')
        self.assertIsNone(new.manual_review_result)
        self.assertEqual(new.source_quality_issue,'source_fragment_suspected')


if __name__=='__main__':
    unittest.main()
