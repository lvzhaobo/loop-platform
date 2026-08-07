"""Page-contract checker regression tests."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.checkers.pages import PagesChecker


class TestPagesChecker(unittest.TestCase):
    def test_valid_navigation_passes_and_dead_link_fails(self):
        contract = {
            "schema_version": 2,
            "entry": "index.html",
            "pages": [
                {"id": "home", "file": "index.html", "entry": True},
                {"id": "merge", "file": "merge-sort.html"},
            ],
            "navigation": [{"from": "index.html", "to": "merge-sort.html"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            acceptance = root / "acceptance.json"
            acceptance.write_text(json.dumps(contract), encoding="utf-8")
            (root / "index.html").write_text('<a href="merge-sort.html">Merge</a>', encoding="utf-8")
            (root / "merge-sort.html").write_text('<a href="index.html">Home</a>', encoding="utf-8")
            passed = PagesChecker().check(directory, acceptance_path=str(acceptance))
            self.assertTrue(passed.all_pass)

            (root / "index.html").write_text('<a href="missing.html">Merge</a>', encoding="utf-8")
            failed = PagesChecker().check(directory, acceptance_path=str(acceptance))
            self.assertFalse(failed.all_pass)
            self.assertTrue(any(item["name"] == "链接存在:index.html→missing.html" and not item["pass"]
                                for item in failed.checks))


if __name__ == "__main__":
    unittest.main()
