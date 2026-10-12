"""Derived stop policy cannot globally waive native title disagreements."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_source_classification_policy as policy


class RepresentationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.flags=['missing_body','unexplained_result_error','visible_title_difference','source_title_metadata_disagreement']
        self.record={'sample_id':'arbitrary-unlisted-id','critical_flags':[],'unexplained_flags':self.flags[:],
            'unexplained_families':['body_or_media','title'],'automatic_flags':self.flags[:]}
        self.decision={'matched':True,'evidence':{'explained_representation_flags':
            ['source_title_metadata_disagreement','visible_title_difference']}}
        self.bound={'path':'synthetic-unit-only','sha256':'synthetic'}

    def trigger(self,decision):
        # Isolated window test injects a verified proof; real-source proof and
        # hash revalidation are separately exercised by the recovery tests.
        with patch.object(policy,'verify_decision',return_value={'decision':decision}):
            return policy.trigger([self.record],{self.record['sample_id']:self.bound},self.bound,{'error':'missing_body'},{})

    def test_only_record_specific_proven_flags_are_explained(self):
        before=copy.deepcopy(self.record)
        self.assertIsNone(self.trigger(self.decision));self.assertEqual(self.record,before)

    def test_missing_proof_does_not_waive_observed_title_flags(self):
        for evidence in [{},{'explained_representation_flags':['visible_title_difference']}]:
            with self.subTest(evidence=evidence),self.assertRaisesRegex(ValueError,'unresolved anomaly'):
                self.trigger({'matched':True,'evidence':evidence})

    def test_unmatched_source_remains_a_stop_even_if_partial_proof_exists(self):
        self.assertEqual(self.trigger({**self.decision,'matched':False}),'unclassified_source_gap')

    def test_unobserved_duplicate_unknown_or_malformed_claims_reject(self):
        for flags in [['date_conflict'],['visible_title_difference']*2,'visible_title_difference',[None]]:
            with self.subTest(flags=flags),self.assertRaises(ValueError):
                policy._explained_flags({'matched':True,'evidence':{'explained_representation_flags':flags}},self.record)
        no_title={**self.record,'automatic_flags':['missing_body'],'unexplained_flags':['missing_body']}
        with self.assertRaises(ValueError):policy._explained_flags(self.decision,no_title)

    def test_unrelated_and_critical_anomalies_are_not_explained(self):
        for key,flag in [('unexplained_flags','unknown_media'),('critical_flags','critical_identity')]:
            record=copy.deepcopy(self.record);record[key].append(flag)
            with self.subTest(flag=flag),self.assertRaises(ValueError):policy._explained_flags(self.decision,record)


if __name__=='__main__':unittest.main()
