"""Regression tests for independently reproduced state/integrity failures."""
import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_pilot as pilot
from test_tiempo_pilot_resume import parser, response


class PilotReauditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.media = self.base / 'Media'
        self.run_dir = self.media / 'data/00-newspaper_data/crawler/pilots/review'
        self.run_dir.mkdir(parents=True)
        (self.run_dir / 'Kevin_NOTE.md').write_text('Kevin: offline regression fixture.\n')
        self.input = self.base / 'sample.csv'
        self.write_input()

    def write_input(self, count=1, slug='article'):
        with self.input.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['sample_id', 'url', 'expected_year', 'selection_reason', 'expected_kind'])
            writer.writeheader()
            for i in range(count):
                writer.writerow({'sample_id': f'P{i+1:03d}', 'url': f'https://www.tiempo.com.mx/local/{slug}-{i}/',
                                 'expected_year': 2024, 'selection_reason': 'fixture', 'expected_kind': 'article_candidate'})

    def execute(self, **kwargs):
        return pilot.run_pilot(self.input, self.run_dir, self.media, pause_seconds=0,
                               fetcher=kwargs.pop('fetcher', response), parser=kwargs.pop('parser', parser), **kwargs)

    def exports(self):
        return {name: (self.run_dir / name).read_bytes() for name in pilot.OUTPUT_NAMES}

    def rows(self, table='articles'):
        with sqlite3.connect(self.run_dir / 'pilot.sqlite') as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(f'SELECT * FROM {table}')]

    def test_bound_missing_database_stops_before_replacing_exports(self):
        self.execute()
        before = self.exports()
        (self.run_dir / 'pilot.sqlite').rename(self.run_dir / 'preserved.sqlite')
        for mode in ({'export_only': True}, {}, {'retry_errors': True}, {'reparse_cache': True}):
            with self.subTest(mode=mode), self.assertRaisesRegex(pilot.PilotError, 'database is missing'):
                self.execute(**mode)
        self.assertFalse((self.run_dir / 'pilot.sqlite').exists())
        self.assertEqual(before, self.exports())

    def test_manifest_written_before_database_is_safely_resumable(self):
        with patch.object(pilot, 'connect_db', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.execute()
        self.assertFalse(json.loads((self.run_dir / 'manifest.json').read_text())['database_initialized'])
        fetch = Mock(side_effect=response)
        self.assertEqual(self.execute(fetcher=fetch)['article_rows'], 1)
        self.assertEqual(fetch.call_count, 1)
        self.assertTrue(json.loads((self.run_dir / 'manifest.json').read_text())['database_initialized'])

    def test_empty_database_created_before_manifest_ready_is_resumable(self):
        real_atomic = pilot.atomic_bytes
        def interrupt_ready(path, data):
            if path.name == 'manifest.json' and json.loads(data).get('database_initialized'):
                raise KeyboardInterrupt
            return real_atomic(path, data)
        with patch.object(pilot, 'atomic_bytes', side_effect=interrupt_ready), self.assertRaises(KeyboardInterrupt):
            self.execute()
        self.assertTrue((self.run_dir / 'pilot.sqlite').exists())
        self.assertFalse(json.loads((self.run_dir / 'manifest.json').read_text())['database_initialized'])
        self.assertEqual(self.execute()['article_rows'], 1)

    def test_wrong_database_binding_stops_before_modification(self):
        self.execute()
        original_manifest = (self.run_dir / 'manifest.json').read_bytes()
        before = self.exports()
        with sqlite3.connect(self.run_dir / 'pilot.sqlite') as conn:
            conn.execute("UPDATE articles SET manifest_sha256='foreign-manifest'")
        db_before = (self.run_dir / 'pilot.sqlite').read_bytes()
        fetch = Mock()
        with self.assertRaisesRegex(pilot.PilotError, 'does not match'):
            self.execute(export_only=True, fetcher=fetch)
        fetch.assert_not_called()
        self.assertEqual(db_before, (self.run_dir / 'pilot.sqlite').read_bytes())
        self.assertEqual(before, self.exports())
        self.assertEqual(original_manifest, (self.run_dir / 'manifest.json').read_bytes())

    def test_snapshot_missing_changed_or_wrong_sidecar_blocks_export(self):
        self.execute()
        before = self.exports()
        row = self.rows()[0]
        snapshot = self.run_dir / row['snapshot_path']
        raw = snapshot.read_bytes()
        sidecar = snapshot.with_suffix('.json')
        metadata = sidecar.read_bytes()
        for corruption in ('missing', 'changed', 'sidecar'):
            with self.subTest(corruption=corruption):
                if corruption == 'missing':
                    snapshot.unlink()
                elif corruption == 'changed':
                    snapshot.write_bytes(raw + b'broken')
                else:
                    sidecar.write_text(json.dumps({**json.loads(metadata), 'url': 'https://www.tiempo.com.mx/local/other/'}))
                with self.assertRaisesRegex(pilot.PilotError, 'Snapshot'):
                    self.execute(export_only=True)
                self.assertEqual(before, self.exports())
                snapshot.write_bytes(raw)
                sidecar.write_bytes(metadata)

    def test_same_hash_row_for_unselected_url_is_rejected(self):
        self.execute()
        before = self.exports()
        with sqlite3.connect(self.run_dir / 'pilot.sqlite') as conn:
            record = json.loads(conn.execute('SELECT payload_json FROM articles').fetchone()[0])
            record['url'] = 'https://www.tiempo.com.mx/local/not-selected/'
            conn.execute('UPDATE articles SET url=?,payload_json=?', (record['url'], json.dumps(record)))
        with self.assertRaisesRegex(pilot.PilotError, 'does not match'):
            self.execute(export_only=True)
        self.assertEqual(before, self.exports())

    def test_retry_recovers_only_pending_complete_snapshot_without_fetch(self):
        failed = {**response('https://www.tiempo.com.mx/local/article-0/', 1), 'status': 503}
        self.execute(fetcher=Mock(return_value=failed))
        def stop(*args):
            raise KeyboardInterrupt
        self.assertTrue(self.execute(retry_errors=True, after_snapshot=stop)['interrupted'])
        fetch = Mock(side_effect=AssertionError('complete pending retry must be reused'))
        final = self.execute(retry_errors=True, fetcher=fetch)
        fetch.assert_not_called()
        self.assertEqual(final['network_fetch_calls_started'], 2)
        self.assertEqual(final['article_rows'], 1)
        self.assertEqual(final['incomplete_attempts'], 0)
        self.assertEqual(self.rows('fetch_attempts')[-1]['cached_recovery'], 1)

    def test_retry_does_not_reuse_completed_failure_snapshot(self):
        failed = {**response('https://www.tiempo.com.mx/local/article-0/', 1), 'status': 503}
        self.execute(fetcher=Mock(return_value=failed))
        fetch = Mock(side_effect=response)
        self.assertEqual(self.execute(retry_errors=True, fetcher=fetch)['article_rows'], 1)
        self.assertEqual(fetch.call_count, 1)

    def test_partial_interrupted_attempt_gets_explicit_terminal_state(self):
        failed = {**response('https://www.tiempo.com.mx/local/article-0/', 1), 'error': 'curl_exit_18'}
        def stop(*args):
            raise KeyboardInterrupt
        self.execute(fetcher=Mock(return_value=failed), after_snapshot=stop)
        final = self.execute()
        self.assertEqual(final['incomplete_attempts'], 0)
        abandoned = self.rows('fetch_attempts')[0]
        self.assertEqual(abandoned['qa_status'], 'interrupted')
        self.assertIn('superseded', abandoned['error'])

    def test_alias_author_summary_and_media_differences_are_not_lost(self):
        self.write_input(2)
        for field, value in [('authors', 'Known Reporter'), ('summary', 'A summary'), ('media_embeds', '["https://example.test/video"]')]:
            with self.subTest(field=field):
                folder = self.run_dir.parent / field
                folder.mkdir()
                (folder / 'Kevin_NOTE.md').write_text('Kevin')
                def aliases(html, *, url, source_id):
                    return {**parser(html, url=url, source_id=source_id), 'canonical_url': 'https://www.tiempo.com.mx/local/canonical/',
                            field: None if url.endswith('-0/') else value}
                result = pilot.run_pilot(self.input, folder, self.media, pause_seconds=0, fetcher=response, parser=aliases)
                self.assertEqual(result['article_rows'], 2)
                self.assertEqual(result['canonical_collision_groups'], 1)
                frame = pd.read_parquet(folder / 'articles.parquet')
                self.assertEqual(set(frame['canonical_dedup_status']), {'collision_review'})

    def test_second_process_lock_blocks_before_network_or_exports(self):
        fetch = Mock()
        with pilot.exclusive_run(self.run_dir):
            with self.assertRaisesRegex(pilot.PilotError, 'Another process'):
                self.execute(fetcher=fetch)
        fetch.assert_not_called()
        self.assertFalse((self.run_dir / 'manifest.json').exists())

    def test_annotations_are_protected_and_backed_up(self):
        annotations = self.run_dir / pilot.ANNOTATION_NAME
        annotations.write_text('{"format_version":1,"annotations":[],"author":"Kevin"}')
        self.execute()
        self.execute(reparse_cache=True)
        backups = list((self.run_dir / 'backups').glob('*/review_annotations.json'))
        self.assertTrue(backups)
        self.assertEqual(backups[0].read_bytes(), annotations.read_bytes())
        annotations.unlink()
        external = self.base / 'outside.json'
        external.write_text('protected')
        annotations.symlink_to(external)
        with self.assertRaisesRegex(pilot.PilotError, 'escapes'):
            self.execute(export_only=True)
        self.assertEqual(external.read_text(), 'protected')

    def test_offline_reparse_start_time_is_not_original_capture_time(self):
        with patch.object(pilot, 'now', return_value='2024-01-01T00:00:00+00:00'):
            self.execute()
        with patch.object(pilot, 'now', return_value='2025-01-01T00:00:00+00:00'):
            self.execute(reparse_cache=True)
        attempts = self.rows('fetch_attempts')
        self.assertEqual(attempts[-1]['started_at'], '2025-01-01T00:00:00+00:00')
        self.assertEqual(json.loads(self.rows()[0]['payload_json'])['scrape_timestamp'], '2024-01-01T00:00:00+00:00')


if __name__ == '__main__':
    unittest.main()
