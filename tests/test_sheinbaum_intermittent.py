"""Weekday exposure, missing-exposure handling and full YouTube-grid checks."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build',ROOT/'code/08-results/06-sheinbaum-intermittent/00-build.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class IntermittentTests(unittest.TestCase):
    def test_wednesday_spans_weekend_without_counting_it(self):
        dates=pd.bdate_range('2025-01-08',periods=7)
        status=b.spell_status([1,0,0,0,0,0,0],[0]*7)
        self.assertEqual(list(dates[status.eq(1)].strftime('%a')),['Wed','Thu','Fri','Mon','Tue'])
        self.assertEqual(status.tolist(),[1,1,1,1,1,0,0])
    def test_overlapping_events_extend_union(self):
        self.assertEqual(b.spell_status([1,0,0,1]+[0]*5,[0]*9).tolist(),[1]*8+[0])
    def test_unknown_never_becomes_untreated(self):
        a=b.spell_status([0]*6,[1,0,0,0,0,0])
        self.assertTrue(a.iloc[:5].isna().all());self.assertEqual(a.iloc[5],0)
        a=b.spell_status([0,0,1,0,0,0],[1,0,0,0,0,0])
        self.assertTrue(a.iloc[:2].isna().all());self.assertTrue(a.iloc[2:].eq(1).all())
    def test_saved_panel(self):
        full=pd.read_parquet(b.OUT/'full_calendar.parquet')
        d=pd.read_parquet(b.OUT/'analysis_panel.parquet')
        self.assertEqual(full.groupby('unit_id').size().unique().tolist(),[258])
        self.assertEqual(d.unit_id.nunique(),full.unit_id.nunique())
        self.assertTrue(d.date.dt.dayofweek.lt(5).all())
        self.assertTrue(full.loc[~full.weekday,'D'].isna().all())
        self.assertFalse(d.D.isna().any());self.assertTrue(d.groupby('date').D.min().eq(0).all())
        self.assertTrue(d.groupby('unit_id').D.apply(lambda x:x.eq(0).sum()).ge(5).all())
        source=pd.read_parquet(ROOT/'output/balance/sheinbaum_12m/youtube_outlet_daily.parquet')
        source['date']=pd.to_datetime(source.date)
        compare=d.merge(source,on=['unit_id','date'],suffixes=('_used','_source'),validate='one_to_one')
        for name in ['videos','views','likes','comments','interactions']:
            np.testing.assert_array_equal(compare[name+'_used'],compare[name+'_source'])
        self.assertGreater(d.videos.eq(0).sum(),0)
        for o in b.OUTCOMES:
            np.testing.assert_allclose(d['Y_'+o],np.arcsinh(d[o].clip(upper=d[o].quantile(.99))))
        self.assertEqual(sorted(set(full.loc[full.weekday,'date'])-set(d.date)),list(pd.to_datetime(['2025-05-02','2025-05-05','2025-05-06','2025-05-07','2025-05-08'])))
        events=pd.read_csv(b.OUT/'speaking_events.csv',parse_dates=['date'])
        # Independent date-offset construction (not the rolling implementation).
        expected={(row.unit_id,day) for row in events.itertuples() for day in pd.bdate_range(row.date,periods=5)}
        actual=set(map(tuple,d.loc[d.D.eq(1),['unit_id','date']].to_numpy()))
        eligible=set(map(tuple,d[['unit_id','date']].to_numpy()))
        self.assertEqual(actual,expected & eligible)

if __name__=='__main__':unittest.main()
