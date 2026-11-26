"""Per-user font size preference validation and persistence."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import appearance


class FontSizeTest(unittest.TestCase):
    def test_missing_corrupt_and_out_of_range_preferences(self):
        with TemporaryDirectory() as temp:
            preference = Path(temp) / "branchxml" / "font-size"
            with patch.object(appearance, "font_size_file", return_value=preference):
                self.assertEqual(appearance.load_font_size(), appearance.DEFAULT_FONT_SIZE)
                preference.parent.mkdir()
                for invalid in ("not a size", "12.5", "\xff".encode()):
                    preference.write_bytes(invalid if isinstance(invalid, bytes) else invalid.encode("ascii"))
                    self.assertEqual(appearance.load_font_size(), appearance.DEFAULT_FONT_SIZE)
                for text, expected in (("1", appearance.MIN_FONT_SIZE),
                                       ("9", appearance.MIN_FONT_SIZE),
                                       ("28", appearance.MAX_FONT_SIZE),
                                       ("999", appearance.MAX_FONT_SIZE)):
                    preference.write_text(text)
                    self.assertEqual(appearance.load_font_size(), expected)

    def test_save_clamps_and_loads_the_persisted_size(self):
        with TemporaryDirectory() as temp:
            preference = Path(temp) / "branchxml" / "font-size"
            with patch.object(appearance, "font_size_file", return_value=preference):
                for requested, expected in ((8, 9), (15, 15), (45, 28)):
                    self.assertEqual(appearance.save_font_size(requested), expected)
                    self.assertEqual(preference.read_text(encoding="ascii"), f"{expected}\n")
                    self.assertEqual(appearance.load_font_size(), expected)
                with self.assertRaises(TypeError):
                    appearance.save_font_size(True)
                with self.assertRaises(TypeError):
                    appearance.save_font_size(12.5)


if __name__ == "__main__":
    unittest.main()
