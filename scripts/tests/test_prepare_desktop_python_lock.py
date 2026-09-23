"""Preuve hors réseau de la projection : aucun retrait implicite ni haché perdu."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("desktop_lock", ROOT / "scripts/prepare-desktop-python-lock.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def pin(name: str, version: str = "1.0") -> str:
    return f"{name}=={version} \\\n    --hash=sha256:{'a' * 64}\n"


class DesktopPythonLockTests(unittest.TestCase):
    def test_real_projection_preserves_every_other_pin_and_hash(self):
        source = MODULE.LINUX_LOCK.read_text(encoding="utf-8")
        overlay = MODULE.WINDOWS_OVERLAY.read_text(encoding="utf-8")
        before = MODULE.pinned_blocks(source)
        after = MODULE.pinned_blocks(MODULE.project_lock(source, overlay, "win32"))
        self.assertEqual(set(after), (set(before) - {"uvloop"}) | {"colorama"})
        for name in set(before) - {"uvloop"}:
            self.assertEqual(after[name].rstrip(), before[name].rstrip(), name)

    def test_other_platform_is_rejected(self):
        for platform in ("linux", "darwin", "Windows", ""):
            with self.subTest(platform=platform), self.assertRaises(ValueError):
                MODULE.project_lock(pin("uvloop"), pin("colorama"), platform)

    def test_unexpected_overlay_or_collision_is_rejected(self):
        for source, overlay in ((pin("uvloop"), pin("other")),
                                (pin("uvloop") + pin("colorama"), pin("colorama")),
                                (pin("package"), pin("colorama"))):
            with self.subTest(source=source, overlay=overlay), self.assertRaises(ValueError):
                MODULE.project_lock(source, overlay, "win32")

    def test_unhashed_floating_duplicate_and_directives_are_rejected(self):
        invalid = ("package==1.0\n", "package>=1.0\n", pin("package") + pin("package"),
                   pin("package") + "--extra-index-url https://example.invalid\n",
                   "package==1.0 \\\n    --hash=sha256:" + "a" * 64 + " \\\n",
                   "package==1.0 ; sys_platform == 'win32' \\\n    --hash=sha256:" + "a" * 64 + "\n")
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(ValueError):
                MODULE.pinned_blocks(source)


if __name__ == "__main__":
    unittest.main()
