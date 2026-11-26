"""Display a line diff of the bytes BranchXML would save."""
import codecs
import difflib
import re

from gi.repository import Gtk

from document import validate
from i18n import tr


def read_lines(data):
    encoding = validate(data)
    text = data.decode(encoding).removeprefix("\ufeff")
    lines = [line for line in re.findall(r"[^\r\n]*(?:\r\n|[\r\n]|$)", text) if line]
    endings = set(re.findall(r"\r\n|\r|\n", text))
    if lines and not lines[-1].endswith(("\r", "\n")):
        endings.add("")
    names = {"\r\n": "CRLF", "\n": "LF", "\r": "CR", "": "EOF"}
    bom = data.startswith((codecs.BOM_UTF8, codecs.BOM_UTF16_BE, codecs.BOM_UTF16_LE))
    description = " · ".join(filter(None, [encoding.upper(), "BOM" if bom else "",
                                           "/".join(sorted(names[e] for e in endings))]))
    return lines, description


def comparison(before, after, old_name, new_name):
    if before == after:
        return tr("Files are byte-identical."), []
    left, old_format = read_lines(before)
    right, new_format = read_lines(after)
    header = f"{old_name}  ·  {old_format}\n{new_name}  ·  {new_format}"
    show_endings = [s.rstrip("\r\n") for s in left] == [s.rstrip("\r\n") for s in right]
    result = []
    for line in difflib.unified_diff(left, right, fromfile=old_name, tofile=new_name, lineterm=""):
        content = line.rstrip("\r\n")
        if show_endings and line[:1] in ("+", "-") and not line.startswith(("+++", "---")):
            ending = line[len(content):]
            content += "  ⟨" + {"\n": "LF", "\r\n": "CRLF", "\r": "CR", "": "EOF"}[ending] + "⟩"
        result.append(content)
    return header, result or [tr("The text is identical. The file encoding or byte order mark differs.")]


def show_comparison(parent, before, after, old_name, new_name):
    header, lines = comparison(before, after, old_name, new_name)
    dialog = Gtk.Dialog(title=tr("Compare XML"), transient_for=parent, modal=True)
    dialog.add_css_class("branchxml")
    dialog.set_default_size(760, 460)
    dialog.add_button(tr("Close"), Gtk.ResponseType.CLOSE)
    dialog.connect("response", lambda d, *_: d.destroy())
    box = dialog.get_content_area()
    box.append(Gtk.Label(label=header, xalign=0, selectable=True, wrap=True,
                         margin_top=8, margin_bottom=8, margin_start=10))
    if lines:
        view = Gtk.TextView(editable=False, monospace=True, left_margin=10, top_margin=6)
        view.add_css_class("bx-document-text")
        buf = view.get_buffer()
        added = buf.create_tag("add")
        removed = buf.create_tag("remove")
        for line in lines:
            if line.startswith(("+", "-")):
                buf.insert_with_tags_by_name(buf.get_end_iter(), line + "\n", "add" if line[0] == "+" else "remove")
            else:
                buf.insert(buf.get_end_iter(), line + "\n")
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(view)
        box.append(scroll)

        def update_diff_colors(window, *_):
            added.props.background = "#27482f" if window.dark else "#dcf4df"
            added.props.foreground = "#b8e6c2" if window.dark else "#174f2b"
            removed.props.background = "#542e2b" if window.dark else "#fbe1df"
            removed.props.foreground = "#efbdb4" if window.dark else "#742822"

        update_diff_colors(parent)
        theme_handler = parent.connect("notify::dark", update_diff_colors)
        dialog.connect("unrealize", lambda *_: parent.disconnect(theme_handler))
    dialog.present()
