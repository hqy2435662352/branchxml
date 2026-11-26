"""Appearance and hierarchy guides for the GTK editor."""

import re
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango

from i18n import tr


CSS = """
.branchxml .bx-drop-before { box-shadow: inset 0 2px #477056; }
.branchxml .bx-drop-after { box-shadow: inset 0 -2px #477056; }
.branchxml .bx-drop-inside { background-color: #d3e4d5; }
.branchxml {
  background: #fbfaf7;
  color: #30332e;
}
.branchxml .bx-tree,
.branchxml .bx-tree listview,
.branchxml .bx-tree textview,
.branchxml textview,
.branchxml notebook.bx-pages,
.branchxml notebook.bx-inspector,
.branchxml .bx-inspector grid {
  background: #fbfaf7;
  color: #30332e;
}
.branchxml .bx-tree {
  font-family: monospace;
  font-size: 12px;
}
.branchxml .bx-tree row {
  min-height: 24px;
  padding: 0;
  background: #fbfaf7;
  border: none;
}
.branchxml .bx-tree row,
.branchxml .bx-tree cell,
.branchxml entry {
  outline-color: #57735d;
}
.branchxml .bx-tree row:selected {
  background: #e8ede5;
}
.branchxml .bx-tree row:selected:focus,
.branchxml .bx-tree row:selected:focus-within {
  background: #dbe8db;
  box-shadow: inset 2px 0 #52715b;
}
.branchxml .bx-tree cell {
  padding: 0;
}
.branchxml .bx-tree header button {
  min-height: 25px;
  padding: 1px 7px;
  border-radius: 0;
  background: #efeee9;
  color: #43473f;
}
.branchxml .bx-tree header button:hover {
  background: #e5e5de;
}
.branchxml .bx-tree treeexpander {
  border-spacing: 0;
}
.branchxml .bx-tree treeexpander > indent,
.branchxml .bx-tree treeexpander > expander {
  min-width: 19px;
  margin: 0;
  padding: 0;
}
.branchxml .bx-tree indent {
  color: #9a9f94;
}
.branchxml .bx-tree indent.bx-trunk {
  background: image(currentColor) center / 1px 100% no-repeat;
}
.branchxml .bx-tree indent.bx-fork,
.branchxml .bx-tree indent.bx-elbow {
  background: image(currentColor) center top / 1px 100% no-repeat,
              image(currentColor) right center / 50% 1px no-repeat;
}
.branchxml .bx-tree indent.bx-elbow {
  background-size: 1px 50%, 50% 1px;
}
.branchxml .bx-tree indent.bx-fork:dir(rtl),
.branchxml .bx-tree indent.bx-elbow:dir(rtl) {
  background-position: center top, left center;
}
.branchxml .bx-tree indent.bx-link {
  background: image(currentColor) center / 100% 1px no-repeat;
}
.branchxml .bx-tree treeexpander > expander {
  color: #42493e;
  min-width: 9px;
  padding: 0 5px;
  -gtk-icon-size: 9px;
  -gtk-icon-source: -gtk-icontheme("list-add-symbolic");
  -gtk-icon-transform: none;
  background: image(#fbfaf7) center / 9px 9px no-repeat,
              image(#858c80) center / 11px 11px no-repeat,
              image(#9a9f94) right center / 100% 1px no-repeat,
              none center bottom / 1px 50% no-repeat;
}
.branchxml .bx-tree treeexpander > expander:checked {
  -gtk-icon-source: -gtk-icontheme("list-remove-symbolic");
  background-image: image(#fbfaf7), image(#858c80), image(#9a9f94), image(#9a9f94);
}
.branchxml .bx-tree treeexpander > expander.bx-root {
  background-size: 9px 9px, 11px 11px, 50% 1px, 1px 50%;
}
.branchxml .bx-tree treeexpander > expander.bx-root:dir(rtl) {
  background-position: center, center, left center, center bottom;
}
.branchxml .bx-tree .bx-name-cell,
.branchxml .bx-tree .bx-value-cell {
  min-height: 23px;
  padding: 1px 6px;
  font-family: monospace;
}
.branchxml .bx-tree .bx-name-cell {
  padding-left: 2px;
}
.branchxml .bx-tree .bx-row-mark {
  font-size: 10px;
  min-width: 16px;
}
.branchxml .bx-tree .bx-mark-element {
  color: #4a6b83;
}
.branchxml .bx-tree .bx-mark-attribute {
  color: #9b5941;
}
.branchxml .bx-tree .bx-mark-special {
  color: #547951;
}
.branchxml .bx-tree .bx-icon-folder {
  color: #996b24;
}
.branchxml .bx-tree .bx-name-element {
  color: #334d60;
}
.branchxml .bx-tree .bx-name-attribute {
  color: #88452f;
}
.branchxml .bx-tree .bx-name-special {
  color: #486748;
}
.branchxml .bx-tree .bx-value-string {
  color: #395b43;
}
.branchxml .bx-tree .bx-value-number {
  color: #3b5678;
}
.branchxml .bx-tree .bx-value-boolean {
  color: #734d75;
}
.branchxml .bx-tree .bx-value-empty {
  color: #63685e;
}
.branchxml entry.bx-inline-editor {
  font-family: monospace;
  min-height: 22px;
  padding: 1px 5px;
  border: 1px solid #51765c;
  border-radius: 2px;
  background: #ffffff;
  color: #262b25;
  outline-color: #51765c;
}
.branchxml entry.bx-inline-editor selection {
  background-color: #cbdfcf;
  color: #203627;
}
.branchxml headerbar.bx-title {
  min-height: 34px;
  padding: 2px 7px;
  background: #f3f2ee;
  color: #383c35;
}
.branchxml headerbar.bx-title button {
  min-height: 27px;
  padding: 2px 7px;
}
.branchxml headerbar.bx-title label {
  color: #383c35;
}
.branchxml .branchxml-chrome {
  background: #f3f2ee;
  color: #43473f;
}
.branchxml .branchxml-chrome button {
  min-height: 25px;
  padding: 2px 6px;
  border-radius: 2px;
  color: #43473f;
}
.branchxml .branchxml-chrome entry {
  min-height: 26px;
  padding: 2px 6px;
  border-color: #b8bab1;
  border-radius: 2px;
  background: #ffffff;
  color: #30332e;
}
.branchxml .branchxml-chrome separator {
  background: #d8d9d1;
}
.branchxml .branchxml-chrome popovermenubar {
  min-height: 26px;
  background: #efeee9;
  color: #43473f;
}
.branchxml .branchxml-chrome popovermenubar button {
  min-height: 25px;
  color: #43473f;
}
.branchxml paned.bx-workspace > separator {
  min-width: 5px;
  min-height: 4px;
  background: #d8d9d1;
}
.branchxml paned.bx-workspace > separator:hover {
  background: #99ab98;
}
.branchxml notebook.bx-pages > header,
.branchxml notebook.bx-inspector > header {
  min-height: 25px;
  background: #efeee9;
  color: #43473f;
  border-bottom: 1px solid #cdc7c2;
}
.branchxml notebook.bx-pages tab,
.branchxml notebook.bx-inspector tab {
  min-height: 24px;
  padding: 2px 9px;
  background: #efeee9;
  color: #51564c;
  box-shadow: inset 0 -1px #cdc7c2;
}
.branchxml notebook.bx-pages tab:checked,
.branchxml notebook.bx-inspector tab:checked {
  background: #fbfaf7;
  color: #303c30;
  box-shadow: inset 0 -2px #637f65;
}
.branchxml .bx-source text {
  background-color: #fbfaf7;
  color: #30332e;
}
.branchxml .bx-find {
  padding: 2px 6px;
  background: #f3f2ee;
  color: #43473f;
}
.branchxml .bx-find button,
.branchxml .bx-find searchentry {
  min-height: 25px;
  padding: 2px 6px;
}
.branchxml .bx-status {
  min-height: 22px;
  padding: 1px 7px;
  border-top: 1px solid #d8d9d1;
  background: #f3f2ee;
  color: #53584f;
}
"""

