"""Language preferences across fresh application processes."""

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class LanguageTest(unittest.TestCase):
    def test_startup_uses_desktop_preferences_and_saved_override(self):
        with TemporaryDirectory() as config:
            def help_text(language):
                args = [sys.executable, str(Path(__file__).with_name("branchxml.py")), "--help"]
                env = {**os.environ, "XDG_CONFIG_HOME": config, "LANGUAGE": language}
                return subprocess.check_output(args, env=env, text=True)

            self.assertIn("要打开的 XML 文件", help_text("fr:zh_CN:en"))
            self.assertIn("XML file to open", help_text("en:zh_CN"))
            self.assertIn("XML file to open", help_text("fr"))
            pref = Path(config) / "branchxml" / "language"
            pref.parent.mkdir()
            pref.write_text("zh_CN")
            self.assertIn("要打开的 XML 文件", help_text("en"))
            pref.write_text("system")
            self.assertIn("XML file to open", help_text("en"))
            self.assertIn("要打开的 XML 文件", help_text("zh_SG"))
            pref.write_bytes(b"\xff\xff")
            self.assertIn("XML file to open", help_text("en"))


if __name__ == "__main__":
    unittest.main()
