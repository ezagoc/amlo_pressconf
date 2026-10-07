"""Source warnings survive controller classification without fabricated review."""
import sys, tempfile,json,hashlib,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_html import tiempo_fields
from crawler_core.tiempo_pilot import extract_result
from crawler_core.tiempo_continuous_v5 import _risk, _window_trigger

class Priority2WarningFlowTests(unittest.TestCase):
    def test_original_source_markup_remains_a_warning_and_prose_loss_still_halts(self):
        url='https://www.tiempo.com.mx/local/source-warning/'
        body='Texto de una noticia real. '*30
        html=f'<html><head><link rel="canonical" href="{url}"></head><body><article id="article-post"><header><h1>Noticia</h1></header><blockquote><p>Resumen real.</p>Por: Ana 01 Junio 2024 12:01</blockquote><div class="complementos-container"><article data-testid="conversation-turn-1"><p>{body}</p></article></div></article></body></html>'
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);raw=html.encode();(p/'page.html').write_bytes(raw)
            response={'status':200,'final_url':url,'content_type':'text/html','error':None,'text':html}
            (p/'page.json').write_text(json.dumps({'response':{k:v for k,v in response.items() if k!='text'}}))
            row=extract_result({'sample_id':'W1','url':url,'ordinal':0,'expected_year':'2024'},response,{'snapshot_path':'page.html','snapshot_sha256':hashlib.sha256(raw).hexdigest(),'captured_at':'2026-10-07T00:00:00Z','attempt_id':'fixture'},'fixture','fixture',lambda text,*,url,source_id:tiempo_fields(text,url=url))
            plan={'date_start':'2018-01-01','date_end_exclusive':'2026-01-01'}
            rec,_=_risk(row,p,{'known_signatures':[]},{},plan)
            self.assertIn('nested_article_markup_inside_body',rec['source_judgment_flags'])
            self.assertIn('source_embedded_conversation_markup',rec['source_judgment_flags'])
            self.assertEqual(rec['manual_review_status'],'not_reviewed')
            self.assertEqual(rec['unexplained_flags'],[])
            self.assertIsNone(_window_trigger([rec,rec,rec]))
            bad={**row,'main_text':'Resumen real.'}
            wrong,_=_risk(bad,p,{'known_signatures':[]},{},plan)
            self.assertTrue(wrong['unexplained_flags'])
            self.assertEqual(_window_trigger([wrong,wrong]),'two_consecutive_same_family_anomalies')
if __name__=='__main__':unittest.main()
