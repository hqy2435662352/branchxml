"""File, edit and view commands for the desktop window."""

from pathlib import Path

from gi.repository import Gio, Gtk


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

        bar = Gio.Menu()
        for title, commands in (
                ("文件", (("打开…", "open"), ("保存", "save"), ("另存为…", "save-as"))),
                ("编辑", (("撤销", "undo"), ("重做", "redo"), ("查找 XML 源码…", "find-source"))),
                ("视图", (("树视图", "tree"), ("XML 源码", "source"), ("定位到文件路径", "address"),
                        ("显示或隐藏检查面板", "inspector"), ("检查 XML", "check")))):
            menu = Gio.Menu()
            for label, name in commands:
                menu.append(label, "win." + name)
            bar.append_submenu(title, menu)
        self.append(Gtk.PopoverMenuBar.new_from_model(bar))

        tools = Gtk.Box(spacing=2, margin_start=5, margin_end=5, margin_top=2, margin_bottom=2)
        for icon, tooltip, action in (
                ("document-open", "打开（Ctrl+O）", "open"),
                ("document-save", "保存（Ctrl+S）", "save"),
                ("document-save-as", "另存为（Ctrl+Shift+S）", "save-as"),
                ("edit-undo-symbolic", "撤销（Ctrl+Z）", "undo"),
                ("edit-redo-symbolic", "重做（Ctrl+Shift+Z）", "redo")):
            if action == "undo":
                tools.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
            button = Gtk.Button(icon_name=icon, tooltip_text=tooltip, action_name="win." + action)
            button.set_focus_on_click(False)
            button.update_property([Gtk.AccessibleProperty.LABEL], [tooltip])
            button.add_css_class("flat")
            tools.append(button)
        self.address = Gtk.Entry(hexpand=True, tooltip_text="文件路径（Ctrl+L），按 Enter 打开")
        self.address.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "text-x-generic-symbolic")
        self.address.update_property([Gtk.AccessibleProperty.LABEL], ["文件路径"])
        self.address.connect("activate", self.open_address)
        tools.append(self.address)
        self.append(tools)

    def sync_path(self):
        self.address.set_text(str(self.window.document.path.absolute()))

    def focus_address(self):
        self.address.grab_focus()
        self.address.select_region(0, -1)

    def open_address(self, entry):
        try:
            path = Path(entry.get_text()).expanduser()
        except RuntimeError as error:
            self.window.show_error("打开失败", error)
            return
        if not path.is_absolute():
            path = self.window.document.path.absolute().parent / path
        self.sync_path()
        self.window.confirm_changes(lambda: self.window.open_path(path))
