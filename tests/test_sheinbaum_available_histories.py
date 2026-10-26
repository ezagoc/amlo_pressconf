"""Check balance histories and sample membership against the daily video panel."""
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/balance/sheinbaum_12m'


class DailyPanelHistoriesTest(unittest.TestCase):
    def test_histories_equal_daily_totals(self):
        d = pd.read_parquet(OUT / 'youtube_outlet_daily.parquet')
        h = pd.read_csv(OUT / 'youtube_histories.csv').set_index('unit_id')
        metrics = ['videos', 'views', 'likes', 'comments', 'interactions']
        expected = d[d.date.between('2023-10-01', '2024-09-30')].groupby('unit_id')[metrics].sum()
        pd.testing.assert_frame_equal(h[metrics].sort_index(), expected.sort_index(), check_dtype=False)
        for metric in metrics[1:]:
            mean = expected[metric].div(expected.videos.where(expected.videos.gt(0))).fillna(0)
            np.testing.assert_allclose(h.loc[mean.index, metric+'_per_video'], mean)

    def test_every_day_and_zero_video_rows_retained(self):
        d = pd.read_parquet(OUT / 'youtube_outlet_daily.parquet')
        self.assertFalse(d.duplicated(['unit_id', 'date']).any())
        days = (d.date.max()-d.date.min()).days+1
        self.assertTrue(d.groupby('unit_id').size().eq(days).all())
        z = d[d.videos.eq(0)]
        self.assertGreater(len(z), 0)
        self.assertTrue(z[['views','likes','comments','interactions','published']].eq(0).all().all())
        full = pd.read_parquet(OUT / 'full_sample.parquet')
        linked = full[full.unit_id.isin(d.loc[~d.shared, 'unit_id'])]
        self.assertTrue(linked.yt_eligible.all())
        sample = pd.read_parquet(OUT / 'youtube_overlap_sample.parquet')
        merged = sample[['unit_id','date']].merge(d, on=['unit_id','date'], validate='one_to_one')
        self.assertEqual(len(merged), len(sample))
        self.assertGreater(int(merged.videos.eq(0).sum()), 0)


if __name__ == '__main__':
    unittest.main()
