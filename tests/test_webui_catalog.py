from __future__ import annotations

import unittest

from webui.catalog import (
    ART_STYLES,
    DEFAULT_STYLE_ID,
    TARGET_MODES,
    frame_preset,
    public_options,
    requires_custom_grid,
    resolve_style,
)


class WebUiCatalogTests(unittest.TestCase):
    def test_exposes_more_than_twenty_selectable_art_styles(self) -> None:
        self.assertGreaterEqual(len(ART_STYLES), 24)
        options = public_options()
        self.assertEqual(len(options["styles"]), len(ART_STYLES))
        self.assertIn("asset", TARGET_MODES)

    def test_frame_presets_include_dense_animation_and_grid_contract(self) -> None:
        dense = frame_preset(32)
        self.assertEqual((dense["rows"], dense["cols"]), (4, 8))
        self.assertTrue(requires_custom_grid("idle", 32))
        self.assertFalse(requires_custom_grid("idle", 4))

    def test_style_resolution_keeps_preset_and_optional_direction(self) -> None:
        label, prompt = resolve_style(DEFAULT_STYLE_ID, "warm rim light")
        self.assertTrue(label)
        self.assertIn("warm rim light", prompt)


if __name__ == "__main__":
    unittest.main()
