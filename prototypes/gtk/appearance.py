"""Appearance and hierarchy guides for the GTK editor."""

import re
from pathlib import Path
from string import Template

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango

from i18n import tr


COLORS = {
    "drop_edge": ("#477056", "#8aaa8f"),
    "drop_fill": ("#d3e4d5", "#314238"),
    "canvas": ("#fbfaf7", "#1d211f"),
    "foreground": ("#30332e", "#e0e5df"),
    "focus_outline": ("#57735d", "#9abb9e"),
    "branch_row": ("#f3ead9", "#393327"),
    "selected_row": ("#e8ede5", "#38443a"),
    "focused_row": ("#dbe8db", "#405744"),
    "selection_edge": ("#52715b", "#9cbc9f"),
    "header": ("#efeee9", "#272b28"),
    "chrome_text": ("#43473f", "#c9cec6"),
    "hover": ("#e5e5de", "#343934"),
    "tree_line": ("#9a9f94", "#5e695e"),
    "expander_icon": ("#42493e", "#d3dbd1"),
    "expander_border": ("#858c80", "#889288"),
    "element_mark": ("#4a6b83", "#93adc3"),
    "attribute_mark": ("#9b5941", "#d3997f"),
    "text_mark": ("#547951", "#9cba91"),
    "folder": ("#996b24", "#d6b46b"),
    "element": ("#334d60", "#acc2d3"),
    "attribute": ("#88452f", "#ddad94"),
    "text_node": ("#486748", "#b0d0a5"),
    "value": ("#395b43", "#acd0b1"),
    "number": ("#3b5678", "#a6bedc"),
    "boolean": ("#734d75", "#d4b0d7"),
    "empty": ("#63685e", "#b4bbb1"),
    "editor_border": ("#51765c", "#99bd9d"),
    "entry_bg": ("#ffffff", "#282e2a"),
    "entry_text": ("#262b25", "#e1e8e0"),
    "selected_text_bg": ("#cbdfcf", "#405742"),
    "selected_text_fg": ("#203627", "#d4e4d5"),
    "chrome": ("#f3f2ee", "#242825"),
    "caption": ("#383c35", "#d8ddd5"),
    "entry_border": ("#b8bab1", "#535b54"),
    "separator": ("#d8d9d1", "#404741"),
    "separator_hover": ("#99ab98", "#77957d"),
    "tab_line": ("#cdc7c2", "#485048"),
    "tab_label": ("#51564c", "#b9c0b8"),
    "active_tab_label": ("#303c30", "#dce5db"),
    "active_tab_line": ("#637f65", "#86a98b"),
    "status": ("#53584f", "#b6bdb3"),
}

