import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("reviewed_youtube",ROOT/"code/06-outcomes/youtube/07-extract_reviewed_outlets.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
CID="UC"+"a"*22
ENTRY={"id":"test outlet","name":"Test Outlet","youtube":{"url":"https://www.youtube.com/@tést"}}

class FakeAPI:
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    def get(self,resource,**params):
        self.calls.append((resource,params))
        if resource=="channels":return {"items":[{"id":CID,"snippet":{"title":"Test","publishedAt":"2020-01-01T00:00:00Z"},"statistics":{"hiddenSubscriberCount":True},"contentDetails":{"relatedPlaylists":{"uploads":"UUtest"}}}]}
        if resource=="playlistItems":
            if params.get("pageToken")=="page2":return {"items":[{"contentDetails":{"videoId":"v2"}}]}
            return {"items":[{"contentDetails":{"videoId":"v1"}},{"contentDetails":{"videoId":"gone"}}],"nextPageToken":"page2"}
        if self.fail:raise module.APIError("quotaExceeded",403)
        return {"items":[{"id":v,"snippet":{"channelId":CID,"title":v,"publishedAt":"2022-01-01T12:00:00Z"},"statistics":{"viewCount":"7"}} for v in params["id"].split(",") if v!="gone"]}

class ExtractorTests(unittest.TestCase):
    def test_url_selection(self):
        self.assertEqual(module.channel_selector(ENTRY["youtube"]["url"]),{"forHandle":"@tést"})
        self.assertEqual(module.channel_selector("https://www.youtube.com/user/news"),{"forUsername":"news"})
        self.assertEqual(module.channel_selector(CID),{"id":CID})
        for value in ["https://youtube.com.evil.test/@news","https://www.youtube.com/c/news","https://youtu.be/xyz"]:
            with self.assertRaises(ValueError):module.channel_selector(value)
    def test_atomic_resume_missing_stats_and_unavailable_video(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);db=module.open_db(path/"state.sqlite3")
            with self.assertRaises(module.APIError):module.extract_entry(FakeAPI(True),db,ENTRY)
            self.assertEqual(db.execute("SELECT pages FROM progress").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM videos").fetchone()[0],0)
            self.assertEqual(module.extract_entry(FakeAPI(),db,ENTRY,1),(0,1))
            api=FakeAPI();self.assertEqual(module.extract_entry(api,db,ENTRY,1),(1,2))
            self.assertEqual(api.calls[0][1]["pageToken"],"page2")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM videos").fetchone()[0],3)
            api=FakeAPI();module.extract_entry(api,db,ENTRY);self.assertFalse(api.calls)
            module.export(db,path)
            import csv
            with (path/"youtube_videos.csv").open() as f: videos=list(csv.DictReader(f))
            self.assertEqual(next(v for v in videos if v["videoId"]=="gone")["viewCount"],"")
            self.assertTrue(all(v["likeCount"]=="" for v in videos))
            with (path/"youtube_channels.csv").open() as f: channel=list(csv.DictReader(f))[0]
            self.assertEqual(channel["yt_subscriberCount"],"")
            self.assertEqual(channel["uploads_complete"],"True")
            module.extract_entry(FakeAPI(),db,ENTRY,refresh=True)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM videos").fetchone()[0],3)
            db.close()
    def test_channel_change_is_rejected(self):
        db=module.open_db(":memory:");module.extract_entry(FakeAPI(),db,ENTRY,1)
        other={**ENTRY,"youtube":{"url":"https://www.youtube.com/@other"}}
        with self.assertRaises(ValueError):module.extract_entry(FakeAPI(),db,other)
        db.close()
    def test_channels_only_does_not_request_videos(self):
        db=module.open_db(":memory:");api=FakeAPI()
        self.assertEqual(module.extract_entry(api,db,ENTRY,0),(0,0))
        self.assertEqual([r for r,p in api.calls],["channels"])
        db.close()

if __name__=="__main__":unittest.main()
