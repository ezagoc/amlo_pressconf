"""Offline media boundaries: retained source evidence never becomes a transcript."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_html import tiempo_fields
from crawler_core.tiempo_pilot import extract_result
from crawler_core.tiempo_queue import url_evidence


URL = "https://www.tiempo.com.mx/local/media-fixture/"


def page(body, *, lead="", title="Noticia breve", canonical=URL):
    return (f'<html lang="es"><head><link rel="canonical" href="{canonical}"></head>'
            f'<body><article id="article-post"><header><h1>{title}</h1></header>'
            f'<blockquote><p>{lead}</p>Por: Ana 01 Junio 2024 12:01</blockquote>'
            f'<div class="complementos-container">{body}</div></article></body></html>')


def fields(body, **kwargs):
    return tiempo_fields(page(body, **kwargs), url=URL)


class Priority2MediaTests(unittest.TestCase):
    def test_native_video_src_and_source_resolve_and_retain_raw_provenance(self):
        result = fields('<video src="/assets/clip.mp4"><source src="../alt.webm" type="video/webm"></video>')
        self.assertEqual(json.loads(result["media_embeds"]), [
            "https://www.tiempo.com.mx/assets/clip.mp4", "https://www.tiempo.com.mx/local/alt.webm"])
        self.assertEqual(json.loads(result["media_evidence"]), [
            {"source": "native_video.src", "raw_url": "/assets/clip.mp4", "url": "https://www.tiempo.com.mx/assets/clip.mp4", "media_kind": "video"},
            {"source": "native_video.source.src", "raw_url": "../alt.webm", "url": "https://www.tiempo.com.mx/local/alt.webm", "media_kind": "video"}])
        self.assertEqual(result["classification_rule_version"], "tiempo_media_v1")

    def test_request_url_is_resolution_base_not_a_different_canonical(self):
        result = fields('<video src="clip.mp4"></video>', canonical="https://tiempo.com.mx/otra/nota/")
        self.assertEqual(json.loads(result["media_embeds"]), [URL + "clip.mp4"])

    def test_multiple_native_sources_deduplicate_urls_but_keep_evidence(self):
        result = fields('<video src="/clip.mp4"><source src="https://www.tiempo.com.mx/clip.mp4"></video>')
        self.assertEqual(json.loads(result["media_embeds"]), ["https://www.tiempo.com.mx/clip.mp4"])
        self.assertEqual(len(json.loads(result["media_evidence"])), 2)

    def test_native_protocol_relative_http_and_query_urls_are_retained(self):
        result = fields('<video src="//cdn.example.test/play?id=7"></video><video><source src="http://cdn.example.test/stream.m3u8"></video>')
        self.assertEqual(json.loads(result["media_embeds"]), ["https://cdn.example.test/play?id=7", "http://cdn.example.test/stream.m3u8"])

    def test_invalid_native_urls_are_not_video_evidence(self):
        for value in ("", "javascript:alert(1)", "data:video/mp4;base64,AAAA", "blob:https://tiempo.com.mx/id",
                      "file:///tmp/clip.mp4", "ftp://cdn.example.test/clip.mp4", "https://user:secret@cdn.example.test/a.mp4",
                      "https://user@cdn.example.test/a.mp4", "https://cdn.example.test:bad/a.mp4", "https://[invalid/a.mp4"):
            with self.subTest(value=value):
                result = fields(f'<video src="{value}"><source src="{value}"></video>')
                self.assertEqual(json.loads(result["media_embeds"]), [])
                self.assertEqual(json.loads(result["media_evidence"]), [])
                self.assertEqual(result["article_kind"], "article")

    def test_nonarticle_native_ad_video_is_not_article_evidence(self):
        wrappers = ('<aside>{}</aside>', '<div class="ad">{}</div>', '<div class="publicidad-content">{}</div>',
                    '<nav>{}</nav>', '<footer>{}</footer>', '<form>{}</form>', '<button>{}</button>',
                    '<div class="share-buttons">{}</div>', '<div id="sidebar">{}</div>', '<noscript>{}</noscript>')
        for wrapper in wrappers:
            with self.subTest(wrapper=wrapper):
                result = fields(wrapper.format('<video src="/advert.mp4"><source src="/advert.webm"></video>'))
                self.assertEqual(json.loads(result["media_embeds"]), [])
                self.assertEqual(json.loads(result["media_evidence"]), [])
                self.assertEqual(result["article_kind"], "article")

    def test_nonvideo_source_or_video_poster_is_not_video_url(self):
        result = fields('<audio><source src="/audio.mp3"></audio><picture><source src="/image.webp"></picture><video poster="/poster.jpg"></video>')
        self.assertEqual(json.loads(result["media_embeds"]), [])
        self.assertEqual(result["article_kind"], "article")

    def test_zero_prose_video_preserves_missing_title_and_main_text(self):
        result = fields('<video src="/clip.mp4"></video>', title="")
        self.assertEqual(result["article_kind"], "video_only")
        self.assertIsNone(result["main_text"])
        self.assertIsNone(result["summary"])
        self.assertIsNone(result["title"])
        self.assertEqual(result["source_title_status"], "unconfirmed_missing")

    def test_genuine_short_text_and_caption_are_retained(self):
        result = fields('<video src="/clip.mp4"></video><figcaption>Momento del rescate.</figcaption>', lead="Ocurrió hoy.")
        self.assertEqual(result["article_kind"], "article_with_video")
        self.assertEqual(result["main_text"], "Ocurrió hoy.\nMomento del rescate.")
        self.assertLess(len(result["main_text"]), 500)

    def test_trusted_video_iframes_have_narrow_classification(self):
        for link, source in (("https://www.youtube.com/embed/abc", "youtube_iframe.src"),
                             ("//www.youtube-nocookie.com/embed/abc?rel=0", "youtube_iframe.src"),
                             ("https://player.vimeo.com/video/12345", "vimeo_iframe.src")):
            with self.subTest(link=link):
                result = fields(f'<iframe src="{link}"></iframe>')
                self.assertEqual(json.loads(result["media_embeds"]), [link])
                self.assertEqual(result["article_kind"], "video_only")
                self.assertIsNone(result["main_text"])
                self.assertEqual(json.loads(result["media_evidence"])[0]["source"], source)

    def test_arbitrary_or_spoofed_iframe_is_not_video_classification(self):
        for link in ("https://example.test/video", "https://www.youtube.com.evil.test/embed/a", "https://www.youtube.com/",
                     "https://user@www.youtube.com/embed/a", "https://player.vimeo.com/video/not-a-video-id"):
            with self.subTest(link=link):
                result = fields(f'<iframe src="{link}"></iframe>')
                self.assertEqual(json.loads(result["media_embeds"]), [link])
                self.assertEqual(json.loads(result["media_evidence"]), [])
                self.assertEqual(result["article_kind"], "article")

    def test_recognized_video_iframe_in_ad_is_not_article_video(self):
        for body in ('<div class="ad"><iframe src="https://www.youtube.com/embed/advert"></iframe></div>',
                     '<iframe class="ad" src="https://www.youtube.com/embed/advert"></iframe>'):
            with self.subTest(body=body):
                result = fields(body)
                # Preserve the pre-existing link output, but do not misclassify an ad.
                self.assertEqual(json.loads(result["media_embeds"]), ["https://www.youtube.com/embed/advert"])
                self.assertEqual(json.loads(result["media_evidence"]), [])
                self.assertEqual(result["article_kind"], "article")

    def test_twitter_video_markup_is_specific_and_quotation_stays_verbatim(self):
        text = "Dijo: 原文不翻译 — una cita original."
        result = fields(f'<blockquote class="twitter-video"><p>{text}</p><a href="https://x.com/reportera/statuses/123"></a></blockquote>')
        self.assertEqual(result["main_text"], text)
        self.assertEqual(result["article_kind"], "article_with_video")
        self.assertEqual(json.loads(result["media_evidence"])[0]["source"], "twitter_video.href")
        ordinary = fields('<blockquote class="twitter-tweet"><a href="https://x.com/reportera/status/123">Cita real.</a></blockquote>')
        self.assertEqual(ordinary["article_kind"], "article")
        self.assertEqual(ordinary["main_text"], "Cita real.")
        spoofed = fields('<blockquote class="twitter-video"><a href="https://example.test/reportera/status/123">Cita real.</a></blockquote>')
        self.assertEqual(spoofed["article_kind"], "article")

    def test_instagram_original_quotation_and_existing_link_are_unchanged(self):
        permalink = "https://www.instagram.com/p/ABC/?utm_source=ig_embed"
        quotation = "原文保留。Una cita en la noticia."
        result = fields(f'<blockquote class="instagram-media" data-instgrm-permalink="{permalink}"><p>{quotation}</p></blockquote>')
        self.assertEqual(result["main_text"], quotation)
        self.assertEqual(json.loads(result["media_embeds"]), [permalink])
        self.assertEqual(result["article_kind"], "article")

    def test_zero_prose_video_pilot_record_keeps_error_and_http_content_type(self):
        html = page('<iframe src="https://www.youtube.com/embed/abc"></iframe>')
        row = extract_result({"sample_id": "VIDEO", "url": URL, "ordinal": 0, "expected_year": "2024"},
                             {"status": 200, "final_url": URL, "content_type": "text/html", "text": html, "error": None},
                             {"captured_at": "2026-10-06T00:00:00Z", "snapshot_path": "source.html", "snapshot_sha256": "synthetic", "attempt_id": "offline"},
                             "synthetic", "offline", lambda value, *, url, source_id: tiempo_fields(value, url=url))
        self.assertEqual(row["article_kind"], "video_only")
        self.assertEqual(row["content_type"], "text/html")
        self.assertIsNone(row["main_text"])
        self.assertEqual(row["error"], "missing_body")
        self.assertEqual(row["qa_status"], "error")

    def test_social_requests_are_still_excluded_before_article_extraction(self):
        for link in ("https://x.com/reportera/status/123", "https://twitter.com/reportera/status/123"):
            with self.subTest(link=link):
                self.assertEqual(url_evidence(link), (None, None, "invalid_url_review"))

    def test_soft_error_and_unknown_layout_do_not_get_video_classification(self):
        for html in (page('<video src="/clip.mp4"></video>', title="Ocurrió un error al procesar la noticia"),
                     '<html><video src="https://example.test/clip.mp4"></video></html>'):
            with self.subTest(html=html):
                result = tiempo_fields(html, url=URL)
                self.assertIsNotNone(result["source_specific_error"])
                self.assertIsNone(result["article_kind"])
                self.assertIsNone(result["media_evidence"])


if __name__ == "__main__":
    unittest.main()
