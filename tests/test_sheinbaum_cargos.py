import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("cargo_audit", Path(__file__).resolve().parents[1] /
    "code/08-results/03-sheinbaum-participation/03-cargo-audit.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CargoAuditTests(unittest.TestCase):
    def test_reporter_and_photographer_are_not_support_only(self):
        self.assertEqual(module.classify(["REPORTERO", "FOTOGRAFO"]), "REPORTERO + support roles")
        self.assertEqual(module.classify(["REPORTERO"]), "REPORTERO only")

    def test_youtuber_is_kept_distinct_from_reporter(self):
        self.assertEqual(module.classify(["YOUTUBER"]), "YOUTUBER; no REPORTERO")
        self.assertEqual(module.classify(["YOUTUBER", "FOTOGRAFO"]), "YOUTUBER; no REPORTERO")

    def test_support_only_and_unmatched_do_not_imply_reporter(self):
        self.assertEqual(module.classify(["FOTOGRAFO", "CAMAROGRAFO"]), "Only excluded support roles")
        self.assertEqual(module.classify([]), "No matched roster entry")
        self.assertEqual(module.classify(["DIRECTOR"]), "Other cargo; inspect")


if __name__ == "__main__":
    unittest.main()
