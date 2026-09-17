"""Run the existing unittest suites, including scenario-local baseline tests."""
from pathlib import Path
import os
import sys
import unittest


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.discover("tests"))
    suite.addTests(loader.discover("scenarios/tests", top_level_dir="."))
    local_tests = set(Path("scenarios").glob("*/*/test_*.py"))
    local_tests.update(Path("scenarios").glob("*/*/tests/test_*.py"))
    # Real-application recording pilots live one level deeper, under an underscore-prefixed
    # container that scenario discovery deliberately skips. Pick up their standard-library tests
    # with a narrowly scoped pattern; this does not affect scenario contract discovery.
    local_tests.update(Path("scenarios").glob("financial-services/_recordings/*/test_*.py"))
    for path in sorted(local_tests):
        suite.addTests(loader.loadTestsFromName(".".join(path.with_suffix("").parts)))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
