"""Le contrôle statique distingue des fixtures précises des origines et chemins réels."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "desktop_layout", ROOT / "apps/desktop/cmake/check_layout.py"
)
LAYOUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAYOUT)


class DesktopLayoutTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.desktop = self.root / "apps" / "desktop"
        self.desktop.mkdir(parents=True)
        for name, value in (("REPO_ROOT", self.root), ("DESKTOP_ROOT", self.desktop)):
            patched = patch.object(LAYOUT, name, value)
            patched.start()
            self.addCleanup(patched.stop)

    def write(self, relative, content):
        path = self.desktop / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + "\n", encoding="utf-8", newline="\n")

    def network_findings(self):
        findings = LAYOUT.Findings()
        LAYOUT.check_no_hardcoded_origin(findings)
        return findings.items

    def path_findings(self):
        findings = LAYOUT.Findings()
        LAYOUT.check_file_contents(findings)
        return findings.items

    def test_url_userinfo_does_not_hide_the_real_host(self):
        self.write("src/example.cpp", '"https://trusted.invalid@infrastructure.example/api"')
        findings = self.network_findings()
        self.assertEqual(len(findings), 1)
        self.assertIn("infrastructure.example", findings[0])
        self.assertNotIn("(trusted.invalid)", findings[0])

    def test_loopback_regex_is_not_read_as_host_127(self):
        self.write("tests/cpp/example.cpp", r'"^http://127\\.0\\.0\\.1:(\\d+)/rappel$"')
        self.assertEqual(self.network_findings(), [])

    def test_url_fixture_exception_requires_exact_url_and_file(self):
        accepted = next(iter(LAYOUT.NETWORK_URL_FIXTURES["tests/cpp/tst_updates.cpp"]))
        self.write("tests/cpp/tst_updates.cpp", f'"{accepted}"')
        self.assertEqual(self.network_findings(), [])
        self.write("src/example.cpp", f'"{accepted}"')
        self.assertEqual(len(self.network_findings()), 1)
        self.write("tests/cpp/tst_updates.cpp", '"https://github.com/another/endpoint"')
        self.assertEqual(len(self.network_findings()), 2)

    def test_absolute_fixture_exception_requires_exact_path_and_file(self):
        self.write("tests/cpp/tst_sauvegarde.cpp", '"C:/Sauvegardes/h.acpb"')
        self.assertEqual(self.path_findings(), [])
        self.write("src/example.cpp", '"C:/Sauvegardes/h.acpb"')
        self.assertEqual(len(self.path_findings()), 1)
        self.write("tests/cpp/tst_sauvegarde.cpp", '"C:/Users/Paul/local-project"')
        self.assertEqual(len(self.path_findings()), 2)

    def test_real_update_service_origin_is_still_reported(self):
        self.write("src/services/UpdateService.cpp", '"https://api.github.com/repos"')
        findings = self.network_findings()
        self.assertEqual(len(findings), 1)
        self.assertIn("api.github.com", findings[0])

    def test_malformed_origin_is_reported_without_crashing(self):
        self.write("src/example.cpp", '"https://[broken/api"')
        findings = self.network_findings()
        self.assertEqual(len(findings), 1)
        self.assertIn("origine réseau illisible", findings[0])


if __name__ == "__main__":
    unittest.main()
