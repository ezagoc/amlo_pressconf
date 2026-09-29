#!/usr/bin/env python3
"""Resume public Spanish captions for the expanded official video inventory."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import WORK_ROOT  # noqa: E402

import yt_dlp
import download_amlo_tracking_poll as downloader

ROOT = WORK_ROOT / 'recovery' / 'social'
OUTPUT = ROOT / 'youtube'


def fetch(video):
    video_id = video['id']
    record = {'video_id': video_id, 'title': video['title'],
              'url': 'https://www.youtube.com/watch?v=' + video_id}
    try:
        raw = sorted((OUTPUT / 'transcripts/raw').glob(video_id + '*.json3'))
        if not raw:
            args = downloader.build_parser().parse_args([])
            options = downloader.build_ydl_options(args, OUTPUT)
            options.update(quiet=True, no_warnings=True, noprogress=True,
                           retries=1, fragment_retries=1, socket_timeout=20)
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([record['url']])
            raw = sorted((OUTPUT / 'transcripts/raw').glob(video_id + '*.json3'))
        for path in raw:
            downloader.convert_caption_file(path, OUTPUT, video_id)
        record.update(status='downloaded' if raw else 'no_transcript_available',
                      raw_subtitles=[str(p.relative_to(OUTPUT)) for p in raw])
    except Exception as error:
        record.update(status='error', error=str(error))
    return record


def main():
    videos = [json.loads(line) for line in (ROOT / 'expanded_official_videos.jsonl').read_text().splitlines()]
    path = ROOT / 'caption_download_report.json'
    previous = json.loads(path.read_text()) if path.is_file() else []
    report = {r['video_id']: r for r in previous}
    # Existing original captions already preserve these videos; keep their files.
    existing = {p.name.split('.')[0] for p in (WORK_ROOT / 'youtube' / 'transcripts' / 'raw').glob('*.json3')}
    for video in videos:
        if video['id'] in existing:
            report[video['id']] = {'video_id': video['id'], 'title': video['title'],
                                    'status': 'available_in_original_archive'}
    pending = [v for v in videos if report.get(v['id'], {}).get('status') not in
               {'downloaded', 'available_in_original_archive', 'no_transcript_available'}]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(fetch, v) for v in pending]):
            record = future.result()
            report[record['video_id']] = record
            downloader.write_json(path, [report[k] for k in sorted(report)])
            print(json.dumps({'completed': len(report), 'total': len(videos),
                              'video_id': record['video_id'], 'status': record['status']}), flush=True)


if __name__ == '__main__':
    main()
