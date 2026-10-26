"""Synthetic invariants and read-only checks on the extended YouTube build."""
import importlib.util
import json
import unittest
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('extended',ROOT/'code/06-outcomes/youtube/09-build_extended_panel.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ExtendedYouTubeTests(unittest.TestCase):
    def test_original_daily_sum_convention(self):
        v=pd.DataFrame({'channel_id':['a','a'],'date':[pd.Timestamp('2024-01-01')]*2,
                        'videoId':['1','2'],'viewCount':[2.0,float('nan')],
                        'likeCount':[float('nan')]*2,'commentCount':[0,3]})
        d=m.recovered_daily(v).iloc[0]
        self.assertEqual(d.n_videos,2)
        self.assertEqual(d.viewCount,2)
        self.assertEqual(d.likeCount,0)
        self.assertEqual(d.commentCount,3)

    def test_channel_url_aliases(self):
        self.assertEqual(m.token('https://www.youtube.com/@Example/videos?x=1'),'example')
        self.assertEqual(m.token('@Example'),'example')
        self.assertIsNone(m.token(None))

    def test_saved_panel_coverage_and_video_totals(self):
        folder=m.media_path('data/06-outcomes/youtube/extended')
        audit=json.loads((folder/'build_audit.json').read_text())
        p=pd.read_parquet(folder/'panel_daily.parquet')
        v=pd.read_parquet(folder/'deduplicated_video_metrics.parquet')
        self.assertFalse(p.duplicated(['channel_id','date']).any())
        self.assertFalse(v.videoId.duplicated().any())
        self.assertGreater(p.loc[p.source_date_observed,'date'].max(),pd.Timestamp('2026-01-01'))
        self.assertTrue(p.source_date_observed.all())
        self.assertTrue(p.source_entity_matched.all())
        self.assertTrue(p[['n_videos','viewCount','likeCount','commentCount']].notna().all().all())
        days=(p.date.max()-p.date.min()).days+1
        self.assertTrue(p.groupby('channel_id').size().eq(days).all())
        self.assertTrue(p.loc[p.n_videos.eq(0),['viewCount','likeCount','commentCount']].eq(0).all().all())
        # Reconcile observed cells against globally deduplicated publication IDs.
        counts=v.groupby(['channel_id','date']).size().rename('actual')
        checked=p.set_index(['channel_id','date']).join(counts)
        observed=checked[checked.source_date_observed]
        self.assertTrue(observed.n_videos.eq(observed.actual.fillna(0)).all())
        self.assertEqual(int(p.n_videos.sum()),len(v)-audit['archived_videos_outside_coverage'])
        # Independently repeat the original groupby/sum/fill convention for
        # every recovered counter, including days outside archive diagnostics.
        for c in ['viewCount','likeCount','commentCount']:
            expected=v.groupby(['channel_id','date'])[c].sum().reindex(checked.index,fill_value=0)
            pd.testing.assert_series_equal(checked[c],expected,check_names=False,check_dtype=False)
            expected_mean=checked[c].div(checked.n_videos.where(checked.n_videos.gt(0))).fillna(0)
            pd.testing.assert_series_equal(checked[c+'_per_video'],expected_mean,check_names=False)
        self.assertTrue((~p.archive_complete_interval & p.n_videos.gt(0)).any())
        self.assertTrue((~p.archive_complete_interval & p.n_videos.eq(0)).any())
        for path,h in audit['input_sha256'].items():self.assertEqual(m.digest(Path(path)),h)

if __name__=='__main__':unittest.main()
