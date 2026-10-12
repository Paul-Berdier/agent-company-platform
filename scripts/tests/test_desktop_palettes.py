"""Contrastes des quatre variantes natives et refus d'une palette incomplète."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOKENS = ROOT / "design" / "tokens"
SPEC = importlib.util.spec_from_file_location(
    "desktop_tokens", ROOT / "apps/desktop/cmake/generate_design_tokens.py"
)
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


def contrast(first: str, second: str) -> float:
    def luminance(value: str) -> float:
        channels = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
                  for x in channels]
        return sum(x * weight for x, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    low, high = sorted((luminance(first), luminance(second)))
    return (high + 0.05) / (low + 0.05)


class DesktopPalettesTest(unittest.TestCase):
    def test_text_controls_and_status_contrasts_in_every_variant(self):
        families = json.loads((TOKENS / "desktop-palettes.json").read_text(encoding="utf-8"))["families"]
        for family, palette in families.items():
            for mode in ("dark", "light"):
                colors = {key: value[mode] for key, value in palette["colors"].items()}
                status = {key: value[mode] for key, value in palette["semantic-status"].items()}
                surfaces = [key for key in colors if key.startswith("surface.")
                            and key != "surface.scrimless"]
                pairs = []
                for text in ("text.primary", "text.secondary", "text.muted"):
                    for surface in surfaces:
                        pairs.append((text, surface, colors[text], colors[surface], 4.5))
                for accent in ("accent.primary", "accent.hover", "accent.pressed"):
                    pairs.append(("text.onAccent", accent, colors["text.onAccent"], colors[accent], 4.5))
                pairs.append(("text.onSecondary", "accent.secondary", colors["text.onSecondary"],
                              colors["accent.secondary"], 4.5))
                for border in ("border.interactive", "border.focus"):
                    for surface in surfaces:
                        pairs.append((border, surface, colors[border], colors[surface], 3.0))
                for key, value in status.items():
                    if key.endswith(".foreground"):
                        for surface in ("surface.canvas", "surface.panel", "surface.panelRaised", "surface.sunken"):
                            pairs.append((key, surface, value, colors[surface], 4.5))
                        pairs.append((key, "tint", value, status[key.replace("foreground", "tint")], 4.5))
                    elif key.endswith(".border"):
                        pairs.append((key, "surface.panel", value, colors["surface.panel"], 3.0))
                for foreground, background, first, second, minimum in pairs:
                    with self.subTest(family=family, mode=mode, foreground=foreground, background=background):
                        self.assertGreaterEqual(contrast(first, second), minimum)

    def test_missing_variant_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "tokens"
            shutil.copytree(TOKENS, copied)
            path = copied / "desktop-palettes.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            del document["families"]["pixel"]["colors"]["surface.canvas"]["light"]
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(GENERATOR.GenerationError):
                GENERATOR.render_all(copied)

    def test_generated_qml_is_current(self):
        for name, content in GENERATOR.render_all(TOKENS).items():
            with self.subTest(file=name):
                path = ROOT / "apps/desktop/qml/theme/generated" / name
                self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_web_keeps_the_original_palette(self):
        # load_tokens est aussi consommé par le générateur Hermes ; les surcharges sont natives.
        colors = GENERATOR.load_tokens(TOKENS, "colors")
        self.assertNotIn("$desktopPalettes", colors)
        self.assertEqual(colors["tokens"]["surface.canvas"]["dark"], "#191c1a")


if __name__ == "__main__":
    unittest.main()
