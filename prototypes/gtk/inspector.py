"""Lower pane for XML syntax checks and the selected node."""

from gi.repository import Gtk, Pango

from document import error_text
from i18n import tr


class Inspector(Gtk.Notebook):
    def __init__(self, check):
        super().__init__()
        self.add_css_class("bx-inspector")
        grid = Gtk.Grid(column_spacing=16, row_spacing=4, margin_start=8, margin_end=8,
                        margin_top=4, margin_bottom=4)
        self.result = []
        self.headings = {}
        self.report_message = ""
        for col, title in enumerate(("Description", "File", "Line", "Column")):
            heading = Gtk.Label(xalign=0)
            self.headings[title] = heading
            heading.add_css_class("dim-label")
            grid.attach(heading, col, 0, 1, 1)
            label = Gtk.Label(xalign=0, hexpand=col == 0, ellipsize=Pango.EllipsizeMode.END)
            if col:
                label.set_width_chars(18 if col == 1 else 4)
                label.set_max_width_chars(28 if col == 1 else 8)
            grid.attach(label, col, 1, 1, 1)
            self.result.append(label)
        self.append_page(grid, Gtk.Label())

        self.info = Gtk.Label(xalign=0, yalign=0, selectable=True, margin_start=8, margin_top=6)
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.info)
        self.append_page(scroll, Gtk.Label())
        button = Gtk.Button()
        button.connect("clicked", lambda *_: check())
        self.set_action_widget(button, Gtk.PackType.END)

    def translate_ui(self):
        for title, heading in self.headings.items():
            heading.set_text(tr(title))
        self.set_tab_label_text(self.get_nth_page(0), tr("Check Results"))
        self.set_tab_label_text(self.get_nth_page(1), tr("Node Info"))
        button = self.get_action_widget(Gtk.PackType.END)
        button.set_label(tr("Check XML"))
        button.set_tooltip_text(tr("Check XML syntax and namespaces"))
        self.translate_report()

    def translate_report(self):
        message = self.report_message
        text = tr(message) if isinstance(message, str) else error_text(message)
        self.result[0].set_text(text)
        self.result[0].set_tooltip_text(text or None)

    def report(self, message, path):
        self.report_message = message.with_traceback(None) if isinstance(message, Exception) else message
        self.translate_report()
        line = getattr(message, "lineno", None)
        offset = getattr(message, "offset", None)
        for label, text in zip(self.result[1:], (path.name, str(line or ""), str(offset + 1) if offset is not None else "")):
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
        if row.value is None:
            detail = tr("Children  {count}", count=row.children.get_n_items())
        else:
            detail = tr("Value  {value}", value=row.value)
        self.info.set_text(f"{path}\n{detail}")
