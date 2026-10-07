"""Retained export, truthful errors and offline resume for video/source gaps."""
import csv,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_pilot import run_pilot
from crawler_core.tiempo_html import tiempo_fields

class Priority2RetentionTests(unittest.TestCase):
    def test_all_results_are_accessible_and_resume_does_not_refetch_source_gaps(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);media=p/'Media';run=media/'data/00-newspaper_data/crawler/pilots/priority2-test';run.mkdir(parents=True)
            (run/'Kevin_NOTE.md').write_text('Author: Kevin\nOffline regression fixture only.\n')
            inp=p/'input.csv'
            with inp.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['sample_id','url','expected_year','selection_reason','expected_kind']);w.writeheader()
                for n in range(3):w.writerow({'sample_id':f'R{n}','url':f'https://www.tiempo.com.mx/local/test-{n}/','expected_year':'2024','selection_reason':'Offline regression','expected_kind':'article_candidate'})
            def fetch(url,timeout,**kw):
                n=int(url.rstrip('/').split('-')[-1]);title='' if n==2 else 'Noticia';body='<p>Breve texto real.</p>' if n else '<video><source src="/video/test.mp4"></video>'
                h=f'<html><head><link rel="canonical" href="{url}"></head><body><article id="article-post"><header><h1>{title}</h1></header><blockquote>Por: Ana 01 Junio 2024 12:01</blockquote><div class="complementos-container">{body}</div></article></body></html>'
                return {'status':200,'final_url':url,'content_type':'text/html','error':None,'text':h}
            def parser(text,*,url,source_id):return tiempo_fields(text,url=url)
            opts={'pause_seconds':0,'parser':parser}
            first=run_pilot(inp,run,media,fetcher=Mock(side_effect=fetch),**opts)
            retained=pd.read_parquet(run/'retained_results.parquet').set_index('sample_id')
            self.assertEqual(len(retained),3)
            self.assertEqual(retained.loc['R0','article_kind'],'video_only')
            self.assertEqual(retained.loc['R0','error'],'missing_body')
            self.assertTrue(pd.isna(retained.loc['R0','main_text']))
            self.assertEqual(retained.loc['R2','error'],'missing_title')
            self.assertTrue(pd.isna(retained.loc['R2','title']))
            self.assertIn('Breve texto real.',retained.loc['R2','main_text'])
            self.assertTrue(retained.manual_review_status.eq('not_reviewed').all())
            self.assertEqual(len(pd.read_parquet(run/'articles.parquet')),1)
            self.assertEqual(first['retained_result_rows'],3)
            before=(run/'retained_results.parquet').read_bytes()
            nofetch=Mock(side_effect=AssertionError('Completed rows must not be refetched'))
            resumed=run_pilot(inp,run,media,fetcher=nofetch,**opts)
            nofetch.assert_not_called();self.assertEqual(resumed['network_fetch_calls_started'],3)
            self.assertEqual(before,(run/'retained_results.parquet').read_bytes())
            self.assertEqual(pd.read_csv(run/'retained_results.csv').sample_id.tolist(),['R0','R1','R2'])
            manifest=json.loads((run/'export_manifest.json').read_text())
            self.assertIn('retained_results.parquet',manifest['files'])

if __name__=='__main__':unittest.main()
