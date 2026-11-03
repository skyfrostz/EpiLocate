import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "check_project_documentation.py"
SPEC = importlib.util.spec_from_file_location("check_project_documentation", SCRIPT)
CHECKER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CHECKER)


class DocumentationCheckerTests(unittest.TestCase):
    def run_checker(self, paths, *arguments):
        output = io.StringIO()
        argv = [str(SCRIPT), "--base", "p0/integration", *arguments]
        with patch.object(CHECKER, "changed_paths", return_value=set(paths)):
            with patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(output):
                    code = CHECKER.main()
        return code, output.getvalue()

    def test_documentation_only_change_passes(self):
        code, output = self.run_checker(
            ["docs/project/DOCUMENTATION_GUIDE.md", "AGENTS.md"]
        )
        self.assertEqual(code, 0)
        self.assertIn("documentation-only", output)

    def test_engineering_change_without_logs_fails(self):
        code, output = self.run_checker(["backend_v2/api/app.py"])
        self.assertEqual(code, 1)
        self.assertIn("ITERATION_HISTORY.md", output)
        self.assertIn("ENGINEERING_JOURNAL.md", output)

    def test_engineering_change_with_both_logs_passes(self):
        code, output = self.run_checker(
            [
                "backend_v2/api/app.py",
                "docs/project/ITERATION_HISTORY.md",
                "docs/project/ENGINEERING_JOURNAL.md",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("PASS", output)


if __name__ == "__main__":
    unittest.main()
