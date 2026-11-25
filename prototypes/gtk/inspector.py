"""Lower pane for XML syntax checks and the selected node."""

from gi.repository import Gtk, Pango


class Inspector(Gtk.Notebook):
    def __init__(self, check):
        super().__init__()
        self.add_css_class("bx-inspector")
        grid = Gtk.Grid(column_spacing=16, row_spacing=4, margin_start=8, margin_end=8,
                        margin_top=4, margin_bottom=4)
        self.result = []
        for col, title in enumerate(("说明", "文件", "行", "列")):
            heading = Gtk.Label(label=title, xalign=0)
            heading.add_css_class("dim-label")
            grid.attach(heading, col, 0, 1, 1)
            label = Gtk.Label(xalign=0, hexpand=col == 0, ellipsize=Pango.EllipsizeMode.END)
            if col:
                label.set_width_chars(18 if col == 1 else 4)
                label.set_max_width_chars(28 if col == 1 else 8)
            grid.attach(label, col, 1, 1, 1)
            self.result.append(label)
        self.append_page(grid, Gtk.Label(label="检查结果"))

        self.info = Gtk.Label(xalign=0, yalign=0, selectable=True, margin_start=8, margin_top=6)
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.info)
        self.append_page(scroll, Gtk.Label(label="节点信息"))
        button = Gtk.Button(label="检查 XML", tooltip_text="检查当前文档的 XML 语法和命名空间")
        button.connect("clicked", lambda *_: check())
        self.set_action_widget(button, Gtk.PackType.END)

    def report(self, message, path, error=None):
        line = getattr(error, "lineno", None)
        offset = getattr(error, "offset", None)
        for label, text in zip(self.result, (message, path.name, str(line or ""), str(offset + 1) if offset is not None else "")):
            label.set_text(text)
            label.set_tooltip_text(text or None)

    def select_node(self, tree_row):
        if tree_row is None:
            self.info.set_text("")
            return
        row = tree_row.get_item()
        names = []
        while tree_row is not None:
            names.append(tree_row.get_item().name)
            tree_row = tree_row.get_parent()
        path = "/" + "/".join(reversed(names))
        detail = f"子项  {row.children.get_n_items()}" if row.value is None else f"值  {row.value}"
        self.info.set_text(f"{path}\n{detail}")
