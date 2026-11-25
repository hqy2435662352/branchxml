"""File, edit and view commands for the desktop window."""

from pathlib import Path

from gi.repository import Gio, Gtk

from i18n import CHOICES, tr


class Chrome(Gtk.Box):
    def __init__(self, window, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.add_css_class("branchxml-chrome")
        for name, callback in (
                ("undo", lambda: window.history(False)), ("redo", lambda: window.history(True)),
                ("address", self.focus_address), ("check", window.check_xml),
                ("find-source", window.find_source),
                ("tree", lambda: window.pages.set_current_page(0)),
                ("source", lambda: window.pages.set_current_page(1)),
                ("inspector", lambda: window.inspector.set_visible(not window.inspector.get_visible()))):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_, run=callback: run())
            window.add_action(action)
        app.set_accels_for_action("win.address", ["<Control>l"])
        app.set_accels_for_action("win.find-source", ["<Control>f"])

        self.menu_bar = Gtk.PopoverMenuBar.new_from_model(Gio.Menu())
        self.append(self.menu_bar)

        tools = Gtk.Box(spacing=2, margin_start=5, margin_end=5, margin_top=2, margin_bottom=2)
        self.buttons = {}
        for icon, tooltip, action in (
                ("document-open", "Open (Ctrl+O)", "open"),
                ("document-save", "Save (Ctrl+S)", "save"),
                ("document-save-as", "Save As (Ctrl+Shift+S)", "save-as"),
                ("edit-undo-symbolic", "Undo (Ctrl+Z)", "undo"),
                ("edit-redo-symbolic", "Redo (Ctrl+Shift+Z)", "redo")):
            if action == "undo":
                tools.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
            button = Gtk.Button(icon_name=icon, action_name="win." + action)
            button.set_focus_on_click(False)
            self.buttons[tooltip] = button
            button.add_css_class("flat")
            tools.append(button)
        self.address = Gtk.Entry(hexpand=True)
        self.address.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "text-x-generic-symbolic")
        self.address.connect("activate", self.open_address)
        tools.append(self.address)
        self.append(tools)

    def translate_ui(self):
        bar = Gio.Menu()
        for title, commands in (
                ("File", (("Open…", "open"), ("Save", "save"), ("Save As…", "save-as"))),
                ("Edit", (("Undo", "undo"), ("Redo", "redo"), ("Find in XML Source…", "find-source"))),
                ("View", (("Tree View", "tree"), ("XML Source", "source"), ("Go to File Path", "address"),
                          ("Show or Hide Inspector", "inspector"), ("Check XML", "check")))):
            menu = Gio.Menu()
            for label, name in commands:
                menu.append(tr(label), "win." + name)
            if title == "View":
                languages = Gio.Menu()
                for choice, label in CHOICES.items():
                    languages.append(tr(label) if choice == "system" else label, "win.language::" + choice)
                menu.append_submenu(tr("Language"), languages)
            bar.append_submenu(tr(title), menu)
        self.menu_bar.set_menu_model(bar)
        for tooltip, button in self.buttons.items():
            text = tr(tooltip)
            button.set_tooltip_text(text)
            button.update_property([Gtk.AccessibleProperty.LABEL], [text])
        self.address.set_tooltip_text(tr("File path (Ctrl+L), press Enter to open"))
        self.address.update_property([Gtk.AccessibleProperty.LABEL], [tr("File path")])

    def sync_path(self):
        self.address.set_text(str(self.window.document.path.absolute()))

    def focus_address(self):
        self.address.grab_focus()
        self.address.select_region(0, -1)

    def open_address(self, entry):
        try:
            path = Path(entry.get_text()).expanduser()
        except RuntimeError as error:
            self.window.show_error("Could not open the file", error)
            return
        if not path.is_absolute():
            path = self.window.document.path.absolute().parent / path
        self.sync_path()
        self.window.confirm_changes(lambda: self.window.open_path(path))
