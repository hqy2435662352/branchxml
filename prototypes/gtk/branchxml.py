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

import appearance
import i18n
from chrome import Chrome
from document import Document, error_text, move_neighbor
from i18n import tr
from inspector import Inspector
from source_view import SourcePage


FILE_ERRORS = (OSError, GLib.Error, ExpatError, ValueError, LookupError)
PAGE_HINTS = ("Right-click a node for actions", "Ctrl+F Find  ·  F3 Next  ·  Shift+F3 Previous")
NODE_COMMANDS = (
    ("sibling", "Add Sibling", "Insert"), ("child", "Add Child Element", "Ctrl+Insert"),
    ("attribute", "Add Attribute", "Alt+Insert"), ("duplicate", "Duplicate Node", "Ctrl+D"),
    ("move-up", "Move Up", "Alt+↑"), ("move-down", "Move Down", "Alt+↓"),
    ("delete", "Delete Node", "Delete"),
)


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
        self.set_default_size(920, 690)
        self.add_css_class("branchxml")
        appearance.install(self.get_display())
        titlebar = Gtk.HeaderBar()
        titlebar.add_css_class("bx-title")
        titlebar.set_title_widget(Gtk.Box())
        titlebar.pack_start(Gtk.Image.new_from_icon_name("application-xml"))
        caption = Gtk.Label(ellipsize=Pango.EllipsizeMode.MIDDLE, xalign=0)
        self.bind_property("title", caption, "label")
        titlebar.pack_start(caption)
        self.set_titlebar(titlebar)
        self.cells = {}
        self.name_cells = {}
        self.padded_row = None
        self.anchor_handler = None
        self.active = None
        self.preedit = ""
        self.placed = False

        self.view = Gtk.ColumnView()
        self.view.connect("unmap", lambda *_: self.cancel_scroll_anchor())
        self.view.add_css_class("bx-tree")
        self.view.set_show_column_separators(True)
        self.view.set_show_row_separators(False)

        names = Gtk.SignalListItemFactory()
        names.connect("setup", self.setup_name)
        names.connect("bind", self.bind_name)
        names.connect("unbind", self.unbind_name)
        self.name_column = Gtk.ColumnViewColumn.new("", names)
        self.name_column.set_fixed_width(270)
        self.name_column.set_resizable(True)
        self.view.append_column(self.name_column)

        values = Gtk.SignalListItemFactory()
        values.connect("setup", self.setup_value)
        values.connect("bind", self.bind_value)
        values.connect("unbind", self.unbind_value)
        self.value_column = Gtk.ColumnViewColumn.new("", values)
        self.value_column.set_expand(True)
        self.view.append_column(self.value_column)

        history_keys = Gtk.EventControllerKey()
        history_keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        history_keys.connect("key-pressed", self.history_key)
        self.add_controller(history_keys)

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
        self.entry.add_css_class("bx-inline-editor")
        self.field.append(self.entry)
        self.overlay.add_overlay(self.field)
        self.overlay.connect("get-child-position", self.position_field)
        scroll.get_vadjustment().connect("notify::page-size", self.limit_bottom_margin)
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
        self.status = Gtk.Label(ellipsize=Pango.EllipsizeMode.END, hexpand=True, xalign=0)
        self.encoding = Gtk.Label()
        statusbar = Gtk.Box(spacing=12)
        statusbar.add_css_class("bx-status")
        statusbar.append(self.status)
        statusbar.append(self.encoding)
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for name, shortcut, callback in (
                ("open", "<Control>o", lambda: self.choose_file(False)),
                ("save", "<Control>s", self.save),
                ("save-as", "<Control><Shift>s", lambda: self.choose_file(True))):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_, run=callback: run())
            self.add_action(action)
            app.set_accels_for_action("win." + name, [shortcut])
        language = Gio.SimpleAction.new_stateful("language", GLib.VariantType.new("s"),
                                                 GLib.Variant("s", i18n.preference))
        language.connect("change-state", self.change_language)
        self.add_action(language)
        for name, _title, _shortcut in NODE_COMMANDS:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda action, _: self.node_command(action.get_name()))
            self.add_action(action)
        self.node_menu = Gtk.PopoverMenu.new_from_model(Gio.Menu())
        self.node_menu.set_has_arrow(False)
        self.node_menu.set_halign(Gtk.Align.START)
        self.node_menu.connect_after("closed", lambda *_: self.view.grab_focus())
        layout.append(self.node_menu)
        context_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        context_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        context_click.connect("pressed", self.context_pressed)
        self.view.add_controller(context_click)
        self.pages = Gtk.Notebook()
        self.pages.add_css_class("bx-pages")
        self.pages.append_page(self.overlay, Gtk.Label())
        self.source = SourcePage()
        self.pages.append_page(self.source, Gtk.Label())
        self.pages.connect("switch-page", self.switch_page)

        self.inspector = Inspector(self.check_xml)
        workspace = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        workspace.add_css_class("bx-workspace")
        workspace.set_start_child(self.pages)
        workspace.set_end_child(self.inspector)
        workspace.set_resize_end_child(False)
        workspace.set_shrink_start_child(False)
        self.inspector.set_size_request(-1, 108)
        self.chrome = Chrome(self, app)
        layout.append(self.chrome)
        layout.append(workspace)
        layout.append(statusbar)
        self.set_child(layout)
        self.set_document(document)
        self.translate_ui()
        self.view.grab_focus()
        self.connect("close-request", self.close_requested)

    def change_language(self, action, value):
        choice = value.get_string()
        if choice == i18n.preference or choice not in i18n.CHOICES:
            return
        try:
            i18n.select_language(choice)
        except (OSError, GLib.Error) as error:
            self.show_error("Could not save the language preference", error)
            return
        for window in self.get_application().get_windows():
            if isinstance(window, RecipeWindow):
                window.lookup_action("language").set_state(value)
                window.translate_ui()

    def translate_ui(self):
        self.name_column.set_title(tr("Node"))
        self.value_column.set_title(tr("Value"))
        self.pages.set_tab_label_text(self.overlay, tr("Tree View"))
        self.pages.set_tab_label_text(self.source, tr("XML Source"))
        self.chrome.translate_ui()
        self.source.translate_ui()
        self.inspector.translate_ui()
        self.inspector.select_node(self.selection.get_selected_item())
        menu = Gio.Menu()
        for name, title, shortcut in NODE_COMMANDS:
            menu.append(f"{tr(title)}    {shortcut}", "win." + name)
        self.node_menu.set_menu_model(menu)
        for cell, row in self.name_cells.items():
            appearance.set_name(cell, row)
        if self.active is not None:
            self.label_editor(self.active)
        message, hint, values = self.status_content
        self.set_status(message, hint, **values)

    def set_status(self, message, hint=None, **values):
        self.status_content = message, hint, values
        text = tr(message, **values)
        if hint:
            text += "  ·  " + tr(hint)
        self.status.set_label(text)

    def set_document(self, document):
        self.finish(False)
        self.document = document
        self.expanded = set()
        self.install_tree()
        self.update_title()
        self.chrome.sync_path()
        self.inspector.report("XML is well-formed", document.path)
        self.source.clear_search()
        self.refresh_source()
        self.encoding.set_label(document.encoding.upper())
        self.set_status("Opened {filename}", PAGE_HINTS[self.pages.get_current_page()], filename=document.path.name)
        # Open a small recipe far enough to start editing; cap initial work for larger ones.
        pos = 0
        while pos < min(80, self.rows.get_n_items()):
            self.rows.get_item(pos).set_expanded(True)
            pos += 1
        self.scroll_to_row(0)

    def switch_page(self, notebook, page, index):
        if not hasattr(self, "document"):
            return
        if index == 1:
            self.finish(True)
            self.refresh_source(force=True)
        self.set_status(PAGE_HINTS[index])

    def refresh_source(self, force=False):
        if not force and self.pages.get_current_page() != 1:
            return
        try:
            xml = self.document.xml_bytes().decode("utf-8-sig")
        except FILE_ERRORS as error:
            xml = ""
            self.inspector.set_visible(True)
            self.inspector.set_current_page(0)
            self.inspector.report(error, self.document.path)
        self.source.set_xml(xml)

    def find_source(self):
        self.pages.set_current_page(1)
        self.source.search_entry.grab_focus()
        self.source.search_entry.select_region(0, -1)

    def check_xml(self):
        self.finish(True)
        self.inspector.set_visible(True)
        self.inspector.set_current_page(0)
        try:
            self.document.render()
        except FILE_ERRORS as error:
            self.inspector.report(error, self.document.path)
        else:
            self.inspector.report("XML is well-formed", self.document.path)

    def changed(self):
        self.inspector.report("Changes have not been checked", self.document.path)
        self.inspector.select_node(self.selection.get_selected_item())
        self.refresh_source()

    def install_tree(self):
        self.cancel_scroll_anchor()
        self.clear_bottom_margin()
        self.rows = Gtk.TreeListModel.new(self.document.roots, False, False,
                                          lambda row: row.children if row.children.get_n_items() else None)
        self.watched_branches = set()
        self.selection = Gtk.SingleSelection.new(self.rows)
        self.view.set_model(self.selection)
        self.selection.connect("notify::selected-item", lambda *_: self.update_node_actions())
        self.watch_branches(self.rows, self.document.roots)
        self.update_node_actions()

    def watch_branches(self, parent, children):
        pending = [(parent, children)]
        while pending:
            parent, children = pending.pop()
            for index, row in enumerate(children):
                if not row.children.get_n_items():
                    continue
                branch = parent.get_child_row(index)
                if (row.path, row.name) in self.expanded:
                    branch.set_expanded(True)
                    pending.append((branch, row.children))
                # GtkTreeListModel only holds a weak reference to each row wrapper.
                self.watched_branches.add(branch)
                branch.connect("notify::expanded", self.expansion_changed)

    def expansion_changed(self, branch, _property):
        if not branch.is_expandable():
            # GTK detached this row when an ancestor closed. Keep its remembered state.
            self.watched_branches.discard(branch)
            return
        row = branch.get_item()
        key = (row.path, row.name)
        if branch.get_expanded():
            self.expanded.add(key)
            self.watch_branches(branch, row.children)
        else:
            self.expanded.discard(key)
        self.keep_branch_position(branch)

    def row_widget(self, branch):
        widget = self.cells.get(branch.get_item())
        while widget is not None and widget.get_accessible_role() != Gtk.AccessibleRole.ROW:
            widget = widget.get_parent()
        return widget

    def clear_bottom_margin(self):
        if self.padded_row is not None:
            self.padded_row.set_margin_bottom(0)
            self.padded_row = None

    def limit_bottom_margin(self, adjustment, _property):
        row = self.padded_row
        if row is not None:
            # Keep the last node on screen at the scroll limit after the pane shrinks.
            limit = max(0, int(adjustment.get_page_size()) - row.get_height())
            row.set_margin_bottom(min(row.get_margin_bottom(), limit))

    def cancel_scroll_anchor(self):
        if self.anchor_handler is not None:
            clock, handler = self.anchor_handler
            clock.disconnect(handler)
            self.anchor_handler = None

    def scroll_to_row(self, pos, column=None, flags=Gtk.ListScrollFlags(0)):
        # Explicit navigation supersedes a fold awaiting layout.
        self.cancel_scroll_anchor()
        self.view.scroll_to(pos, column, flags, None)

    def keep_branch_position(self, branch):
        self.cancel_scroll_anchor()
        self.clear_bottom_margin()
        if not self.view.get_mapped():
            return
        widget = self.row_widget(branch)
        if widget is None or not widget.get_height():
            return
        ok, bounds = widget.compute_bounds(self.view)
        if not ok:
            return
        height = self.view.get_height()
        y = bounds.get_y()
        header = height - self.view.get_vadjustment().get_page_size()
        if y >= height or y + bounds.get_height() <= header:
            return

        # Keep GTK's virtualized row available while it lays out the new subtree.
        self.view.scroll_to(branch.get_position(), None, Gtk.ListScrollFlags(0), None)

        # GTK repeats layout before painting, so the user sees only the anchored position.
        clock = self.view.get_frame_clock()
        self.anchor_handler = clock, clock.connect_after("layout", self.restore_branch_position, branch, y)

    def restore_branch_position(self, clock, branch, y):
        row = self.row_widget(branch)
        if row is None or not row.get_mapped():
            self.cancel_scroll_anchor()
            return
        _, bounds = row.compute_bounds(self.view)
        delta = round(bounds.get_y() - y)
        adjustment = self.view.get_vadjustment()
        target = adjustment.get_value() + delta
        if self.padded_row is None and target > adjustment.get_upper() - adjustment.get_page_size():
            last = self.row_widget(self.rows.get_item(self.rows.get_n_items() - 1))
            if last is not None:
                _, bounds = last.compute_bounds(self.view)
                gap = round(self.view.get_height() - bounds.get_y() - bounds.get_height() + delta)
                if gap > 0:
                    self.padded_row = last
                    last.set_margin_bottom(gap)
                    return  # Apply the offset once GTK includes the margin in the scroll range.
        self.cancel_scroll_anchor()
        adjustment.set_value(target)

    def update_node_actions(self):
        self.node_menu.popdown()
        item = self.selection.get_selected_item()
        row = item.get_item() if item else None
        self.inspector.select_node(item)
        for name in ("sibling", "child", "attribute", "duplicate", "delete", "move-up", "move-down"):
            enabled = row is not None
            if enabled and name in ("move-up", "move-down"):
                enabled = move_neighbor(self.rows.get_model(), row, name) is not None
            elif enabled and name in ("child", "attribute"):
                enabled = row.element
            elif enabled and len(row.path) == 1:
                enabled = not row.element and name != "sibling"
            self.lookup_action(name).set_enabled(enabled)

    def context_pressed(self, gesture, presses, x, y):
        # Hit-test the whole row, including its indentation and cell padding.
        hit = self.view.pick(x, y, Gtk.PickFlags.DEFAULT)
        while hit is not None and hit is not self.view:
            if hit.get_accessible_role() == Gtk.AccessibleRole.ROW:
                for label in self.cells.values():
                    if label.is_ancestor(hit):
                        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                        self.popup_node_menu(label.tree_row, self.view, x, y)
                        return
                return
            hit = hit.get_parent()

    def popup_node_menu(self, tree_row, widget, x, y):
        x, y = widget.translate_coordinates(self.node_menu.get_parent(), x, y)
        self.finish(True)
        self.selection.set_selected(tree_row.get_position())
        self.scroll_to_row(tree_row.get_position(), flags=Gtk.ListScrollFlags.FOCUS)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self.node_menu.set_pointing_to(rect)
        self.node_menu.popup()

    def node_command(self, operation):
        self.finish(True)
        row = self.selection.get_selected_item().get_item()
        if operation in ("duplicate", "delete", "move-up", "move-down"):
            self.change_node(row, operation)
            return
        attribute = operation == "attribute" or (operation == "sibling" and row.name.startswith("@"))
        dialog = Gtk.Dialog(title=tr("Add Attribute" if attribute else "Add Element"),
                            transient_for=self, modal=True)
        dialog.add_button(tr("Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(tr("Add"), Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        entry = Gtk.Entry(text="attribute" if attribute else "element", activates_default=True,
                          margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        entry.update_property([Gtk.AccessibleProperty.LABEL], [tr("XML name")])
        dialog.get_content_area().append(entry)

        def answered(dialog, response):
            name = entry.get_text()
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                self.change_node(row, operation, name)

        dialog.connect("response", answered)
        dialog.present()
        entry.grab_focus()
        entry.select_region(0, -1)

    def change_node(self, row, operation, name=""):
        try:
            selected = self.document.structure(row, operation, name)
        except FILE_ERRORS as error:
            self.show_error("Could not update the node", error)
            return
        self.show_change(selected)
        self.set_status("Node updated  ·  Ctrl+Z to undo")

    def show_change(self, row):
        rebuilt = self.rows.get_model() != self.document.roots
        if rebuilt:
            self.install_tree()
        self.refresh_value(row)
        self.changed()
        target = self.rows.get_child_row(row.path[0])
        for index in row.path[1:]:
            target.set_expanded(True)
            target = target.get_child_row(index)
        if rebuilt:
            target.set_expanded(True)
        flags = Gtk.ListScrollFlags.SELECT | Gtk.ListScrollFlags.FOCUS
        self.scroll_to_row(target.get_position(), self.value_column, flags)
        self.view.grab_focus()

    def update_history_actions(self):
        for action, stack in (("undo", self.document.undo_stack), ("redo", self.document.redo_stack)):
            self.lookup_action(action).set_enabled(self.active is not None or bool(stack))

    def update_title(self):
        self.update_history_actions()
        marker = "● " if self.document.dirty else ""
        self.set_title(f"{marker}{self.document.path.name} — BranchXML · GTK")

    def show_error(self, message, error):
        Gtk.AlertDialog(message=tr(message), detail=error_text(error), buttons=[tr("Close")]).show(self)

    def confirm_changes(self, proceed):
        self.finish(True)
        if not self.document.dirty:
            proceed()
            return
        dialog = Gtk.AlertDialog(message=tr("Save changes to {filename}?", filename=self.document.path.name),
                                 buttons=[tr("Cancel"), tr("Discard Changes"), tr("Save")],
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
        dialog = Gtk.FileDialog(title=tr("Save As" if save_as else "Open XML"), modal=True,
                                accept_label=tr("Save" if save_as else "Open"))
        dialog.set_initial_folder(Gio.File.new_for_path(str(path.absolute().parent)))
        if save_as:
            dialog.set_initial_name(tr("{stem}-copy{suffix}", stem=path.stem, suffix=path.suffix))
            dialog.save(self, None, self.file_chosen, True)
        else:
            dialog.open(self, None, self.file_chosen, False)

    def file_chosen(self, dialog, result, save_as):
        try:
            file = dialog.save_finish(result) if save_as else dialog.open_finish(result)
            path = file.get_path()
            if path is None:
                raise ValueError(tr("Choose a local file."))
        except GLib.Error as error:
            if not any(error.matches(Gtk.DialogError.quark(), code)
                       for code in (Gtk.DialogError.DISMISSED, Gtk.DialogError.CANCELLED)):
                self.show_error("File dialog error", error)
            return
        except ValueError as error:
            self.show_error("Could not select the file", error)
            return
        if save_as:
            self.save(path)
        else:
            self.confirm_changes(lambda: self.open_path(path))

    def open_path(self, path):
        try:
            doc = Document(path)
        except FILE_ERRORS as error:
            self.inspector.report(error, Path(path))
            self.inspector.set_visible(True)
            self.inspector.set_current_page(0)
            self.show_error("Could not open the file", error)
            return
        self.set_document(doc)

    def save(self, path=None):
        self.finish(True)
        try:
            self.document.save(path or self.document.path)
        except FILE_ERRORS as error:
            self.inspector.report(error, self.document.path)
            self.show_error("Could not save the file", error)
            return False
        self.update_title()
        self.chrome.sync_path()
        self.inspector.report("XML is well-formed", self.document.path)
        self.set_status("Saved to {path}", path=self.document.path)
        return True

    def setup_name(self, factory, item):
        expander = Gtk.TreeExpander()
        expander.set_child(appearance.name_cell())
        item.set_child(expander)

    def bind_name(self, factory, item):
        tree_row = item.get_item()
        expander = item.get_child()
        expander.set_list_row(tree_row)
        cell, row = expander.get_child(), tree_row.get_item()
        self.name_cells[cell] = row
        appearance.set_name(cell, row)

    def unbind_name(self, factory, item):
        expander = item.get_child()
        self.name_cells.pop(expander.get_child(), None)
        expander.set_list_row(None)

    def setup_value(self, factory, item):
        label = cell_label()
        label.set_hexpand(True)
        item.set_child(label)
        click = Gtk.GestureClick(button=1)
        click.connect("released", lambda *_: self.request_edit(item.get_position()))
        label.add_controller(click)

    def bind_value(self, factory, item):
        label = item.get_child()
        label.tree_row = item.get_item()
        row = label.row = label.tree_row.get_item()
        appearance.set_value(label, row)
        label.set_text(row.value or "")
        label.set_tooltip_text(row.value or None)
        self.cells[row] = label
        if self.active is row:
            self.overlay.queue_allocate()

    def unbind_value(self, factory, item):
        label = item.get_child()
        if self.padded_row is not None and label.is_ancestor(self.padded_row):
            self.clear_bottom_margin()
        self.cells.pop(label.row, None)
        label.row = label.tree_row = None

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
        self.update_history_actions()
        self.placed = False
        self.selection.set_selected(pos)
        self.scroll_to_row(pos, self.value_column)
        # Reusing the entry must not carry typing history from the previous field.
        self.entry.set_enable_undo(False)
        self.entry.set_text(row.value)
        self.entry.set_enable_undo(True)
        self.label_editor(row)
        self.overlay.queue_allocate()
        self.field.set_visible(True)
        self.entry.grab_focus()
        self.entry.select_region(0, -1)
        self.set_status("Editing {name}  ·  Enter to commit  ·  Tab to continue  ·  Esc to cancel", name=row.name)

    def label_editor(self, row):
        self.entry.update_property([Gtk.AccessibleProperty.LABEL], [tr("Edit the value of {name}", name=row.name)])

    def commit_value(self):
        value = self.entry.get_text()
        if value != self.active.value:
            self.document.edit(self.active, value)
            self.changed()
        self.refresh_value(self.active)

    def refresh_value(self, row):
        self.update_title()
        label = self.cells.get(row)
        if label is not None:
            appearance.set_value(label, row)
            label.set_text(row.value or "")
            label.set_tooltip_text(row.value or None)

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
        self.update_history_actions()
        self.set_status("Committed edit to {name}" if commit else "Canceled edit to {name}", name=name)

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
        self.set_status("Reached the last visible value" if direction > 0 else "Reached the first visible value")

    def history_key(self, controller, key, code, mods):
        mods &= Gtk.accelerator_get_default_mod_mask()
        ctrl = Gdk.ModifierType.CONTROL_MASK
        key = Gdk.keyval_to_lower(key)
        redo = ((mods == ctrl and key == Gdk.KEY_y) or
                (mods == (ctrl | Gdk.ModifierType.SHIFT_MASK) and key == Gdk.KEY_z))
        if self.preedit or not (redo or (mods == ctrl and key == Gdk.KEY_z)):
            return False

        focus = self.get_focus()
        if focus and (focus.get_ancestor(Gtk.SearchEntry) or
                      focus.get_ancestor(Gtk.Entry) not in (None, self.entry)):
            return False
        return self.history(redo)

    def history(self, redo):
        if self.active:
            # Give uncommitted typing first use of the shortcut, including local redo.
            before = self.entry.get_text()
            self.entry.get_delegate().activate_action("text.redo" if redo else "text.undo", None)
            if self.entry.get_text() != before or before != self.active.value:
                return True

        row = self.document.step_history(redo)
        if row is not None:
            self.finish(False)
            self.show_change(row)
            self.set_status("Redid change to {name}" if redo else "Undid change to {name}", name=row.name)
        return True

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
        if self.active:
            return False
        mods &= Gtk.accelerator_get_default_mod_mask()
        if ((key == Gdk.KEY_Menu and not mods) or
                (key == Gdk.KEY_F10 and mods == Gdk.ModifierType.SHIFT_MASK)):
            target = self.selection.get_selected_item()
            label = self.cells.get(target.get_item()) if target else None
            if label is not None and label.get_mapped():
                self.popup_node_menu(target, label, 0, label.get_height() / 2)
            return True
        commands = {
            (Gdk.KEY_Insert, 0): "sibling", (Gdk.KEY_Insert, Gdk.ModifierType.CONTROL_MASK): "child",
            (Gdk.KEY_Insert, Gdk.ModifierType.ALT_MASK): "attribute",
            (Gdk.KEY_Up, Gdk.ModifierType.ALT_MASK): "move-up",
            (Gdk.KEY_Down, Gdk.ModifierType.ALT_MASK): "move-down",
            (Gdk.KEY_d, Gdk.ModifierType.CONTROL_MASK): "duplicate", (Gdk.KEY_Delete, 0): "delete",
        }
        command = commands.get((Gdk.keyval_to_lower(key), mods))
        if command:
            self.lookup_action(command).activate(None)
            return True
        if mods & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
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
    parser = argparse.ArgumentParser(description=tr("BranchXML GTK 4 XML editor."))
    parser.add_argument("xml", nargs="?", type=Path,
                        default=Path(__file__).resolve().parents[2] / "examples/demo.xml", help=tr("XML file to open"))
    path = parser.parse_args().xml
    if Gtk.check_version(4, 12, 0):
        parser.exit(1, tr("BranchXML requires GTK 4.12 or later.") + "\n")
    try:
        document = Document(path)
    except FILE_ERRORS as error:
        parser.exit(1, f"{path}: {error_text(error)}\n")
    app = Gtk.Application(application_id="io.github.branchxml.InputPrototype",
                          flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", lambda app: RecipeWindow(app, document).present())
    return app.run([])


if __name__ == "__main__":
    sys.exit(main())
