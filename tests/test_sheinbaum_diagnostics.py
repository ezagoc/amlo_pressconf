"""Boundary/holdout tests use the original weekday clock, including unknown gaps."""
import importlib.util
import json
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('diag',ROOT/'code/08-results/06-sheinbaum-intermittent/03-build-diagnostics.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class DiagnosticsTests(unittest.TestCase):
    def test_clean_spell(self):
        pre,post,on,off=m.event_labels([0]*6+[1]*5+[0]*6)
        np.testing.assert_array_equal(pre,[0,-5,-4,-3,-2,-1]+[0]*11)
        np.testing.assert_array_equal(post,[0]*11+[1,2,3,4,5,0])
        self.assertEqual(np.flatnonzero(on).tolist(),[6]);self.assertEqual(np.flatnonzero(off).tolist(),[11])
    def test_unknown_not_transition(self):
        pre,post,on,off=m.event_labels([0,np.nan,1,1,np.nan,0,0])
        self.assertFalse(on.any());self.assertFalse(off.any());self.assertFalse(pre.any());self.assertFalse(post.any())
    def test_ambiguity_and_contiguous_windows(self):
        pre,post,_,_=m.event_labels([0]*6+[1]*5+[0]*3+[1]*7+[0]*6)
        self.assertEqual(np.flatnonzero((pre!=0)&(post!=0)).tolist(),[11,12,13])
        self.assertFalse(pre[6:11].any());self.assertFalse(post[14:21].any())
    def test_saved_labels_and_outcomes(self):
        audit=json.loads((m.OUT/'build_audit.json').read_text())
        for key,path in audit['input_paths'].items():self.assertEqual(m.b.sha(Path(path)),audit['sha256'][key])
        d=pd.read_parquet(m.OUT/'analysis_panel.parquet');full=pd.read_parquet(m.OUT/'weekday_event_labels.parquet')
        self.assertFalse(d.loc[d.clean_train,'holdout'].any());self.assertTrue(d.loc[d.clean_train,'D'].eq(0).all())
        self.assertTrue(d.loc[d.pre_day.ne(0)|d.post_day.ne(0),'D'].eq(0).all())
        for _,g in full.groupby('unit_id'):
            z=g.set_index('sample_day')
            for r in g[g.pre_day.ne(0)].itertuples():
                onset=r.sample_day-r.pre_day
                self.assertEqual(z.loc[onset,'D'],1)
                self.assertTrue(z.loc[r.sample_day:onset-1,'D'].eq(0).all())
            for r in g[g.post_day.ne(0)].itertuples():
                exit_day=r.sample_day-r.post_day+1
                self.assertEqual(z.loc[exit_day-1,'D'],1)
                self.assertTrue(z.loc[exit_day:r.sample_day,'D'].eq(0).all())
        source=pd.read_parquet(m.b.OUT/'analysis_panel.parquet')
        c=d.merge(source,on=['unit_id','date'],suffixes=('_a','_b'),validate='one_to_one')
        for o in m.b.OUTCOMES:
            np.testing.assert_array_equal(c['Y_'+o+'_a'],c['Y_'+o+'_b'])
        excluded=set(d.loc[~d.clean_eligible,'unit_id'])
        self.assertEqual(excluded,{'avan noticias','healy','nx noticias'})
        self.assertEqual(d.loc[d.group.notna(),'unit_id'].nunique(),106)
        self.assertEqual(d.loc[d.clean_eligible,'unit_id'].nunique(),122)
        self.assertEqual(d.date.nunique(),179)
if __name__=='__main__':unittest.main()
