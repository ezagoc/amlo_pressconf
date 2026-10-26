import unittest
from pathlib import Path
import pandas as pd
from official_source import parse, speaker_prefix, validate_page
from pipeline import raw_runs, spoken_text, DEFAULT_ROOT


class OfficialParserTests(unittest.TestCase):
    def test_full_bold_question_and_inline_word(self):
        text='<p><strong>PREGUNTA: ¿Cuándo?</strong></p><p>El <em>I</em>nstituto.</p>'
        filler=''.join('<p>'+('Texto ordinario. '*15)+'</p>' for _ in range(101))
        headings=''.join('<p><strong>PREGUNTA:</strong> ¿Y después?</p>' for _ in range(11))
        page=('<h1>Versión estenográfica. 4 de marzo de 2025</h1><div class="article-body">'+text+filler+headings+'</div>').encode()
        rows,_=parse(page,'2025-03-04',{'raw_path':'fixture','url':'fixture','sha256':'fixture'})
        self.assertEqual(rows[0]['text'],'¿Cuándo?')
        self.assertEqual(rows[1]['text'],'El Instituto.')
        self.assertEqual(len(raw_runs(pd.DataFrame(rows))),12)

    def test_non_speaker_colons_preserved(self):
        for text in ['Los resultados son: buenos.', '¿Cuándo?: hoy.', '(VIDEO)']:
            self.assertEqual(speaker_prefix(text),(None,text))
        self.assertEqual(spoken_text('—000—'),'')

    def test_unparsed_body_text_fails_closed(self):
        page=('<h1>Versión estenográfica. 4 de marzo de 2025</h1><div class="article-body">'
              '<h2>Texto fuera de párrafos.</h2><p>'+('Habla. '*2000)+'</p></div>').encode()
        with self.assertRaisesRegex(ValueError,'Unparsed'):
            parse(page,'2025-03-04',{})

    def test_archived_march4_regression(self):
        path=DEFAULT_ROOT/'official_source/pilot-10/raw/2025-03-04.html'
        if not path.exists():self.skipTest('Local official archive unavailable')
        rows,_=parse(path.read_bytes(),'2025-03-04',{'raw_path':str(path),'url':'fixture','sha256':'fixture'})
        df=pd.DataFrame(rows)
        match=df[df.text.str.startswith('Pero en el caso de los lugares públicos')]
        self.assertEqual(len(match),1)
        self.assertEqual(match.iloc[0].participant_raw,'PREGUNTA')
        self.assertIn('DAVID KERSHENOBICH',df.iloc[match.index[0]+1].participant_raw)
        for name in ['EDUARDO CLARK','DAVID KERSHENOBICH','ALEJANDRO SVARCH','ZOÉ ROBLEDO']:
            self.assertTrue(df.participant_raw.str.contains(name).any())

    def test_date_validation_does_not_match_day_suffix(self):
        page=('<h1>Versión estenográfica. 14 de julio de 2025</h1>'
              '<div class="article-body"><p>'+('Texto. '*300)+'</p></div>').encode()
        with self.assertRaisesRegex(ValueError,'date mismatch'):
            validate_page(page,'2025-07-04')

    def test_first_day_ordinal_validates_without_accepting_another_date(self):
        page=('<h1>Versión estenográfica. 1º de abril de 2025</h1>'
              '<div class="article-body"><p>'+('Texto. '*300)+'</p></div>').encode()
        validate_page(page,'2025-04-01')
        with self.assertRaisesRegex(ValueError,'date mismatch'):
            validate_page(page,'2025-04-11')

    def test_document_header_is_separate_from_speech(self):
        path=DEFAULT_ROOT/'official_source/full/raw/2025-07-14.html'
        if not path.exists():self.skipTest('Local official archive unavailable')
        rows,_=parse(path.read_bytes(),'2025-07-14',{'raw_path':str(path),'url':'fixture','sha256':'fixture'})
        self.assertTrue(all(r['row_kind']=='document_metadata' for r in rows[:4]))
        self.assertEqual(rows[4]['row_kind'],'transcript')
        self.assertIn('CLAUDIA SHEINBAUM',rows[4]['participant_raw'])

if __name__=='__main__':unittest.main()
