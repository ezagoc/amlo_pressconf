import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('backfill',ROOT/'code/06-outcomes/youtube/08-backfill_reviewed_playlists.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class FakeAPI:
    def __init__(self,fail=False):self.fail=fail;self.calls=[]
    def get(self,resource,**params):
        self.calls.append(resource)
        if resource=='playlists':return {'items':[{'id':'p','snippet':{'channelId':'target','title':'News 2022','publishedAt':'2022-01-01T00:00:00Z'}}]}
        if resource=='playlistItems':return {'items':[{'contentDetails':{'videoId':vid},'snippet':{'videoOwnerChannelId':owner}} for vid,owner in [('own','target'),('foreign','other'),('misleading','target'),('private','target')]]}
        if self.fail:raise m.base.APIError('quotaExceeded',403)
        return {'items':[{'id':'own','snippet':{'channelId':'target','publishedAt':'2021-01-01T00:00:00Z'}},{'id':'misleading','snippet':{'channelId':'other'}}]}

class Tests(unittest.TestCase):
    def test_atomic_resume_and_owner_verification(self):
        db=m.base.open_db(':memory:');m.initialize(db)
        self.assertTrue(m.catalog_page(FakeAPI(),db,'target'))
        with self.assertRaises(m.base.APIError):m.playlist_page(FakeAPI(True),db,'target','p')
        self.assertEqual(db.execute('SELECT pages FROM backfill_playlists').fetchone()[0],0)
        self.assertEqual(db.execute('SELECT count(*) FROM videos').fetchone()[0],0)
        m.playlist_page(FakeAPI(),db,'target','p')
        self.assertEqual(db.execute('SELECT video_id,channel_id FROM videos').fetchall(),[('own','target')])
        decisions=dict(db.execute('SELECT video_id,decision FROM backfill_playlist_videos'))
        self.assertEqual(decisions['foreign'],'excluded_foreign_channel')
        self.assertEqual(decisions['misleading'],'excluded_foreign_channel')
        self.assertEqual(decisions['private'],'unavailable_owner_unverified')
        api=FakeAPI();m.playlist_page(api,db,'target','p');self.assertEqual(api.calls,[])
        db.close()
    def test_year_priority_is_not_a_video_date_filter(self):
        self.assertEqual(m.priority({'snippet':{'title':'News 2022','publishedAt':'2025-01-01'}}),0)
        self.assertEqual(m.priority({'snippet':{'title':'Archive','publishedAt':'2020-01-01'}}),1)
        self.assertEqual(m.priority({'snippet':{'title':'Archive','publishedAt':'2020-01-01'},'contentDetails':{'itemCount':5000}}),2)
        self.assertEqual(m.priority({'snippet':{'title':'Latest','publishedAt':'2025-01-01'}}),3)

if __name__=='__main__':unittest.main()
