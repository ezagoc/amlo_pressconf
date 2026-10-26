import importlib.util
from pathlib import Path
import unittest

import pandas as pd

spec = importlib.util.spec_from_file_location(
    "participation", Path(__file__).resolve().parents[1] / "code/07-final_panel/sheinbaum_participation.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ParticipationTests(unittest.TestCase):
    def test_unobserved_dates_and_dated_links_do_not_create_people(self):
        d1, d2, d3 = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"])
        q = pd.DataFrame({"outlet_id": ["program", "program"], "date": [d1, d2],
                          "reporter_aux": ["ana", "ana"]})
        a = pd.DataFrame({"outlet_id": ["station"] * 6, "date": [d1] * 5 + [d3],
                          "medios": ["Station"] * 6})
        links = pd.DataFrame({"outlet": ["program"], "date": [d1],
                              "attendance_label": ["Station"], "attendance_canonical": ["station"]})
        validated = module.verified_dated_links(links, a, {})
        p = module.assemble_panel(q, a, a.iloc[:0], pd.DatetimeIndex([d1, d2]), validated)
        first = p[(p.outlet_id == "program") & (p.date == d1)].iloc[0]
        self.assertEqual(first.recorded_attendance_n, 0)
        self.assertEqual(first.attendance_supported, 1)
        self.assertTrue(first.common_coverage)
        self.assertEqual(p.recorded_attendance_n.sum(), 6)
        self.assertTrue(p.loc[p.date == d2, "recorded_attendance_n"].isna().all())
        self.assertTrue(p.loc[p.date == d3, "identified"].isna().all())
        self.assertFalse(p.loc[p.date == d3, "common_coverage"].any())

    def test_wrong_roster_date_or_canonical_is_rejected(self):
        a = pd.DataFrame({"outlet_id": ["station"], "date": pd.to_datetime(["2025-01-02"]), "medios": ["Station"]})
        links = pd.DataFrame({"outlet": ["program"], "date": ["2025-01-03"],
                              "attendance_label": ["Station"], "attendance_canonical": ["station"]})
        with self.assertRaises(ValueError):
            module.verified_dated_links(links, a, {})
        links["date"] = "2025-01-02"
        links["attendance_canonical"] = "another outlet"
        with self.assertRaises(ValueError):
            module.verified_dated_links(links, a, {})

    def test_ambiguous_metadata_mapping_is_rejected(self):
        m = pd.DataFrame({"names.transcripts": ["program", "program"],
                          "names.conference": ["station a", "station b"]})
        with self.assertRaises(ValueError):
            module.metadata_links(m)
        self.assertEqual(module.category(pd.Series([None, "aligned", "opp"])), "conflict")

    def test_dated_only_joint_label_needs_no_global_canonical(self):
        a = pd.DataFrame({"outlet_id": [None], "date": pd.to_datetime(["2025-01-02"]),
                          "medios": ["Brand A / Brand B"]})
        links = pd.DataFrame({"outlet": ["brand a"], "date": ["2025-01-02"],
                              "attendance_label": ["Brand A / Brand B"],
                              "attendance_canonical": ["dated link only"]})
        result = module.verified_dated_links(links, a, {})
        self.assertEqual(result.outlet_id.iloc[0], "brand a")
        self.assertTrue(pd.isna(result.linked_attendance_outlet_id.iloc[0]))


if __name__ == "__main__":
    unittest.main()
