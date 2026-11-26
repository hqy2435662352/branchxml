"""Run on a graphical display with /usr/bin/python3 test_branchxml.py."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import time
import unittest

from branchxml import Gdk, GLib, Gio, Gtk, RecipeWindow, Document
import appearance
import i18n
import theme
from i18n import tr


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

    def test_find_hidden_values_replace_undo_and_multiline(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "recipe.xml"
            original = "<r><task><summary>终点 LM2</summary><param value='LM2'/></task><other><v/></other></r>".encode()
            path.write_bytes(original)
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            win.present()
            wait_for(win.get_mapped)
            root = win.rows.get_child_row(0)
            task, other = root.get_child_row(0), root.get_child_row(1)
            task.set_expanded(False)
            other.set_expanded(False)
            win.lookup_action("find").activate(None)
            bar = win.tree_find
            bar.entry.set_text("lm2")
            self.assertEqual(bar.count.get_text(), "1 / 2")
            self.assertTrue(task.get_expanded())
            self.assertFalse(other.get_expanded())
            bar.key_pressed(None, Gdk.KEY_F3, 0, 0)
            self.assertEqual(win.selection.get_selected_item().get_item().name, "@value")
            bar.entry.emit("stop-search")
            win.navigation_key(None, Gdk.KEY_F2, 0, 0)
            win.entry.set_text("LM3")
            win.edit_key(None, Gdk.KEY_Tab, 0, 0)
            win.history(False)
            win.lookup_action("replace").activate(None)
            bar.replacement.set_text("站点")
            bar.replace_all.emit("clicked")
            self.assertIn("<summary>终点 站点</summary><param value='站点'/>", win.document.render().decode())
            win.history(False)
            self.assertEqual(win.document.render(), original)
            bar.close()
            summary = task.get_child_row(0).get_item()
            win.reveal(summary, focus=True)
            win.lookup_action("multiline").activate(None)
            dialog = next(w for w in Gtk.Window.get_toplevels() if isinstance(w, Gtk.Dialog))
            text = dialog.get_content_area().get_first_child().get_child()
            text.get_buffer().set_text("第一行\n第二行")
            dialog.response(Gtk.ResponseType.CANCEL)
            self.assertEqual(win.document.render(), original)
            win.edit_multiline(summary)
            dialog = next(w for w in Gtk.Window.get_toplevels() if isinstance(w, Gtk.Dialog))
            dialog.get_content_area().get_first_child().get_child().get_buffer().set_text("一\n二")
            dialog.response(Gtk.ResponseType.OK)
            self.assertIn("一\n二", win.document.render().decode())
            self.assertFalse(other.get_expanded())

    def test_tree_clipboard_actions_and_unsaved_document(self):
        with TemporaryDirectory() as temp:
            win = RecipeWindow(self.app, Document())
            self.addCleanup(win.destroy)
            win.present()
            wait_for(win.get_mapped)
            self.assertEqual(win.chrome.address.get_text(), "")
            with patch.object(win, "choose_file") as choose:
                win.lookup_action("save").activate(None)
                choose.assert_called_once_with(True)
            root = win.document.roots.get_item(0)
            win.change_node(root, "child", "sample")
            win.lookup_action("copy").activate(None)
            win.reveal(win.document.roots.get_item(0), focus=True)
            win.lookup_action("paste").activate(None)
            wait_for(lambda: win.document.roots.get_item(0).children.get_n_items() == 2)
            win.lookup_action("cut").activate(None)
            self.assertEqual(win.document.roots.get_item(0).children.get_n_items(), 1)
            win.history(False)
            path = Path(temp) / "new file.xml"
            self.assertTrue(win.save(path))
            self.assertIn(b"<sample/><sample/>", path.read_bytes())
            win.lookup_action("new").activate(None)
            self.assertIsNone(win.document.path)

    def test_close_untitled_only_after_first_save_succeeds(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "新 配方.xml"
            win = RecipeWindow(self.app, Document())
            self.addCleanup(win.destroy)
            win.present()
            wait_for(win.get_mapped)
            win.document.edit(win.document.roots.get_item(0), "保存内容")

            def respond(dialog, parent, cancellable, callback):
                callback(dialog, None)

            cancelled = GLib.Error.new_literal(Gtk.DialogError.quark(), "cancel", Gtk.DialogError.DISMISSED)
            with (patch.object(Gtk.AlertDialog, "choose", respond),
                  patch.object(Gtk.AlertDialog, "choose_finish", return_value=2),
                  patch.object(Gtk.FileDialog, "save", respond),
                  patch.object(Gtk.FileDialog, "save_finish", side_effect=[cancelled, Gio.File.new_for_path(str(path))])):
                win.lookup_action("close").activate(None)
                self.assertTrue(win.get_visible() and win.document.dirty)
                self.assertFalse(path.exists())
                win.lookup_action("close").activate(None)
                wait_for(lambda: not win.get_visible())
                self.assertIn("<root>保存内容</root>", path.read_text())

    def test_xpath_and_schema_diagnostics_use_current_values(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "sample.xml"
            path.write_text("<r>\n<n>bad</n>\n<n>wrong</n>\n</r>")
            schema = path.with_suffix(".xsd")
            schema.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="r"><xs:complexType><xs:sequence><xs:element name="n" type="xs:int" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element></xs:schema>')
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            win.present()
            wait_for(win.get_mapped)
            win.lookup_action("xpath").activate(None)
            win.tree_find.entry.set_text("//n[2]")
            win.tree_find.entry.emit("activate")
            self.assertEqual(win.selection.get_selected_item().get_item().value, "wrong")
            win.tree_find.close()
            win.attach_schema(schema)
            self.assertEqual((win.inspector.first_line, win.inspector.extra_rows), (2, 1))
            win.inspector.jump.emit("clicked")
            self.assertEqual(win.pages.get_current_page(), 1)
            buf = win.source.buffer
            self.assertEqual(buf.get_iter_at_mark(buf.get_insert()).get_line(), 1)
            win.pages.set_current_page(0)
            for index in (1, 2):
                win.request_edit(index)
                win.entry.set_text("42")
                win.leave(True)
            wait_for(lambda: win.inspector.result[0].get_text() == tr("XML matches the schema"))
            self.assertEqual(win.inspector.extra_rows, 0)
            self.assertIn("wrong", path.read_text())
            win.set_document(Document())
            self.assertFalse(win.lookup_action("clear-schema").get_enabled())

    def test_regex_and_tree_source_positions_after_unicode_edit(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "图.xml"
            path.write_bytes("\ufeff<r name='茶'><a id='LM2'/><b>lm34</b></r>\r\n".encode())
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            win.present()
            wait_for(win.get_mapped)
            win.request_edit(1)
            win.entry.set_text("茶和薄荷")
            win.leave(True)
            win.find(replacing=True)
            bar = win.tree_find
            bar.regex.set_active(True)
            bar.case.set_active(True)
            bar.entry.set_text(r"LM(\d+)")
            self.assertEqual(len(bar.matches), 1)
            bar.case.set_active(False)
            self.assertEqual(len(bar.matches), 2)
            bar.replacement.set_text(r"站\1")
            bar.replace(True)
            self.assertIn(b"<b>" + "站34".encode() + b"</b>", win.document.xml_bytes())
            win.history(False)
            bar.entry.set_text("[")
            self.assertFalse(bar.matches)
            bar.regex.set_active(False)
            bar.entry.set_text("LM2")
            bar.close()
            attr = win.selection.get_selected_item().get_item()
            win.lookup_action("locate").activate(None)
            buf = win.source.buffer
            self.assertEqual(buf.get_text(*buf.get_selection_bounds(), False), "id='LM2'")
            pos = win.source.xml.index("LM2") + 1
            buf.place_cursor(buf.get_iter_at_offset(pos))
            win.lookup_action("locate").activate(None)
            self.assertIs(win.selection.get_selected_item().get_item(), attr)
            win.navigation_key(None, Gdk.KEY_Left, 0, 0)
            self.assertEqual(win.selection.get_selected_item().get_item().name, "a")
            win.navigation_key(None, Gdk.KEY_Right, 0, 0)
            self.assertIs(win.selection.get_selected_item().get_item(), attr)

    def test_ctrl_wheel_changes_shared_font_size(self):
        with (TemporaryDirectory() as temp,
              patch.object(appearance, "font_size_file", return_value=Path(temp) / "font-size")):
            win = RecipeWindow(self.app, Document())
            self.addCleanup(win.destroy)
            for page, unit, notch in ((win.tree_page, Gdk.ScrollUnit.WHEEL, 1),
                                      (win.source, Gdk.ScrollUnit.SURFACE, 10)):
                wheel = next(c for c in page.observe_controllers() if isinstance(c, Gtk.EventControllerScroll))
                self.assertEqual(wheel.get_propagation_phase(), Gtk.PropagationPhase.CAPTURE)
                self.assertFalse(wheel.emit("scroll", 0.0, -1.0))
                with (patch.object(wheel, "get_current_event_state", return_value=Gdk.ModifierType.CONTROL_MASK),
                      patch.object(wheel, "get_unit", return_value=unit)):
                    self.assertFalse(wheel.emit("scroll", 1.0, 0.0))
                    wheel.emit("scroll", 0.0, -notch / 2)
                    wheel.emit("scroll-end")
                    for expected in (12, 13):
                        self.assertTrue(wheel.emit("scroll", 0.0, -notch / 2))
                        self.assertEqual(win.font_size, expected)
                    self.assertTrue(wheel.emit("scroll", 0.0, 3 * notch))
                    self.assertEqual(appearance.load_font_size(), 10)
                    self.assertTrue(wheel.emit("scroll", 0.0, -2 * notch))
                    self.assertEqual(win.font_size, 12)

    def test_font_size_scales_document_and_keeps_pending_edit(self):
        with (TemporaryDirectory() as temp,
              patch.object(appearance, "font_size_file", return_value=Path(temp) / "font-size")):
            path = Path(temp) / "recipe.xml"
            original = ("<r>" + "<step>配方</step>" * 100 + "</r>").encode()
            path.write_bytes(original)
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            win.present()
            win.lookup_action("source").activate(None)
            source = win.source.view

            def source_height():
                return source.get_iter_location(win.source.buffer.get_start_iter()).height

            wait_for(lambda: source.get_width() > 0 and source_height() > 0)
            default_source_height = source_height()
            win.lookup_action("tree").activate(None)
            wait_for(lambda: win.view.get_mapped() and win.view.get_height() > 0)
            win.request_edit(70)
            wait_for(lambda: win.placed)
            row = win.active
            label = win.cells[row]
            editor = win.entry.get_delegate()

            def width(widget):
                return widget.create_pango_layout("配方 Recipe").get_pixel_size()[0]

            label_width, editor_width = width(label), width(editor)
            win.entry.set_text("暂未提交")
            for _ in range(appearance.DEFAULT_FONT_SIZE, appearance.MAX_FONT_SIZE):
                win.lookup_action("font-increase").activate(None)
            wait_for(lambda: width(label) > label_width and width(editor) > editor_width)
            self.assertFalse(win.lookup_action("font-increase").get_enabled())
            self.assertEqual(win.entry.get_text(), "暂未提交")
            self.assertIs(win.active, row)
            win.edit_key(None, Gdk.KEY_Escape, 0, 0)
            win.lookup_action("source").activate(None)
            wait_for(lambda: source_height() > default_source_height)
            for _ in range(appearance.MIN_FONT_SIZE, appearance.MAX_FONT_SIZE):
                win.lookup_action("font-decrease").activate(None)
            wait_for(lambda: source_height() < default_source_height)
            self.assertFalse(win.lookup_action("font-decrease").get_enabled())
            self.assertEqual(appearance.load_font_size(), appearance.MIN_FONT_SIZE)
            win.lookup_action("font-reset").activate(None)
            self.assertFalse(win.lookup_action("font-reset").get_enabled())
            self.assertEqual(appearance.load_font_size(), appearance.DEFAULT_FONT_SIZE)
            self.assertFalse(win.document.dirty)
            self.assertEqual(win.document.render(), original)

    def test_theme_action_preserves_edits_and_recolors_source_matches(self):
        with (TemporaryDirectory() as temp,
              patch.object(theme, "preference_file", return_value=Path(temp) / "theme")):
            path = Path(temp) / "recipe.xml"
            original = "<recipe name='茶'><task>热水</task></recipe>".encode()
            path.write_bytes(original)
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            win.present()
            wait_for(win.get_mapped)
            manager = self.app.theme_manager
            initial_choice = manager.preference
            try:
                win.activate_action("win.theme", GLib.Variant("s", "light"))
                win.request_edit(1)
                wait_for(lambda: win.placed)
                win.entry.set_text("草稿")
                win.activate_action("win.theme", GLib.Variant("s", "dark"))
                self.assertTrue(win.dark)
                self.assertEqual(win.entry.get_text(), "草稿")
                self.assertIsNotNone(win.active)
                win.edit_key(None, Gdk.KEY_Escape, 0, 0)
                win.find_source()
                source = win.source
                source.search_entry.set_text("task")
                matches = list(source.matches)
                self.assertEqual(len(matches), 2)
                dark_highlight = source.current_hit.props.background_rgba.to_string()
                second = RecipeWindow(self.app, Document())
                self.addCleanup(second.destroy)
                self.assertTrue(second.dark)
                second.activate_action("win.theme", GLib.Variant("s", "light"))
                self.assertFalse(win.dark)
                self.assertEqual(win.lookup_action("theme").get_state().get_string(), "light")
                self.assertNotEqual(source.current_hit.props.background_rgba.to_string(), dark_highlight)
                self.assertEqual(source.matches, matches)
                self.assertEqual(theme.read_preference(), "light")
                self.assertFalse(win.document.dirty)
                self.assertEqual(win.document.render(), original)
            finally:
                manager.set_preference(initial_choice)

    def test_language_menu_preserves_edits_tree_state_and_search(self):
        with (TemporaryDirectory() as temp,
              patch.object(i18n, "preference_file", return_value=Path(temp) / "config" / "language"),
              patch.object(i18n, "preference", i18n.preference),
              patch.object(i18n, "_catalog", i18n._catalog)):
            i18n.select_language("en")
            path = Path(temp) / "recipe.xml"
            original = "<r name='File'><task>Save</task><group><子项/></group></r>".encode()
            path.write_bytes(original)
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            win.present()
            wait_for(win.get_mapped)
            group = win.rows.get_item(3)
            group.set_expanded(False)
            win.request_edit(1)
            win.entry.set_text("茶 & water")
            win.activate_action("win.language", GLib.Variant("s", "zh_CN"))
            self.assertEqual((win.name_column.get_title(), win.value_column.get_title()), ("节点", "值"))
            self.assertEqual(win.pages.get_tab_label_text(win.source), "XML 源码")
            self.assertEqual(win.inspector.result[0].get_text(), "XML 格式正确")
            self.assertEqual(win.lookup_action("language").get_state().get_string(), "zh_CN")
            view = win.chrome.menu_bar.get_menu_model().get_item_link(2, Gio.MENU_LINK_SUBMENU)
            last = view.get_n_items() - 1
            self.assertEqual(view.get_item_attribute_value(last, "label", None).get_string(), "语言")
            languages = view.get_item_link(last, Gio.MENU_LINK_SUBMENU)
            self.assertEqual(languages.get_item_attribute_value(0, "label", None).get_string(), "跟随系统")
            menu = win.node_menu.get_menu_model()
            labels = {
                menu.get_item_attribute_value(i, "action", None).get_string():
                menu.get_item_attribute_value(i, "label", None).get_string().split()[0]
                for i in range(menu.get_n_items())
            }
            self.assertEqual(labels["win.expand-subtree"], "展开整个子树")
            self.assertEqual(labels["win.collapse-subtree"], "收起整个子树")
            self.assertEqual(labels["win.sibling"], "新增同级节点")
            self.assertEqual(win.entry.get_text(), "茶 & water")
            self.assertEqual(win.active.value, "File")
            self.assertFalse(win.document.dirty)
            win.edit_key(None, Gdk.KEY_Tab, 0, 0)
            win.find_source()
            win.source.search_entry.set_text("task")
            win.source.move_match(1)
            buffer = win.source.buffer
            xml = buffer.get_text(*buffer.get_bounds(), True)
            self.assertIn("<task>Save</task>", xml)
            self.assertIn("茶 &amp; water", xml)

            win.activate_action("win.language", GLib.Variant("s", "en"))
            self.assertEqual(win.inspector.result[0].get_text(), "Changes have not been checked")
            self.assertEqual(win.pages.get_tab_label_text(win.source), "XML Source")
            self.assertEqual(win.source.search_entry.get_placeholder_text(), "Find in XML source (Ctrl+F)")
            self.assertEqual(win.source.count.get_text(), "2 / 2")
            self.assertEqual(buffer.get_text(*buffer.get_bounds(), True), xml)
            self.assertFalse(group.get_expanded())
            self.assertEqual(len(win.document.undo_stack), 1)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(i18n.preference_file().read_text().strip(), "en")

            invalid = Path(temp) / "无效.xml"
            invalid.write_text("<r></wrong>")
            with patch.object(win, "show_error"):
                win.open_path(invalid)
            self.assertIn("mismatched tag", win.inspector.result[0].get_text())
            win.activate_action("win.language", GLib.Variant("s", "zh_CN"))
            self.assertIn("起始和结束标签不匹配", win.inspector.result[0].get_text())
            self.assertEqual(win.inspector.result[1].get_text(), invalid.name)
            win.history(False)
            self.assertTrue(win.save())
            self.assertEqual(path.read_bytes(), original)

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
            self.assertEqual(win.inspector.result[0].get_text(), tr("XML is well-formed"))
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

    def test_tree_guides_follow_siblings_after_reordering(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "tree.xml"
            path.write_text("<root><first><a/><b/></first><last><c/></last></root>")
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            win.present()

            def guides(name):
                wait_for(lambda: any(row.name == name for row in win.name_cells.values()))
                cell = next(cell for cell, row in win.name_cells.items() if row.name == name)
                slot = cell.get_parent().get_first_child()
                result = []
                while slot != cell:
                    result.append(next((c for c in slot.get_css_classes() if c.startswith("bx-")), None))
                    slot = slot.get_next_sibling()
                return result

            self.assertEqual(guides("root"), ["bx-root"])
            self.assertEqual(guides("a"), ["bx-trunk", "bx-fork", "bx-link"])
            self.assertEqual(guides("b"), ["bx-trunk", "bx-elbow", "bx-link"])
            self.assertEqual(guides("c"), [None, "bx-elbow", "bx-link"])
            win.reveal(win.document.roots.get_item(0).children.get_item(1))
            win.node_command("move-up")
            self.assertEqual(guides("c"), ["bx-trunk", "bx-elbow", "bx-link"])
            self.assertEqual(guides("last"), ["bx-fork", "bx-link"])
            win.history(False)
            self.assertEqual(guides("c"), [None, "bx-elbow", "bx-link"])

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

    def test_fold_near_end_keeps_row_under_pointer(self):
        for following in ("", "<after/>"):
            with self.subTest(following=following), TemporaryDirectory() as temp:
                path = Path(temp) / "recipe.xml"
                xml = ("<recipe>" + "<step/>" * 200 + "<params>" + "<param/>" * 7
                       + "</params>" + following + "</recipe>")
                path.write_text(xml)
                win = RecipeWindow(self.app, Document(path))
                self.addCleanup(win.destroy)
                params = win.rows.get_child_row(0).get_child_row(200)
                params.set_expanded(True)
                win.set_resizable(False)  # Measure the fold without a simultaneous compositor resize.
                win.present()
                scroll = win.view.get_vadjustment()
                wait_for(lambda: scroll.get_page_size() > 0 and scroll.get_upper() > scroll.get_page_size())
                scroll.set_value(scroll.get_upper() - scroll.get_page_size())

                def center(row):
                    label = win.cells.get(row.get_item())
                    if label is not None and label.get_height():
                        _, bounds = label.compute_bounds(win.view)
                        return bounds.get_y() + bounds.get_height() / 2
                    return -1

                wait_for(lambda: 0 < center(params) < win.view.get_height() - 100)
                clock = win.view.get_frame_clock()

                def toggle(expanded):
                    before = center(params)
                    painted = []
                    handler = clock.connect_after("after-paint", lambda *_: painted.append(center(params)))
                    try:
                        params.set_expanded(expanded)
                        wait_for(lambda: painted)
                        win.view.queue_draw()
                        wait_for(lambda: len(painted) >= 2)
                    finally:
                        clock.disconnect(handler)
                    self.assertTrue(all(abs(y - before) <= 1 for y in painted), (before, painted))

                toggle(False)
                if following:
                    after = win.rows.get_child_row(0).get_child_row(201)
                    self.assertGreater(center(after), center(params))
                    self.assertLess(center(after) - center(params), 2 * win.cells[params.get_item()].get_height())
                click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
                win.context_pressed(click, 1, 60, win.view.get_height() - 12)
                self.assertFalse(win.node_menu.get_visible())

                old_y = center(params)
                scroll.set_value(scroll.get_value() - 35)
                wait_for(lambda: center(params) > old_y + 30)
                toggle(True)
                self.assertEqual(len(params.get_children()), 7)
                self.assertFalse(win.document.dirty)
                self.assertEqual(path.read_bytes(), xml.encode())

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
            self.assertEqual(page.count.get_text(), tr("No matches"))
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

    def test_context_menu_expands_and_collapses_entire_subtree(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "recipe.xml"
            original = b"<r><task><params><param key='x'/></params></task><other><leaf/></other></r>"
            path.write_bytes(original)
            win = RecipeWindow(self.app, Document(path))
            self.addCleanup(win.destroy)
            root = win.rows.get_child_row(0)
            task, other = root.get_child_row(0), root.get_child_row(1)
            expand = win.lookup_action("expand-subtree")
            collapse = win.lookup_action("collapse-subtree")

            # Closing a single row leaves remembered descendants beneath it.
            task.get_child_row(0).set_expanded(False)
            other.set_expanded(False)
            win.selection.set_selected(task.get_position())
            self.assertTrue(expand.get_enabled() and collapse.get_enabled())
            expand.activate(None)
            params = task.get_child_row(0)
            self.assertTrue(params.get_expanded() and params.get_child_row(0).get_expanded())
            self.assertFalse(other.get_expanded())

            task.set_expanded(False)
            collapse.activate(None)
            task.set_expanded(True)
            params = task.get_child_row(0)
            self.assertFalse(params.get_expanded())
            params.set_expanded(True)
            self.assertFalse(params.get_child_row(0).get_expanded())

            win.selection.set_selected(root.get_position())
            collapse.activate(None)
            self.assertEqual(win.rows.get_n_items(), 1)
            expand.activate(None)
            expand.activate(None)
            self.assertEqual(win.rows.get_n_items(), 7)
            self.assertTrue(all(row.get_expanded() for row in win.rows if row.is_expandable()))
            win.selection.set_selected(win.rows.get_n_items() - 1)
            self.assertFalse(expand.get_enabled() or collapse.get_enabled())
            self.assertFalse(win.document.undo_stack)
            self.assertFalse(win.document.dirty)
            self.assertEqual(win.document.render(), original)
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
