"""Compact, light XML tree styling for the GTK prototype."""

import re
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango

from i18n import tr


CSS = """
.branchxml {
  background: #ffffff;
  color: #202632;
}
.branchxml .bx-tree,
.branchxml .bx-tree listview,
.branchxml .bx-tree textview,
.branchxml textview,
.branchxml notebook.bx-pages,
.branchxml notebook.bx-inspector,
.branchxml .bx-inspector grid {
  background: #ffffff;
  color: #202632;
}
.branchxml .bx-tree {
  font-family: monospace;
  font-size: 12px;
}
.branchxml .bx-tree row {
  min-height: 24px;
  padding: 0;
  color: #202632;
  border-bottom: 1px solid #e8edf2;
}
.branchxml .bx-tree row:nth-child(even) {
  background: #f1f7fc;
}
.branchxml .bx-tree row:selected {
  background: #c5def5;
}
.branchxml .bx-tree row:selected:focus,
.branchxml .bx-tree row:selected:focus-within {
  background: #2673bb;
}
.branchxml .bx-tree row:selected label {
  color: #17334f;
}
.branchxml .bx-tree row:selected:focus label,
.branchxml .bx-tree row:selected:focus-within label {
  color: #ffffff;
}
.branchxml .bx-tree row:selected image {
  color: #7c570f;
}
.branchxml .bx-tree row:selected:focus image,
.branchxml .bx-tree row:selected:focus-within image {
  color: #ffffff;
}
.branchxml .bx-tree cell {
  padding: 0;
}
.branchxml .bx-tree header button {
  min-height: 25px;
  padding: 1px 7px;
  border-radius: 0;
  background: #eaf2fa;
  color: #234568;
}
.branchxml .bx-tree header button:hover {
  background: #d7e8f6;
}
.branchxml .bx-tree .bx-name-cell,
.branchxml .bx-tree .bx-value-cell {
  min-height: 24px;
  padding: 1px 6px;
  font-family: monospace;
  font-size: 12px;
}
.branchxml .bx-tree .bx-name-cell {
  padding-left: 2px;
}
.branchxml .bx-tree .bx-row-mark {
  font-size: 10px;
}
.branchxml .bx-tree .bx-mark-element {
  color: #3473ae;
}
.branchxml .bx-tree .bx-mark-attribute {
  color: #c44740;
}
.branchxml .bx-tree .bx-mark-special {
  color: #218447;
}
.branchxml .bx-tree .bx-icon-folder {
  color: #c58a16;
}
.branchxml .bx-tree .bx-name-element {
  color: #2e669d;
}
.branchxml .bx-tree .bx-name-attribute {
  color: #bd403a;
}
.branchxml .bx-tree .bx-name-special {
  color: #187744;
}
.branchxml .bx-tree .bx-value-string {
  color: #187444;
}
.branchxml .bx-tree .bx-value-number {
  color: #2769aa;
}
.branchxml .bx-tree .bx-value-boolean {
  color: #8153a5;
}
.branchxml .bx-tree .bx-value-empty {
  color: #66717e;
}
.branchxml entry.bx-inline-editor {
  min-height: 22px;
  padding: 1px 5px;
  border: 1px solid #2b75b8;
  border-radius: 2px;
  background: #ffffff;
  color: #17202b;
}
.branchxml headerbar.bx-title {
  min-height: 34px;
  padding: 2px 7px;
  background: #f2f5f8;
  color: #25384b;
}
.branchxml headerbar.bx-title button {
  min-height: 27px;
  padding: 2px 7px;
}
.branchxml headerbar.bx-title label {
  color: #25384b;
}
.branchxml .branchxml-chrome {
  background: #f2f5f8;
  color: #304154;
}
.branchxml .branchxml-chrome button {
  min-height: 25px;
  padding: 2px 6px;
  border-radius: 2px;
  color: #304154;
}
.branchxml .branchxml-chrome entry {
  min-height: 26px;
  padding: 2px 6px;
  border-color: #aebdca;
  border-radius: 2px;
  background: #ffffff;
  color: #1d2935;
}
.branchxml .branchxml-chrome separator {
  background: #d7e0e8;
}
.branchxml .branchxml-chrome popovermenubar {
  min-height: 26px;
  background: #eaf2fa;
  color: #304154;
}
.branchxml .branchxml-chrome popovermenubar button {
  min-height: 25px;
  color: #304154;
}
.branchxml paned.bx-workspace > separator {
  min-width: 5px;
  min-height: 4px;
  background: #d8e0e8;
}
.branchxml paned.bx-workspace > separator:hover {
  background: #8bb5dd;
}
.branchxml notebook.bx-pages > header,
.branchxml notebook.bx-inspector > header {
  min-height: 25px;
  background: #eaf2fa;
  color: #263c50;
}
.branchxml notebook.bx-pages tab,
.branchxml notebook.bx-inspector tab {
  min-height: 24px;
  padding: 2px 9px;
  background: #eaf2fa;
  color: #344c62;
}
.branchxml notebook.bx-pages tab:checked,
.branchxml notebook.bx-inspector tab:checked {
  background: #ffffff;
  color: #1b3b59;
}
.branchxml .bx-source text {
  background-color: #ffffff;
  color: #202632;
}
.branchxml .bx-find {
  padding: 2px 6px;
  background: #f2f5f8;
  color: #304154;
}
.branchxml .bx-find button,
.branchxml .bx-find searchentry {
  min-height: 25px;
  padding: 2px 6px;
}
.branchxml .bx-status {
  min-height: 22px;
  padding: 1px 7px;
  border-top: 1px solid #d8e0e8;
  background: #f2f6fa;
  color: #435365;
}
"""

_PROVIDERS = {}


VALUE_NUMBER = re.compile(r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$")


def install(display):
    if display in _PROVIDERS:
        return
    Gtk.IconTheme.get_for_display(display).add_search_path(str(Path(__file__).resolve().with_name("icons")))
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _PROVIDERS[display] = provider


def name_cell():
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    box.add_css_class("bx-name-cell")
    mark = Gtk.Label(label="●")
    folder = Gtk.Image.new_from_icon_name("folder-symbolic")
    folder.add_css_class("bx-icon-folder")
    label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
    box.append(mark)
    box.append(folder)
    box.append(label)
    return box


def set_name(box, row):
    mark = box.get_first_child()
    folder = mark.get_next_sibling()
    label = box.get_last_child()
    label.set_text(row.name)
    container = row.element and row.children.get_n_items() > 0
    folder.set_tooltip_text(tr("Element with child nodes"))
    folder.set_visible(container)
    mark.set_visible(not container)
    if row.element:
        kind = "element"
        tooltip = "Element value from CDATA" if row.span and row.span[2] == "cdata" else "XML element"
    elif row.name.startswith("@"):
        kind, tooltip = "attribute", "XML attribute"
    else:
        kind = "special"
        tooltip = "XML processing instruction" if row.span[2].startswith("pi") else "XML comment or text node"
    label.set_css_classes(["bx-name-" + kind])
    mark.set_css_classes(["bx-row-mark", "bx-mark-" + kind])
    mark.set_tooltip_text(tr(tooltip))


def value_kind(value):
    if not value:
        return "empty"
    if value.casefold() in ("true", "false"):
        return "boolean"
    if VALUE_NUMBER.fullmatch(value):
        return "number"
    return "string"


def set_value(label, row):
    label.set_css_classes(["bx-value-cell", "bx-value-" + value_kind(row.value)])
