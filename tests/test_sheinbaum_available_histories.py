import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('balance_build', ROOT / 'code/08-results/04-sheinbaum-balance/00-build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class AvailableHistoriesTest(unittest.TestCase):
    def test_metric_specific_observations(self):
        videos = pd.DataFrame({'viewCount': [10, 20, 30], 'likeCount': [2, np.nan, 4],
                               'commentCount': [np.nan, 3, 1]})
        r = build.available_video_history(videos)
        self.assertEqual(r['videos'], 3)
        self.assertEqual(r['views'], 60)
        self.assertEqual(r['likes'], 6)
        self.assertEqual(r['likes_per_video'], 3)
        self.assertEqual(r['comments_per_video'], 2)
        self.assertEqual(r['interactions'], 5)
        self.assertEqual(r['interactions_per_video'], 5)
        self.assertEqual(r['interactions_observed_videos'], 1)

    def test_no_videos_is_zero_but_unknown_counters_are_not(self):
        empty = pd.DataFrame(columns=['viewCount', 'likeCount', 'commentCount'])
        self.assertEqual(build.available_video_history(empty)['videos'], 0)
        self.assertEqual(build.available_video_history(empty)['views'], 0)
        missing = pd.DataFrame({'viewCount': [np.nan], 'likeCount': [np.nan], 'commentCount': [np.nan]})
        r = build.available_video_history(missing)
        self.assertEqual(r['videos'], 1)
        self.assertTrue(np.isnan(r['views']))

    def test_saved_partial_archives_are_retained(self):
        p = ROOT / 'output/balance/sheinbaum_12m'
        h = pd.read_csv(p / 'youtube_histories.csv').set_index('unit_id')
        self.assertTrue((~h.complete_grid & h.videos.notna()).any())
        self.assertTrue((h.likes_observed_videos < h.videos).any())
        for metric in ['views', 'likes', 'comments', 'interactions']:
            d = h[h[metric + '_observed_videos'].gt(0)]
            np.testing.assert_allclose(d[metric] / d[metric + '_observed_videos'], d[metric + '_per_video'])


if __name__ == '__main__':
    unittest.main()
