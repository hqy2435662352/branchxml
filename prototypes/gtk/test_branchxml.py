"""Run on a graphical display with /usr/bin/python3 test_branchxml.py."""
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from branchxml import Gdk, GLib, Gio, Gtk, RecipeWindow, read_rows


def wait_for(condition):
    main = GLib.MainContext.default()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        while main.pending():
            main.iteration(False)
        if condition():
            return
        time.sleep(.01)
    raise AssertionError("GTK did not reach the expected state")


class InputTest(unittest.TestCase):
    def test_tab_cancel_and_recycled_rows(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "recipe.xml"
            original = '<recipe name="测试">' + ''.join(
                f'<step n="{i}"><summary><![CDATA[茶 & 水]]></summary></step>' for i in range(50)
            ) + '</recipe>'
            path.write_text(original, encoding="utf-8")
            app = Gtk.Application(flags=Gio.ApplicationFlags.NON_UNIQUE)
            app.register(None)
            win = RecipeWindow(app, path, read_rows(path))
            self.addCleanup(win.destroy)
            win.present()
            wait_for(lambda: win.get_mapped() and win.get_width() > 0)

            win.request_edit(1)
            wait_for(lambda: win.placed)
            entry = win.entry
            entry.set_text("改好的值")
            win.edit_key(None, Gdk.KEY_Tab, 0, 0)
            self.assertEqual(win.rows.get_item(1).get_item().value, "改好的值")
            self.assertEqual(win.active.name, "@n")
            win.edit_key(None, Gdk.KEY_Tab, 0, 0)
            self.assertEqual(entry.get_text(), "茶 & 水")
            entry.set_text("取消这次修改")
            selected = win.active
            win.edit_key(None, Gdk.KEY_Escape, 0, 0)
            self.assertIsNone(win.active)
            self.assertEqual(selected.value, "茶 & 水")
            win.request_edit(4)
            win.preedit_changed(entry, "拼")
            win.edit_key(None, Gdk.KEY_Tab, 0, 0)
            self.assertIs(win.active, selected)
            win.preedit_changed(entry, "")
            win.edit_key(None, Gdk.KEY_ISO_Left_Tab, 0, Gdk.ModifierType.SHIFT_MASK)
            self.assertEqual(win.active.name, "@n")

            win.request_edit(76)
            wait_for(lambda: win.placed and win.cell_bounds() is not None)
            self.assertIs(win.entry, entry)
            self.assertEqual(win.selection.get_selected(), 76)
            win.entry.set_text("屏幕外的行")
            win.entry.emit("activate")
            self.assertEqual(win.rows.get_item(76).get_item().value, "屏幕外的行")
            self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
