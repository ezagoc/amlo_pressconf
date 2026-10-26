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
    def test_unknown_engagement_is_not_zero(self):
        self.assertTrue(pd.isna(m.strict_sum(pd.Series([2.0,float('nan')]))))
        self.assertEqual(m.strict_sum(pd.Series([0.0,3.0])),3.0)

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
        self.assertTrue(p.loc[~p.source_date_observed,['n_videos','viewCount','likeCount','commentCount']].isna().all().all())
        self.assertTrue(p.loc[p.n_videos.eq(0),['viewCount','likeCount','commentCount']].eq(0).all().all())
        # Reconcile observed cells against globally deduplicated publication IDs.
        counts=v.groupby(['channel_id','date']).size().rename('actual')
        checked=p.set_index(['channel_id','date']).join(counts)
        observed=checked[checked.source_date_observed]
        self.assertTrue(observed.n_videos.eq(observed.actual.fillna(0)).all())
        self.assertEqual(int(p.n_videos.sum()),len(v)-audit['archived_videos_outside_coverage'])
        for path,h in audit['input_sha256'].items():self.assertEqual(m.digest(Path(path)),h)

if __name__=='__main__':unittest.main()