_PROVIDERS = {}


VALUE_NUMBER = re.compile(r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$")


DEFAULT_FONT_SIZE = 12
MIN_FONT_SIZE = 9
MAX_FONT_SIZE = 28


def font_size_file():
    return Path(GLib.get_user_config_dir()) / "branchxml" / "font-size"


def load_font_size():
    try:
        size = int(font_size_file().read_text(encoding="ascii").strip())
    except (OSError, UnicodeError, ValueError):
        return DEFAULT_FONT_SIZE
    return min(MAX_FONT_SIZE, max(MIN_FONT_SIZE, size))


def save_font_size(size):
    if isinstance(size, bool) or not isinstance(size, int):
        raise TypeError("font size must be an integer")
    size = min(MAX_FONT_SIZE, max(MIN_FONT_SIZE, size))
    path = font_size_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    GLib.file_set_contents(str(path), f"{size}\n".encode("ascii"))
    return size


def install(display, font_size):
    if display not in _PROVIDERS:
        icons = Path(__file__).resolve().with_name("icons")
        Gtk.IconTheme.get_for_display(display).add_search_path(str(icons if icons.is_dir() else icons.parent.parent / "icons"))
        provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        _PROVIDERS[display] = provider
    document_font = f"""
    .branchxml .bx-tree .bx-name-cell, .branchxml .bx-tree .bx-value-cell,
    .branchxml .bx-inline-editor, .branchxml .bx-source, textview.bx-document-text {{
      font-size: {font_size}px;
    }}"""
    _PROVIDERS[display].load_from_data((CSS + document_font).encode())


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


def bind_tree_row(expander, row):
    expander.set_list_row(row)
    # GTK lays out one indent per ancestor, then a toggle or a spacer for the node.
    slot = expander.get_child().get_prev_sibling()
    slot.set_css_classes(["bx-root" if row.get_depth() == 0 else "bx-link"])
    branch = row
    while (parent := branch.get_parent()) is not None:
        slot = slot.get_prev_sibling()
        has_next = branch.get_item().path[-1] + 1 < parent.get_item().children.get_n_items()
        if branch is row:
            slot.set_css_classes(["bx-fork" if has_next else "bx-elbow"])
        else:
            slot.set_css_classes(["bx-trunk"] if has_next else [])
        branch = parent


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
