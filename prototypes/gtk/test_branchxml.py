"""Run on a graphical display with /usr/bin/python3 test_branchxml.py."""
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from branchxml import Gdk, GLib, Gio, Gtk, RecipeWindow, Document


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
    @classmethod
    def setUpClass(cls):
        cls.app = Gtk.Application(flags=Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None)

    def test_undo_from_next_field_after_tab(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "recipe.xml"
            original = b"<r name='a' n='1'><summary><![CDATA[tea]]></summary><end /></r>"
            path.write_bytes(original)
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            win.present()
            wait_for(lambda: win.get_mapped())
            win.request_edit(1)
            for value in ("b", "2", "茶"):
                win.entry.set_text(value)
                win.edit_key(None, Gdk.KEY_Tab, 0, 0)
            self.assertEqual(win.active.name, "end")
            ctrl = Gdk.ModifierType.CONTROL_MASK
            for pos, value in ((3, "tea"), (2, "1"), (1, "a")):
                self.assertTrue(win.history_key(None, Gdk.KEY_z, 0, ctrl))
                self.assertEqual(win.selection.get_selected(), pos)
                self.assertEqual(win.rows.get_item(pos).get_item().value, value)
            for key, mods in ((Gdk.KEY_y, ctrl), (Gdk.KEY_Z, ctrl | Gdk.ModifierType.SHIFT_MASK),
                              (Gdk.KEY_y, ctrl)):
                self.assertTrue(win.history_key(None, key, 0, mods))
            self.assertTrue(win.save())
            self.assertNotEqual(path.read_bytes(), original)
            for _ in range(3):
                win.history_key(None, Gdk.KEY_z, 0, ctrl)
            self.assertTrue(win.save())
            self.assertEqual(path.read_bytes(), original)

    def test_duplicate_edit_delete_and_restore_selection(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "recipe.xml"
            original = b"<r>\n  <task n='1'><s><![CDATA[A&B]]></s></task>\n</r>"
            path.write_bytes(original)
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            win.present()
            wait_for(lambda: win.get_mapped())
            self.assertFalse(win.lookup_action("delete").get_enabled())
            win.selection.set_selected(1)
            ctrl = Gdk.ModifierType.CONTROL_MASK
            win.navigation_key(None, Gdk.KEY_d, 0, ctrl)
            clone_pos = win.selection.get_selected()
            clone = win.selection.get_selected_item().get_item()
            self.assertEqual(clone.path, (0, 1))
            win.request_edit(clone_pos + 1)
            self.assertFalse(win.navigation_key(None, Gdk.KEY_Delete, 0, 0))
            win.entry.set_text("2")
            win.leave(True)
            win.selection.set_selected(clone_pos)
            win.navigation_key(None, Gdk.KEY_Delete, 0, 0)
            win.history_key(None, Gdk.KEY_z, 0, ctrl)
            restored = win.selection.get_selected_item().get_item()
            self.assertEqual((restored.path, restored.children.get_item(0).value), ((0, 1), "2"))
            win.history_key(None, Gdk.KEY_y, 0, ctrl)
            self.assertTrue(win.save())
            win.open_path(path)
            self.assertEqual(win.document.roots.get_item(0).children.get_n_items(), 1)
            self.assertEqual(path.read_bytes(), original)

    def test_tab_cancel_and_recycled_rows(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "recipe.xml"
            original = '<recipe name="测试">' + ''.join(
                f'<step n="{i}"><summary><![CDATA[茶 & 水]]></summary></step>' for i in range(50)
            ) + '</recipe>'
            path.write_text(original, encoding="utf-8")
            win = RecipeWindow(self.app, Document(path))
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

            # Save As includes the still-active field, then Ctrl+S targets the new path.
            win.request_edit(1)
            win.entry.set_text("另存时的值")
            copy = path.with_name("copy.xml")
            self.assertTrue(win.save(copy))
            win.request_edit(1)
            win.entry.set_text("保存时的值")
            win.lookup_action("save").activate(None)
            self.assertIn('name="保存时的值"', copy.read_text(encoding="utf-8"))
            self.assertFalse(win.document.dirty)
            win.open_path(path)
            self.assertEqual(win.rows.get_item(1).get_item().value, "测试")
            self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
