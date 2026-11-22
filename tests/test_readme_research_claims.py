"""Regression checks for README research-claim status. No treatments or evaluations."""
from pathlib import Path
import unittest

README = Path(__file__).resolve().parents[1] / "README.md"


def section(doc, start, end):
    return doc.split(start + "\n", 1)[1].split(end + "\n", 1)[0]


class ReadmeResearchClaimsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = README.read_text(encoding="utf-8")

    def test_retained_outputs_do_not_assert_original_source_authenticity(self):
        status = section(self.doc, "## Research status", "## Experimental design")
        self.assertIn("original reports/traces **not independently authenticated**", status)
        self.assertIn("Pending original-source authentication", status)
        self.assertIn("an access and custody gap", status)
        self.assertIn("Authenticated blinded distribution", status)
        self.assertNotIn("provenance-verified, and preserved", status)

    def test_fixed_order_is_not_randomized_causal_evidence(self):
        design = section(self.doc, "## Experimental design", "## Research pipeline")
        outcomes = section(self.doc, "## What is measured", "## Human evaluation")
        self.assertIn("do not isolate causal effects", design)
        self.assertIn("exact sign-flip p-values", outcomes)
        self.assertIn("not design-based randomization-test evidence", outcomes)
        self.assertIn("sign exchangeability has not been established", outcomes)
        self.assertNotIn("sign-flip/randomization p-values", outcomes)

    def test_postcollection_freeze_and_required_covers_are_discoverable(self):
        status = section(self.doc, "## Research status", "## Experimental design")
        map_text = section(self.doc, "## Reproducibility map", "## Core agent capabilities")
        rules = section(self.doc, "## Research integrity rules", "## Limitations and threats to validity")
        self.assertIn("paper/MAIN_STUDY_REPORTING_COVER.md", status)
        self.assertIn("docs/MAIN_STUDY_QUALIFIED_REPORTING.md", status)
        self.assertIn("committed after treatment and evaluator recovery", map_text)
        self.assertIn("reporting requires the qualification cover", map_text)
        self.assertNotIn("Frozen confirmatory main-study inference", map_text)
        self.assertIn("Prospective precollection statistical preregistration", rules)
        self.assertIn("not established", rules)

    def test_scientific_claim_stages_are_kept_distinct(self):
        status = section(self.doc, "## Research status", "## Experimental design")
        self.assertIn("The five-task pilot is diagnostic", status)
        self.assertIn("later sensitivity analyses are exploratory", status)
        self.assertIn("human validation is pending", status)


if __name__ == "__main__":
    unittest.main()
