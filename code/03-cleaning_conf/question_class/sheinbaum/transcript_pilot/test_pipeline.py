import copy
import unittest
import pandas as pd
from pipeline import validate_structure, validate_qa, spoken_text

class EvidenceTests(unittest.TestCase):
    def test_stage_directions_not_counted_as_speech(self):
        for text in ['(FIRMA DE DECRETO)', '(inaudible)', '---', '[Chiapas, Oaxaca]']:
            self.assertEqual(spoken_text(text),'')
        self.assertEqual(spoken_text('(Habla en lengua indígena) Kuíra ba.'),'Kuíra ba.')
        self.assertEqual(spoken_text('Gracias. Buenos días.'),'Gracias. Buenos días.')
    def setUp(self):
        self.day=pd.DataFrame({'source_row':[0,1,2,3], 'participant':['PREGUNTA','PREGUNTA','PRESIDENTA','PREGUNTA'],
            'text':['Buenos días.','¿Cuándo? ¿Cuánto?','Mañana. Diez pesos.','Gracias.']})
        self.structure={'speakers':[{'speaker_id':1,'role':'journalist','identity_basis':'unresolved','evidence_rows':[]},
            {'speaker_id':2,'role':'president','identity_basis':'source_label','evidence_rows':[2]}],
            'segments':[{'start':0,'end':1,'speaker_id':1,'delivery':'live'},
                {'start':2,'end':2,'speaker_id':2,'delivery':'live'},
                {'start':3,'end':3,'speaker_id':1,'delivery':'live'}]}
        self.qa={'items':[{'item_number':1,'spans':[{'row':1,'quote':'¿Cuándo?'}],'context_rows':[0],
            'followup_of':None,'response_ranges':[{'start':2,'end':2}],'link_status':'linked'},
            {'item_number':2,'spans':[{'row':1,'quote':'¿Cuánto?'}],'context_rows':[],
            'followup_of':None,'response_ranges':[{'start':2,'end':2}],'link_status':'linked'}]}
    def test_shared_answer_and_split_question(self):
        validate_structure(self.structure,self.day);validate_qa(self.qa,self.day,self.structure)
    def test_partition_missing_overlap_and_cross_label(self):
        for start,end in [(1,1),(0,2)]:
            bad=copy.deepcopy(self.structure);bad['segments'][0].update(start=start,end=end)
            with self.assertRaises(ValueError):validate_structure(bad,self.day)
    def test_reject_paraphrase(self):
        self.qa['items'][0]['spans'][0]['quote']='¿Para cuándo?'
        with self.assertRaises(ValueError):validate_qa(self.qa,self.day,self.structure)
    def test_reject_video_question(self):
        self.structure['segments'][0]['delivery']='recorded'
        with self.assertRaises(ValueError):validate_qa(self.qa,self.day,self.structure)
    def test_reject_response_from_reporter(self):
        self.qa['items'][0]['response_ranges']=[{'start':3,'end':3}]
        with self.assertRaises(ValueError):validate_qa(self.qa,self.day,self.structure)
    def test_no_response_and_invalid_followup(self):
        self.qa['items'][0].update(response_ranges=[],link_status='no_response_found')
        validate_qa(self.qa,self.day,self.structure)
        self.qa['items'][0]['followup_of']=2
        with self.assertRaises(ValueError):validate_qa(self.qa,self.day,self.structure)

if __name__=='__main__':unittest.main()
