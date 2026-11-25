#!/usr/bin/python3
"""BranchXML GTK 4 XML editor."""

import argparse
import sys
from pathlib import Path
from xml.parsers.expat import ExpatError

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from document import Document


FILE_ERRORS = (OSError, GLib.Error, ExpatError, ValueError, LookupError)


def is_editable(row):
    return row.value is not None and "\n" not in row.value and "\r" not in row.value


def cell_label():
    label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
    label.set_margin_start(5)
    label.set_margin_end(5)
    return label


class RecipeWindow(Gtk.ApplicationWindow):
    def __init__(self, app, document):
        super().__init__(application=app)
        self.set_default_size(820, 650)
        self.cells = {}
        self.active = None
        self.preedit = ""
        self.placed = False

        self.view = Gtk.ColumnView()
        self.view.set_show_column_separators(True)
        self.view.set_show_row_separators(True)

        names = Gtk.SignalListItemFactory()
        names.connect("setup", self.setup_name)
        names.connect("bind", self.bind_name)
        names.connect("unbind", lambda _, item: item.get_child().set_list_row(None))
        name_column = Gtk.ColumnViewColumn.new("节点", names)
        name_column.set_fixed_width(285)
        name_column.set_resizable(True)
        self.view.append_column(name_column)

        values = Gtk.SignalListItemFactory()
        values.connect("setup", self.setup_value)
        values.connect("bind", self.bind_value)
        values.connect("unbind", self.unbind_value)
        self.value_column = Gtk.ColumnViewColumn.new("值", values)
        self.value_column.set_expand(True)
        self.view.append_column(self.value_column)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.navigation_key)
        self.view.add_controller(keys)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.view)
        self.overlay = Gtk.Overlay()
        self.overlay.set_child(scroll)

        # A single native input context stays focused across Tab, including off-screen rows.
        self.field = Gtk.Box(visible=False)
        self.entry = Gtk.Entry(hexpand=True)
        self.field.append(self.entry)
        self.overlay.add_overlay(self.field)
        self.overlay.connect("get-child-position", self.position_field)
        for adjustment in (scroll.get_vadjustment(), scroll.get_hadjustment()):
            adjustment.connect("value-changed", lambda *_: self.overlay.queue_allocate())
        self.entry.get_delegate().connect("preedit-changed", self.preedit_changed)
        self.entry.connect("activate", lambda *_: self.leave(True))
        edit_keys = Gtk.EventControllerKey()
        edit_keys.connect("key-pressed", self.edit_key)
        self.field.add_controller(edit_keys)
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *_: self.finish(True))
        self.entry.add_controller(focus)
        self.status = Gtk.Label(ellipsize=Pango.EllipsizeMode.END, label="点值或按 F2 编辑　·　Tab 下一值　·　Esc 取消",
                                xalign=0, margin_start=10, margin_end=10, margin_top=7, margin_bottom=7)
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Gtk.HeaderBar()
        for name, title, shortcut, callback in (
                ("open", "打开", "<Control>o", lambda: self.choose_file(False)),
                ("save", "保存", "<Control>s", self.save),
                ("save-as", "另存为", "<Control><Shift>s", lambda: self.choose_file(True))):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_, run=callback: run())
            self.add_action(action)
            app.set_accels_for_action("win." + name, [shortcut])
            header.pack_start(Gtk.Button(label=title, action_name="win." + name))
        self.set_titlebar(header)
        layout.append(self.overlay)
        layout.append(self.status)
        self.set_child(layout)
        self.set_document(document)
        self.connect("close-request", self.close_requested)

    def set_document(self, document):
        self.finish(False)
        self.document = document
        self.rows = Gtk.TreeListModel.new(document.roots, False, False,
                                          lambda row: row.children if row.children.get_n_items() else None)
        self.selection = Gtk.SingleSelection.new(self.rows)
        self.view.set_model(self.selection)
        self.update_title()
        self.status.set_label(f"已打开 {document.path.name}　·　点值或按 F2 编辑　·　Tab 下一值　·　Esc 取消")
        # Open a small recipe far enough to start editing; cap initial work for larger ones.
        pos = 0
        while pos < min(80, self.rows.get_n_items()):
            self.rows.get_item(pos).set_expanded(True)
            pos += 1

    def update_title(self):
        marker = "● " if self.document.dirty else ""
        self.set_title(f"{marker}{self.document.path.name} — BranchXML · GTK")

    def show_error(self, message, error):
        Gtk.AlertDialog(message=message, detail=str(error)).show(self)

    def confirm_changes(self, proceed):
        self.finish(True)
        if not self.document.dirty:
            proceed()
            return
        dialog = Gtk.AlertDialog(message=f"保存对 {self.document.path.name} 的修改？",
                                 buttons=["取消", "放弃修改", "保存"],
                                 cancel_button=0, default_button=2)

        def answered(dialog, result):
            try:
                answer = dialog.choose_finish(result)
            except GLib.Error:
                return
            if answer == 1 or (answer == 2 and self.save()):
                proceed()

        dialog.choose(self, None, answered)

    def close_requested(self, *_):
        self.finish(True)
        if not self.document.dirty:
            return False
        self.confirm_changes(self.destroy)
        return True

    def choose_file(self, save_as):
        self.finish(True)
        path = self.document.path
        dialog = Gtk.FileDialog(title="另存为" if save_as else "打开 XML", modal=True)
        dialog.set_initial_folder(Gio.File.new_for_path(str(path.absolute().parent)))
        if save_as:
            dialog.set_initial_name(path.stem + "-副本" + path.suffix)
            dialog.save(self, None, self.file_chosen, True)
        else:
            dialog.open(self, None, self.file_chosen, False)

    def file_chosen(self, dialog, result, save_as):
        try:
            file = dialog.save_finish(result) if save_as else dialog.open_finish(result)
            path = file.get_path()
            if path is None:
                raise ValueError("请选择本机文件")
        except GLib.Error as error:
            if not any(error.matches(Gtk.DialogError.quark(), code)
                       for code in (Gtk.DialogError.DISMISSED, Gtk.DialogError.CANCELLED)):
                self.show_error("文件对话框出错", error)
            return
        except ValueError as error:
            self.show_error("无法选择文件", error)
            return
        if save_as:
            self.save(path)
        else:
            self.confirm_changes(lambda: self.open_path(path))

    def open_path(self, path):
        try:
            doc = Document(path)
        except FILE_ERRORS as error:
            self.show_error("打开失败", error)
            return
        self.set_document(doc)

    def save(self, path=None):
        self.finish(True)
        try:
            self.document.save(path or self.document.path)
        except FILE_ERRORS as error:
            self.show_error("保存失败", error)
            return False
        self.update_title()
        self.status.set_label(f"已保存到 {self.document.path}")
        return True

    def setup_name(self, factory, item):
        expander = Gtk.TreeExpander()
        expander.set_child(cell_label())
        item.set_child(expander)

    def bind_name(self, factory, item):
        tree_row = item.get_item()
        expander = item.get_child()
        expander.set_list_row(tree_row)
        expander.get_child().set_text(tree_row.get_item().name)

    def setup_value(self, factory, item):
        label = cell_label()
        label.set_hexpand(True)
        label.set_size_request(-1, 32)
        item.set_child(label)
        click = Gtk.GestureClick(button=1)
        click.connect("released", lambda *_: self.request_edit(item.get_position()))
        label.add_controller(click)

    def bind_value(self, factory, item):
        label = item.get_child()
        row = item.get_item().get_item()
        label.row = row
        label.set_text(row.value or "")
        label.set_tooltip_text(row.value or None)
        self.cells[row] = label
        if self.active is row:
            self.overlay.queue_allocate()

    def unbind_value(self, factory, item):
        self.cells.pop(item.get_child().row, None)

    def preedit_changed(self, widget, text):
        self.preedit = text

    def cell_bounds(self):
        label = self.cells.get(self.active)
        if label is None or not label.get_mapped():
            return None
        ok, bounds = label.compute_bounds(self.overlay)
        if ok and bounds.get_y() >= 0 and bounds.get_y() + bounds.get_height() <= self.overlay.get_height() + 1:
            return bounds
        return None

    def position_field(self, overlay, field, rect):
        bounds = self.cell_bounds()
        if bounds:
            rect.x, rect.y = round(bounds.get_x()), round(bounds.get_y())
            rect.width, rect.height = round(bounds.get_width()), round(bounds.get_height())
            self.placed = True
        else:
            # A recycled row may be briefly unmapped while scroll_to lays out the destination.
            rect.x, rect.y, rect.width, rect.height = -1000, -1000, 20, 32
            if self.placed and self.active:
                self.placed = False
                GLib.idle_add(self.finish_if_scrolled_out, self.active)
        return True

    def finish_if_scrolled_out(self, row):
        if self.active is row and not self.cell_bounds():
            self.leave(True)
        return GLib.SOURCE_REMOVE

    def request_edit(self, pos):
        tree_row = self.rows.get_item(pos)
        if tree_row is None or not is_editable(tree_row.get_item()):
            return
        row = tree_row.get_item()
        if row is self.active:
            return
        if self.active:
            self.commit_value()
        self.active = row
        self.placed = False
        self.selection.set_selected(pos)
        self.view.scroll_to(pos, self.value_column, Gtk.ListScrollFlags(0), None)
        self.entry.set_text(row.value)
        self.entry.update_property([Gtk.AccessibleProperty.LABEL], [f"编辑 {row.name} 的值"])
        self.overlay.queue_allocate()
        self.field.set_visible(True)
        self.entry.grab_focus()
        self.entry.select_region(0, -1)
        self.status.set_label(f"编辑 {row.name}　·　Enter 提交　·　Tab 提交并继续　·　Esc 取消")

    def commit_value(self):
        self.document.edit(self.active, self.entry.get_text())
        self.update_title()
        label = self.cells.get(self.active)
        if label is not None:
            label.set_text(self.active.value)
            label.set_tooltip_text(self.active.value or None)

    def finish(self, commit):
        if self.active is None:
            return
        if commit:
            self.commit_value()
        name = self.active.name
        self.active = None
        self.entry.reset_im_context()
        self.preedit = ""
        self.field.set_visible(False)
        self.status.set_label(("已提交" if commit else "已取消") + f" {name} 的编辑")

    def leave(self, commit):
        if self.active and not self.preedit:
            self.finish(commit)
            self.view.grab_focus()

    def step(self, direction):
        pos = self.selection.get_selected()
        for i in range(pos + direction, self.rows.get_n_items() if direction > 0 else -1, direction):
            if is_editable(self.rows.get_item(i).get_item()):
                self.request_edit(i)
                return
        if self.active:
            self.leave(True)
        self.status.set_label("已到最后一个可见值" if direction > 0 else "已到第一个可见值")

    def edit_key(self, controller, key, code, mods):
        if not self.active or key not in (Gdk.KEY_Escape, Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            return False
        # Bubble phase: the IM can consume Escape/Tab to handle its candidate list first.
        if not self.preedit:
            if key == Gdk.KEY_Escape:
                self.leave(False)
            else:
                self.step(-1 if key == Gdk.KEY_ISO_Left_Tab or mods & Gdk.ModifierType.SHIFT_MASK else 1)
        return True

    def navigation_key(self, controller, key, code, mods):
        if self.active or mods & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        pos = self.selection.get_selected()
        if pos == Gtk.INVALID_LIST_POSITION:
            return False
        if key in (Gdk.KEY_F2, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.request_edit(pos)
            return True
        if key in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            if key == Gdk.KEY_Tab and not mods & Gdk.ModifierType.SHIFT_MASK and is_editable(self.rows.get_item(pos).get_item()):
                self.request_edit(pos)
            else:
                self.step(-1 if key == Gdk.KEY_ISO_Left_Tab or mods & Gdk.ModifierType.SHIFT_MASK else 1)
            return True
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xml", nargs="?", type=Path,
                        default=Path(__file__).resolve().parents[2] / "examples/demo.xml")
    path = parser.parse_args().xml
    if Gtk.check_version(4, 12, 0):
        parser.exit(1, "此原型需要 GTK 4.12 或更高版本。\n")
    try:
        document = Document(path)
    except FILE_ERRORS as error:
        parser.exit(1, f"{path}: {error}\n")
    app = Gtk.Application(application_id="io.github.branchxml.InputPrototype",
                          flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", lambda app: RecipeWindow(app, document).present())
    return app.run([])


if __name__ == "__main__":
    sys.exit(main())
