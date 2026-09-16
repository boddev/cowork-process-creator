import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from scenarios._shared.contract import load_scenario
from scenarios._shared.pipeline import baseline_environment, run_case
from scenarios.tests.fixtures import make_scenario, temporary_directory


class BaselineEnvironmentTests(unittest.TestCase):
    def test_preserves_os_directories_without_tokens_or_python_search_paths(self):
        values = {
            "SystemRoot": "os-root",
            "SystemDrive": "os-drive",
            "USERPROFILE": "profile",
            "LOCALAPPDATA": "local-data",
            "APPDATA": "app-data",
            "ProgramData": "program-data",
            "ALLUSERSPROFILE": "all-profiles",
            "HOMEDRIVE": "home-drive",
            "HOMEPATH": "home-path",
            "TEMP": "temporary",
            "PYTHONPATH": "untrusted-import-location",
            "GH_TOKEN": "do-not-inherit",
            "AZURE_CLIENT_SECRET": "do-not-inherit",
            "PATH": "not-needed-for-explicit-interpreter",
        }
        with mock.patch.dict(os.environ, values, clear=True):
            actual = baseline_environment()
        self.assertEqual({key.upper(): value for key, value in actual.items()}, {key.upper(): value for key, value in values.items()
                                  if key not in {"PYTHONPATH", "GH_TOKEN", "AZURE_CLIENT_SECRET", "PATH"}})

    @unittest.skipUnless(sys.platform == "win32", "Windows Store Python directory regression")
    def test_actual_windows_baseline_has_no_unexpanded_environment_cache_tree(self):
        with temporary_directory() as directory:
            root = make_scenario(Path(directory) / "scenarios")
            scenario = load_scenario(root)
            report = run_case(scenario, scenario.case("demo"))
            self.assertEqual(report["state"], "baseline_pass", report["errors"])
            self.assertEqual(report["execution"]["python_version"], ".".join(map(str, sys.version_info[:3])))
            self.assertEqual(report["execution"]["platform"], "win32")
            self.assertNotIn(str(root), str(report["execution"]))
            self.assertEqual(report["execution"]["command"][3], "baseline.py")
            self.assertFalse(any("%" in path.name for path in root.rglob("*")),
                             "OS directory environment must not become a literal scenario path")
            self.assertFalse(list(root.rglob("*.db")))


if __name__ == "__main__":
    unittest.main()
