"""Validate saved official AMLO files and summarize source differences offline."""
import argparse
from pathlib import Path
import json
from difflib import SequenceMatcher
import pandas as pd
from scrape import compact, digest, media_path, norm, save


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=media_path('data', '02-conferences', 'official_source', 'full'))
    args = p.parse_args(); root = args.root; out = root / 'auxiliar'
    manifest = json.loads((root / 'manifest.json').read_text())
    pages = manifest['pages']
    for page in pages:
        assert digest(Path(page['raw_path']).read_bytes()) == page['sha256'], page['url']
    data = pd.read_parquet(out / 'transcript_rows.parquet')
    assert not data.duplicated(['date', 'source_row']).any(), 'Duplicate source-row IDs in selected daily pages'
    assert data.groupby('date').source_url.nunique().eq(1).all()
    assert data.groupby('date').source_sha256.nunique().eq(1).all()
    assert data.word_count.eq(data.text.str.split().str.len()).all()
    inv = pd.read_csv(out / 'original_csv_inventory.csv')
    assert all(digest(Path(r.path).read_bytes()) == r.sha256 for r in inv.itertuples()), 'Original CSV changed during collection'
    cmp = pd.read_csv(out / 'source_comparison.csv')
    paired = cmp[cmp.official_available].copy()
    paired['word_difference'] = paired.official_words - paired.csv_words
    paired['word_difference_percent'] = 100 * paired.word_difference / paired.csv_words.where(paired.csv_words.gt(0))
    paired['absolute_word_difference'] = paired.word_difference.abs()
    paired.sort_values('absolute_word_difference', ascending=False).to_csv(out / 'ranked_source_differences.csv', index=False)
    label_changes = []
    days = {date: day[day.text.map(compact).ne('')].reset_index(drop=True) for date, day in data.groupby('date')}
    repeats = []
    for date, day in days.items():
        long_paragraphs = [norm(t) for t in day.text if len(t.split()) >= 5]
        if len(long_paragraphs) < 100: continue
        middle = len(long_paragraphs) // 2
        ratio = SequenceMatcher(None, long_paragraphs[:middle], long_paragraphs[middle:], autojunk=False).ratio()
        if ratio >= .85:
            repeats.append({'date': date, 'first_second_half_similarity': ratio,
                            'official_url': day.source_url.iloc[0], 'raw_words': int(day.word_count.sum()),
                            'status': 'possible_duplicated_official_transcript_block_review_before_word_counts'})
    pd.DataFrame(repeats, columns=['date','first_second_half_similarity','official_url','raw_words','status']).to_csv(out / 'official_repeated_text_review.csv', index=False)
    for record in paired.itertuples():
        old = pd.read_csv(record.csv_path).fillna('').reset_index(names='csv_row')
        old = old[old.Texto.map(compact).ne('')].reset_index(drop=True)
        new = days[record.date]
        for match in SequenceMatcher(None, old.Texto.map(compact).tolist(), new.text.map(compact).tolist(), autojunk=False).get_matching_blocks():
            for offset in range(match.size):
                a, b = old.iloc[match.a + offset], new.iloc[match.b + offset]
                if norm(a.Participante) != norm(b.participant_raw):
                    label_changes.append({'date': record.date, 'csv_path': record.csv_path,
                        'csv_row': int(a.csv_row), 'official_row': int(b.source_row),
                        'csv_label': a.Participante, 'official_label': b.participant_raw,
                        'text': b.text, 'official_url': b.source_url})
    pd.DataFrame(label_changes, columns=['date','csv_path','csv_row','official_row','csv_label','official_label','text','official_url']).to_csv(out / 'aligned_speaker_label_differences.csv', index=False)
    report = {'validation': 'PASS', 'archived_page_hashes_checked': len(pages),
              'selected_dates': int(data.date.nunique()), 'selected_rows': len(data),
              'unchanged_original_csv_files': len(inv), 'comparable_csv_files': len(paired),
              'median_official_minus_csv_words': float(paired.word_difference.median()),
              'median_absolute_word_difference': float(paired.absolute_word_difference.median()),
              'original_files_with_zero_words': int(paired.csv_words.eq(0).sum()),
              'possible_duplicated_official_transcripts': len(repeats),
              'files_with_at_least_100_words_absolute_difference': int(paired.absolute_word_difference.ge(100).sum()),
              'files_with_at_least_5_percent_absolute_difference': int(paired.word_difference_percent.abs().ge(5).sum()),
              'exactly_aligned_paragraphs_with_different_speaker_labels': len(label_changes),
              'interpretation': 'Difference thresholds are inspection leads, not validated omissions or accuracy estimates. Duplicate/misdated originals and formatting can affect comparisons.'}
    save(out / 'integrity_and_comparison_audit.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