CSS = """
.branchxml .bx-drop-before { box-shadow: inset 0 2px $drop_edge; }
.branchxml .bx-drop-after { box-shadow: inset 0 -2px $drop_edge; }
.branchxml .bx-drop-inside { background-color: $drop_fill; }
.branchxml {
  background: $canvas;
  color: $foreground;
}
.branchxml .bx-tree,
.branchxml .bx-tree listview,
.branchxml .bx-tree textview,
.branchxml textview,
.branchxml notebook.bx-pages,
.branchxml notebook.bx-inspector,
.branchxml .bx-inspector grid {
  background: $canvas;
  color: $foreground;
}
.branchxml .bx-tree {
  font-family: monospace;
  font-size: 12px;
}
.branchxml .bx-tree row {
  min-height: 24px;
  padding: 0;
  background: $canvas;
  border: none;
}
.branchxml .bx-tree row,
.branchxml .bx-tree cell,
.branchxml entry {
  outline-color: $focus_outline;
}
.branchxml .bx-tree row:not(:selected) .bx-branch:not(.bx-drop-inside) {
  background-color: $branch_row;
}
.branchxml .bx-tree row:selected {
  background: $selected_row;
}
.branchxml .bx-tree row:selected:focus,
.branchxml .bx-tree row:selected:focus-within {
  background: $focused_row;
  box-shadow: inset 2px 0 $selection_edge;
}
.branchxml .bx-tree cell {
  padding: 0;
}
.branchxml .bx-tree header button {
  min-height: 25px;
  padding: 1px 7px;
  border-radius: 0;
  background: $header;
  color: $chrome_text;
}
.branchxml .bx-tree header button:hover {
  background: $hover;
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
  color: $tree_line;
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
  color: $expander_icon;
  min-width: 9px;
  padding: 0 5px;
  -gtk-icon-size: 9px;
  -gtk-icon-source: -gtk-icontheme("list-add-symbolic");
  -gtk-icon-transform: none;
  background: image($canvas) center / 9px 9px no-repeat,
              image($expander_border) center / 11px 11px no-repeat,
              image($tree_line) right center / 100% 1px no-repeat,
              none center bottom / 1px 50% no-repeat;
}
.branchxml .bx-tree treeexpander > expander:checked {
  -gtk-icon-source: -gtk-icontheme("list-remove-symbolic");
  background-image: image($canvas), image($expander_border), image($tree_line), image($tree_line);
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
.branchxml .bx-tree .bx-value-cell {
  padding-left: 11px;
  padding-right: 11px;
}
.branchxml .bx-tree .bx-row-mark {
  font-size: 10px;
  min-width: 16px;
}
.branchxml .bx-tree .bx-mark-element {
  color: $element_mark;
}
.branchxml .bx-tree .bx-mark-attribute {
  color: $attribute_mark;
}
.branchxml .bx-tree .bx-mark-special {
  color: $text_mark;
}
.branchxml .bx-tree .bx-icon-folder {
  color: $folder;
}
.branchxml .bx-tree .bx-name-element {
  color: $element;
}
.branchxml .bx-tree .bx-name-attribute {
  color: $attribute;
}
.branchxml .bx-tree .bx-name-special {
  color: $text_node;
}
.branchxml .bx-tree .bx-value-string {
  color: $value;
}
.branchxml .bx-tree .bx-value-number {
  color: $number;
}
.branchxml .bx-tree .bx-value-boolean {
  color: $boolean;
}
.branchxml .bx-tree .bx-value-empty {
  color: $empty;
}
.branchxml entry.bx-inline-editor {
  font-family: monospace;
  min-height: 22px;
  padding: 1px 5px;
  border: 1px solid $editor_border;
  border-radius: 2px;
  background: $entry_bg;
  color: $entry_text;
  outline-color: $editor_border;
}
.branchxml entry.bx-inline-editor selection {
  background-color: $selected_text_bg;
  color: $selected_text_fg;
}
.branchxml headerbar.bx-title {
  min-height: 34px;
  padding: 2px 7px;
  background: $chrome;
  color: $caption;
}
.branchxml headerbar.bx-title button {
  min-height: 27px;
  padding: 2px 7px;
}
.branchxml headerbar.bx-title label {
  color: $caption;
}
.branchxml .branchxml-chrome {
  background: $chrome;
  color: $chrome_text;
}
.branchxml .branchxml-chrome button {
  min-height: 25px;
  padding: 2px 6px;
  border-radius: 2px;
  color: $chrome_text;
}
.branchxml .branchxml-chrome entry {
  min-height: 26px;
  padding: 2px 6px;
  border-color: $entry_border;
  border-radius: 2px;
  background: $entry_bg;
  color: $foreground;
}
.branchxml .branchxml-chrome separator {
  background: $separator;
}
.branchxml .branchxml-chrome popovermenubar {
  min-height: 26px;
  background: $header;
  color: $chrome_text;
}
.branchxml .branchxml-chrome popovermenubar button {
  min-height: 25px;
  color: $chrome_text;
}
.branchxml paned.bx-workspace > separator {
  min-width: 5px;
  min-height: 4px;
  background: $separator;
}
.branchxml paned.bx-workspace > separator:hover {
  background: $separator_hover;
}
.branchxml notebook.bx-pages > header,
.branchxml notebook.bx-inspector > header {
  min-height: 25px;
  background: $header;
  color: $chrome_text;
  border-bottom: 1px solid $tab_line;
}
.branchxml notebook.bx-pages tab,
.branchxml notebook.bx-inspector tab {
  min-height: 24px;
  padding: 2px 9px;
  background: $header;
  color: $tab_label;
  box-shadow: inset 0 -1px $tab_line;
}
.branchxml notebook.bx-pages tab:checked,
.branchxml notebook.bx-inspector tab:checked {
  background: $canvas;
  color: $active_tab_label;
  box-shadow: inset 0 -2px $active_tab_line;
}
.branchxml .bx-source text {
  background-color: $canvas;
  color: $foreground;
}
.branchxml .bx-find {
  padding: 2px 6px;
  background: $chrome;
  color: $chrome_text;
}
.branchxml .bx-find button,
.branchxml .bx-find searchentry {
  min-height: 25px;
  padding: 2px 6px;
}
.branchxml .bx-status {
  min-height: 22px;
  padding: 1px 7px;
  border-top: 1px solid $separator;
  background: $chrome;
  color: $status;
}
"""

DARK_WIDGET_CSS = """
.branchxml popover, .branchxml menu {
  background: $header;
  color: $foreground;
}
.branchxml popover modelbutton:hover, .branchxml menu menuitem:hover {
  background: $selected_row;
}
.branchxml text selection, .branchxml entry selection {
  background-color: $selected_text_bg;
  color: $selected_text_fg;
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


def document_css(font_size, dark=False):
    colors = {name: pair[dark] for name, pair in COLORS.items()}
    css = Template(CSS + DARK_WIDGET_CSS if dark else CSS).substitute(colors)
    return css + f"""
    .branchxml .bx-tree .bx-name-cell, .branchxml .bx-tree .bx-value-cell,
    .branchxml .bx-inline-editor, .branchxml .bx-source, textview.bx-document-text {{
      font-size: {font_size}px;
    }}"""


def install(display, font_size, dark=False):
    style = (font_size, dark)
    if display in _PROVIDERS:
        provider, previous = _PROVIDERS[display]
        if previous == style:
            return
    else:
        icons = Path(__file__).resolve().with_name("icons")
        Gtk.IconTheme.get_for_display(display).add_search_path(str(icons if icons.is_dir() else icons.parent.parent / "icons"))
        provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    provider.load_from_string(document_css(font_size, dark))
    _PROVIDERS[display] = provider, style


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
    expander.set_css_classes(["bx-branch"] if row.is_expandable() else [])
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
    if row.children.get_n_items():
        label.add_css_class("bx-branch")
