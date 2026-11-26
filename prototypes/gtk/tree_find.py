"""Find node names and edit matched values without leaving the tree."""
import re

from gi.repository import Gdk, GLib, Gtk, Pango
from xml.parsers.expat import ExpatError

from document import walk_rows
from i18n import tr
from xml_tools import xpath_result


class TreeFind(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, visible=False)
        self.window = window
        self.matches = []
        self.index = 0
        self.xpath = False
        self.pending_xpath = False
        self.message = None
        self.cached_roots = None
        self.rows = []
        bar = Gtk.Box(spacing=4)
        bar.add_css_class("bx-find")
        self.entry = Gtk.SearchEntry(hexpand=True)
        self.entry.connect("changed", lambda *_: self.search())
        self.entry.connect("activate", lambda *_: self.next_or_evaluate(1))
        self.entry.connect("next-match", lambda *_: self.move(1))
        self.entry.connect("previous-match", lambda *_: self.move(-1))
        self.entry.connect("stop-search", lambda *_: self.close())
        bar.append(self.entry)
        self.regex = Gtk.CheckButton()
        self.case = Gtk.CheckButton()
        for option in (self.regex, self.case):
            option.connect("toggled", lambda *_: self.search())
            bar.append(option)
        self.count = Gtk.Label(ellipsize=Pango.EllipsizeMode.END, max_width_chars=30)
        bar.append(self.count)
        self.buttons = []
        for icon, action in (("go-up-symbolic", lambda: self.move(-1)),
                             ("go-down-symbolic", lambda: self.move(1)),
                             ("window-close-symbolic", self.close)):
            button = Gtk.Button(icon_name=icon, focus_on_click=False)
            button.connect("clicked", lambda _, run=action: run())
            self.buttons.append(button)
            bar.append(button)
        self.append(bar)
        self.bindings = Gtk.Entry(visible=False)
        self.bindings.connect("changed", lambda *_: self.search())
        self.bindings.connect("activate", lambda *_: self.evaluate())
        self.append(self.bindings)
        self.replace_bar = Gtk.Box(spacing=4)
        self.replace_bar.add_css_class("bx-find")
        self.replacement = Gtk.Entry(hexpand=True)
        self.replace_bar.append(self.replacement)
        self.replace_one = Gtk.Button()
        self.replace_all = Gtk.Button()
        for button, many in ((self.replace_one, False), (self.replace_all, True)):
            button.connect("clicked", lambda _, all_rows=many: self.replace(all_rows))
            self.replace_bar.append(button)
        self.append(self.replace_bar)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.key_pressed)
        self.add_controller(keys)

    def translate_ui(self):
        prompt = tr("XPath expression · Enter to evaluate" if self.xpath else "Find node names and values")
        self.entry.set_placeholder_text(prompt)
        self.entry.update_property([Gtk.AccessibleProperty.LABEL], [prompt])
        self.bindings.set_placeholder_text(tr("Optional namespaces · prefix=URI (use default for the default namespace)"))
        self.bindings.update_property([Gtk.AccessibleProperty.LABEL], [tr("XPath namespaces")])
        self.replacement.set_placeholder_text(tr("Replacement value"))
        self.replacement.update_property([Gtk.AccessibleProperty.LABEL], [tr("Replacement value")])
        self.replace_one.set_label(tr("Replace in Value"))
        self.replace_all.set_label(tr("Replace All Values"))
        self.regex.set_label(tr("Regex"))
        self.case.set_label(tr("Match case"))
        for button, label in zip(self.buttons, ("Previous match (Shift+F3)", "Next match (F3)", "Close")):
            button.set_tooltip_text(tr(label))
            button.update_property([Gtk.AccessibleProperty.LABEL], [tr(label)])
        self.update_count()

    def open(self, replacing=False, xpath=False):
        self.window.finish(True)
        if self.xpath != xpath:
            self.entry.set_text("")
        self.xpath = xpath
        self.bindings.set_visible(xpath)
        self.regex.set_visible(not xpath)
        self.case.set_visible(not xpath)
        self.set_visible(True)
        self.replace_bar.set_visible(replacing)
        self.search()
        self.translate_ui()
        self.entry.grab_focus()
        self.entry.select_region(0, -1)

    def close(self):
        self.set_visible(False)
        self.window.view.grab_focus()

    def reset(self):
        self.set_visible(False)
        self.entry.set_text("")
        self.replacement.set_text("")
        self.bindings.set_text("")
        self.discard_rows()

    def discard_rows(self):
        self.matches = []
        self.index = 0
        self.cached_roots = None
        self.rows = []

    def pattern(self):
        text = self.entry.get_text()
        return re.compile(text if self.regex.get_active() else re.escape(text),
                          0 if self.case.get_active() else re.IGNORECASE)

    def search(self, navigate=True):
        query = self.entry.get_text()
        self.message = None
        if self.xpath:
            self.matches = []
            self.index = 0
            self.pending_xpath = bool(query)
            self.update_count()
            return
        try:
            pattern = self.pattern() if query else None
        except re.error as error:
            self.matches = []
            self.message = str(error)
            self.update_count()
            return
        if pattern and self.cached_roots is not self.window.document.roots:
            self.cached_roots = self.window.document.roots
            self.rows = list(walk_rows(self.cached_roots))
        previous = self.matches[self.index].path if self.matches and not navigate else None
        self.matches = [row for row in self.rows
                        if pattern.search(row.name) or pattern.search(row.value or "")] if pattern else []
        self.index = next((i for i, row in enumerate(self.matches) if row.path == previous), 0)
        self.update_count()
        if navigate and self.matches:
            self.window.reveal(self.matches[self.index])

    def update_count(self):
        if self.xpath and self.pending_xpath:
            self.count.set_text(tr("Press Enter"))
        elif self.message is not None:
            self.count.set_text(self.message)
        elif self.matches:
            self.count.set_text(f"{self.index + 1} / {len(self.matches)}")
        else:
            self.count.set_text(tr("No matches") if self.entry.get_text() else "")
        self.count.set_tooltip_text(self.count.get_text() or None)
        for button in self.buttons[:2]:
            button.set_sensitive(bool(self.matches))

    def evaluate(self):
        if not self.entry.get_text():
            return
        self.pending_xpath = False
        self.index = 0
        try:
            self.matches, self.message = xpath_result(self.window.document, self.entry.get_text(),
                                                           self.bindings.get_text())
        except (ValueError, OSError, GLib.Error, ExpatError) as error:
            self.matches = []
            self.message = str(error)
        self.update_count()
        if self.matches:
            self.window.reveal(self.matches[0])

    def next_or_evaluate(self, step):
        if self.xpath and self.pending_xpath:
            self.evaluate()
        else:
            self.move(step)

    def move(self, step):
        if self.matches:
            self.index = (self.index + step) % len(self.matches)
            self.window.reveal(self.matches[self.index])
            self.update_count()

    def replace(self, all_rows):
        if not self.matches:
            return
        pattern = self.pattern()
        value = self.replacement.get_text()
        rows = self.matches if all_rows else [self.matches[self.index]]
        substitute = value if self.regex.get_active() else (lambda _: value)
        try:
            changes = ((row, pattern.sub(substitute, row.value)) for row in rows if row.value is not None)
            count = self.window.document.edit_values(changes)
        except (re.error, IndexError) as error:
            self.window.show_error("Could not replace values", error)
            return
        if count:
            self.window.refresh_visible_values()
            self.window.changed()
            if self.matches:
                self.window.reveal(self.matches[self.index])
        self.window.set_status("Changed {count} values", count=count)

    def key_pressed(self, controller, key, code, mods):
        if key == Gdk.KEY_Escape:
            self.close()
            return True
        if key == Gdk.KEY_F3:
            self.next_or_evaluate(-1 if mods & Gdk.ModifierType.SHIFT_MASK else 1)
            return True
        return False
