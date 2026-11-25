"""Run on a graphical display with /usr/bin/python3 test_branchxml.py."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import time
import unittest

from branchxml import Gdk, GLib, Gio, Gtk, RecipeWindow, Document


def wait_for(condition):
    main = GLib.MainContext.default()
    deadline = time.monotonic() + 8  # A throttled Wayland window can take several seconds to lay out a row.
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

    def test_source_preview_checks_and_address_bar(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "one.xml"
            original = b"<r><!--note--><value>10</value></r>"
            path.write_bytes(original)
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            win.present()
            wait_for(lambda: win.get_mapped())
            self.assertFalse(win.lookup_action("undo").get_enabled())
            win.request_edit(2)
            win.entry.set_text("茶 & 水")
            win.pages.set_current_page(1)
            buf = win.source.buffer
            self.assertIn("茶 &amp; 水", buf.get_text(*buf.get_bounds(), False))
            self.assertEqual(path.read_bytes(), original)
            win.lookup_action("check").activate(None)
            self.assertEqual(win.inspector.result[0].get_text(), "XML 格式正确")
            win.pages.set_current_page(0)
            win.request_edit(1)
            win.entry.set_text("a--b")
            win.check_xml()
            self.assertIn("--", win.inspector.result[0].get_text())
            self.assertEqual(path.read_bytes(), original)
            for _ in range(2):
                win.lookup_action("undo").activate(None)
            self.assertFalse(win.document.dirty)

            other = path.with_name("two.xml")
            other.write_text("<other/>", encoding="utf-8")
            win.pages.set_current_page(1)
            win.chrome.address.set_text(other.name)
            win.chrome.address.emit("activate")
            self.assertEqual(win.document.path, other)
            self.assertEqual(win.chrome.address.get_text(), str(other))
            self.assertEqual(buf.get_text(*buf.get_bounds(), False), "<other/>")

            invalid = path.with_name("invalid.xml")
            invalid.write_text("<root>\n</wrong>", encoding="utf-8")
            with patch.object(win, "show_error") as alert:
                win.open_path(invalid)
                alert.assert_called_once()
            self.assertEqual(win.document.path, other)
            self.assertEqual(win.inspector.result[1].get_text(), invalid.name)
            self.assertEqual(win.inspector.result[2].get_text(), "2")

    def test_nested_expansion_survives_closing_ancestors(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "recipe.xml"
            task = "<task><params><param n='1'/><param n='2'/></params></task>"
            path.write_text("<recipe><tasks>" + task * 2 + "</tasks></recipe>")
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            win.present()
            root = win.rows.get_child_row(0)
            tasks = root.get_child_row(0)
            first, second = tasks.get_child_row(0), tasks.get_child_row(1)
            first.get_child_row(0).set_expanded(False)
            first.set_expanded(False)
            second.get_child_row(0).get_child_row(1).set_expanded(False)

            def visible():
                return [(r.get_item().path, r.get_expanded()) for r in win.rows]

            before = visible()
            for parent in (tasks, root, root):
                parent.set_expanded(False)
                parent.set_expanded(True)
                self.assertEqual(visible(), before)
            first = root.get_child_row(0).get_child_row(0)
            first.set_expanded(True)
            self.assertFalse(first.get_child_row(0).get_expanded())
            first.get_child_row(0).set_expanded(True)
            self.assertTrue(first.get_child_row(0).get_child_row(1).get_expanded())
            self.assertFalse(win.document.dirty)
            self.assertFalse(win.document.undo_stack)

    def test_source_colors_and_literal_search(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "recipe.xml"
            xml = ("<?xml version='1.0' encoding=\"UTF-8\"?>\r\n"
                   "<配方 地点='导航.A' n=\"42\" enabled='true'>\r\n"
                   "<task>导航.a &amp; 水</task><!-- <假 值='42'/> -->\r\n"
                   "<summary><![CDATA[起点:导航.A <标记>]]></summary></配方>\r\n")
            path.write_bytes(xml.encode())
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            win.present()
            win.lookup_action("find-source").activate(None)
            page = win.source
            buf = page.buffer
            self.assertEqual(win.pages.get_current_page(), 1)
            self.assertEqual(buf.get_text(*buf.get_bounds(), True), xml)

            def has_tag(offset, name):
                return buf.get_iter_at_offset(offset).has_tag(buf.get_tag_table().lookup(name))

            wait_for(lambda: has_tag(xml.rindex("</配方"), "element"))
            for token, tag in (("encoding", "attribute"), ("UTF-8", "string"),
                               ("配方", "element"), ("地点", "attribute"), ("导航.A", "string"),
                               ("42", "number"), ("true", "boolean"), ("水", "string"),
                               ("&amp;", "markup"), ("假", "comment"), ("CDATA", "markup"),
                               ("<标记>", "string")):
                self.assertTrue(has_tag(xml.index(token), tag), token)
            positions = (xml.index("导航.A"), xml.index("导航.a"), xml.rindex("导航.A"))
            page.search_entry.set_text("导航.a")
            for pos in positions:
                self.assertTrue(has_tag(pos, "match"))
            self.assertEqual(page.count.get_text(), "1 / 3")
            page.search_entry.emit("activate")
            self.assertTrue(has_tag(positions[1], "current-match"))
            page.search_key(None, Gdk.KEY_F3, 0, Gdk.ModifierType.SHIFT_MASK)
            page.buttons[0].emit("clicked")
            self.assertTrue(has_tag(positions[2], "current-match"))
            page.search_key(None, Gdk.KEY_F3, 0, 0)
            self.assertEqual(page.count.get_text(), "1 / 3")
            page.search_entry.set_text("导航.*")
            self.assertEqual(page.count.get_text(), "无匹配")
            self.assertFalse(page.buttons[1].get_sensitive())
            self.assertFalse(has_tag(positions[0], "match"))

            page.search_entry.set_text("导航")
            win.pages.set_current_page(0)
            win.request_edit(1)
            win.entry.set_text("新站点")
            win.find_source()
            self.assertEqual(page.count.get_text(), "1 / 2")
            self.assertTrue(has_tag(page.xml.index("新站点"), "string"))
            win.lookup_action("undo").activate(None)
            self.assertEqual(page.count.get_text(), "1 / 3")
            page.search_entry.emit("stop-search")
            self.assertEqual(page.search_entry.get_text(), "")
            self.assertFalse(has_tag(positions[0], "current-match"))
            self.assertTrue(has_tag(positions[0], "string"))
            self.assertFalse(win.document.dirty)
            self.assertEqual(path.read_bytes(), xml.encode())

    def test_open_another_file_while_source_highlights_are_pending(self):
        with TemporaryDirectory() as temp:
            one, two = Path(temp) / "one.xml", Path(temp) / "two.xml"
            one.write_text("<a>" + "<v>old</v>" * 2000 + "</a>")
            two.write_text("<next key='新值'/>")
            win = RecipeWindow(self.app, Document(one))
            self.addCleanup(win.destroy)
            win.present()
            win.find_source()
            page = win.source
            page.search_entry.set_text("old")
            self.assertEqual(page.count.get_text(), "1 / 2000")
            win.open_path(two)
            self.assertEqual(page.search_entry.get_text(), "")
            page.search_entry.set_text("新值")
            buf = page.buffer
            wait_for(page.view.get_mapped)
            clock = page.view.get_frame_clock()
            frame = clock.get_frame_counter()
            page.view.queue_draw()
            wait_for(lambda: clock.get_frame_counter() > frame)
            last = buf.get_iter_at_offset(page.xml.index("新值"))
            self.assertTrue(last.has_tag(page.current_hit))
            self.assertFalse(buf.get_start_iter().has_tag(page.hit))
            self.assertEqual(page.count.get_text(), "1 / 1")
            self.assertEqual(buf.get_text(*buf.get_bounds(), True), two.read_text())

    def test_context_menu_targets_clicked_row(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "recipe.xml"
            original = b"<r><task n='1'/><task n='2'/></r>"
            path.write_bytes(original)
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            win.present()
            target = win.document.roots.get_item(0).children.get_item(1)
            wait_for(lambda: target in win.cells and win.cells[target].get_height() > 0)
            win.selection.set_selected(1)
            label = win.cells[target]
            _, y = label.translate_coordinates(win.view, 0, label.get_height() / 2)
            gesture = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
            win.context_pressed(gesture, 1, 10, y)
            self.assertTrue(win.node_menu.get_visible())
            self.assertIs(win.selection.get_selected_item().get_item(), target)
            self.assertTrue(win.lookup_action("move-up").get_enabled())
            self.assertFalse(win.lookup_action("move-down").get_enabled())
            win.lookup_action("move-up").activate(None)
            self.assertEqual(win.document.render(), b"<r><task n='2'/><task n='1'/></r>")
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
