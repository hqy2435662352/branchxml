"""Lower pane for XML syntax checks and the selected node."""

from gi.repository import Gtk, Pango

from document import error_text
from i18n import tr


class Inspector(Gtk.Notebook):
    def __init__(self, check, show_line):
        super().__init__()
        self.add_css_class("bx-inspector")
        grid = Gtk.Grid(column_spacing=16, row_spacing=4, margin_start=8, margin_end=8,
                        margin_top=4, margin_bottom=4)
        self.result = []
        self.headings = {}
        self.report_message = ""
        self.grid = grid
        self.extra_rows = 0
        self.show_line = show_line
        self.first_line = None
        for col, title in enumerate(("Description", "File", "Line", "Column")):
            heading = Gtk.Label(xalign=0)
            self.headings[title] = heading
            heading.add_css_class("dim-label")
            grid.attach(heading, col, 0, 1, 1)
            label = Gtk.Label(xalign=0, hexpand=col == 0, ellipsize=Pango.EllipsizeMode.END)
            if col:
                label.set_width_chars(18 if col == 1 else 4)
                label.set_max_width_chars(28 if col == 1 else 8)
            if col == 2:
                self.jump = Gtk.Button(has_frame=False, child=label, visible=False)
                self.jump.connect("clicked", lambda *_: self.show_line(self.first_line))
                grid.attach(self.jump, col, 1, 1, 1)
            else:
                grid.attach(label, col, 1, 1, 1)
            self.result.append(label)
        results_scroll = Gtk.ScrolledWindow()
        results_scroll.set_child(grid)
        self.append_page(results_scroll, Gtk.Label())

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

    def report(self, message, path, navigable=True):
        while self.extra_rows:
            self.grid.remove_row(1 + self.extra_rows)
            self.extra_rows -= 1
        self.report_message = message.with_traceback(None) if isinstance(message, Exception) else message
        self.translate_report()
        line = getattr(message, "lineno", None)
        offset = getattr(message, "offset", None)
        name = path.name if path else tr("Untitled.xml")
        for label, text in zip(self.result[1:], (name, str(line or ""), str(offset + 1) if offset is not None else "")):
            label.set_text(text)
            label.set_tooltip_text(text or None)
        self.first_line = line
        self.jump.set_visible(bool(line))
        self.jump.set_sensitive(navigable)

    def report_issues(self, issues, path):
        message, line, column = issues[0]
        self.report(message, path)
        self.first_line = line
        self.result[2].set_text(str(line or ""))
        self.jump.set_visible(bool(line))
        self.result[3].set_text(str(column or ""))
        for message, line, column in issues[1:]:
            self.extra_rows += 1
            index = 1 + self.extra_rows
            info = Gtk.Label(label=message, xalign=0, ellipsize=Pango.EllipsizeMode.END)
            info.set_tooltip_text(message)
            self.grid.attach(info, 0, index, 1, 1)
            self.grid.attach(Gtk.Label(label=self.result[1].get_text(), xalign=0), 1, index, 1, 1)
            if line:
                button = Gtk.Button(label=str(line), has_frame=False)
                button.connect("clicked", lambda _, n=line: self.show_line(n))
                self.grid.attach(button, 2, index, 1, 1)
            self.grid.attach(Gtk.Label(label=str(column or ""), xalign=0), 3, index, 1, 1)

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
