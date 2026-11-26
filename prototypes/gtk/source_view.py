"""Read-only, syntax-highlighted XML with literal find in the displayed text."""

import re

from gi.repository import Gdk, GLib, Gtk
from pygments.lexer import include, inherit
from pygments.lexers.html import XmlLexer
from pygments.token import Comment, Name, String, Text

from appearance import value_kind
from i18n import tr


class SourceXmlLexer(XmlLexer):
    # XML declarations use the same quoted attribute syntax as start tags.
    tokens = {
        "root": [(r"<\?xml(?=\s)", Comment.Preproc, "declaration"), inherit],
        "declaration": [(r"\?>", Comment.Preproc, "#pop"), include("tag")],
    }


def syntax_spans(xml):
    # Unprocessed lexer offsets refer to the original text, including CRLF and Chinese.
    for start, token, text in SourceXmlLexer().get_tokens_unprocessed(xml):
        end = start + len(text)
        if token is Name.Tag:
            kind = "element"
        elif token is Name.Attribute:
            kind = "attribute"
        elif token in String:
            kind = value_kind(text[1:-1]) if len(text) > 2 else "string"
        elif token is Text:
            kind = value_kind(text)
        elif token is Comment.Preproc and text.startswith("<![CDATA["):
            content_start, content_end = start + len("<![CDATA["), end - len("]]>")
            yield start, content_start, "markup"
            if content_start < content_end:
                yield content_start, content_end, value_kind(xml[content_start:content_end])
            yield content_end, end, "markup"
            continue
        elif token is Name.Entity or token is Comment.Preproc:
            kind = "markup"
        elif token in Comment:
            kind = "comment"
        else:
            continue
        yield start, end, kind


class SourcePage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.view = Gtk.TextView(editable=False, monospace=True, left_margin=8, top_margin=6)
        self.view.add_css_class("bx-source")
        self.buffer = self.view.get_buffer()
        self.buffer.set_enable_undo(False)
        self.syntax_tags = {name: self.buffer.create_tag(name)
                            for name in ("element", "attribute", "string", "number", "boolean", "markup", "comment")}
        self.hit = self.buffer.create_tag("match")
        self.current_hit = self.buffer.create_tag("current-match")
        self.set_dark(False)
        self.xml = ""
        self.matches = []
        self.index = None

        bar = Gtk.Box(spacing=4)
        bar.add_css_class("bx-find")
        self.search_entry = Gtk.SearchEntry(hexpand=True)
        self.search_entry.connect("changed", lambda *_: self.find_matches())
        self.search_entry.connect("activate", lambda *_: self.move_match(1))
        self.search_entry.connect("next-match", lambda *_: self.move_match(1))
        self.search_entry.connect("previous-match", lambda *_: self.move_match(-1))
        self.search_entry.connect("stop-search", self.stop_search)
        bar.append(self.search_entry)
        self.count = Gtk.Label()
        bar.append(self.count)
        self.buttons = []
        for icon, step in (("go-up-symbolic", -1), ("go-down-symbolic", 1)):
            button = Gtk.Button(icon_name=icon, sensitive=False, focus_on_click=False)
            button.connect("clicked", lambda _, step=step: self.move_match(step))
            self.buttons.append(button)
            bar.append(button)
        self.append(bar)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.view)
        self.append(scroll)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.search_key)
        self.add_controller(keys)

    def set_dark(self, dark):
        syntax = {
            "element": ("#2e669d", "#8eb7e0"), "attribute": ("#ad3832", "#e59c91"),
            "string": ("#187444", "#8ed3a6"), "number": ("#27579a", "#9bbcf1"),
            "boolean": ("#784390", "#d2a2ef"), "markup": ("#685179", "#c1a1dc"),
            "comment": ("#586974", "#a5b4bd"),
        }
        for name, colors in syntax.items():
            self.syntax_tags[name].set_property("foreground", colors[dark])
        self.hit.set_property("background", "#6d5a25" if dark else "#ffed9b")
        self.hit.set_property("foreground", "#fff2c6" if dark else "#302800")
        self.current_hit.set_property("background", "#946328" if dark else "#ffbd54")
        self.current_hit.set_property("foreground", "#fff1d2" if dark else "#251a08")

    def translate_ui(self):
        self.search_entry.set_placeholder_text(tr("Find in XML source (Ctrl+F)"))
        self.search_entry.update_property([Gtk.AccessibleProperty.LABEL], [tr("Find in XML source")])
        for button, text in zip(self.buttons, ("Previous match (Shift+F3)", "Next match (F3)")):
            button.set_tooltip_text(tr(text))
            button.update_property([Gtk.AccessibleProperty.LABEL], [tr(text)])
        if self.search_entry.get_text() and not self.matches:
            self.count.set_text(tr("No matches"))

    def set_xml(self, xml):
        if xml == self.xml:
            return
        self.xml = xml
        self.buffer.set_text(xml)
        self.color_spans(syntax_spans(xml), lambda: self.xml is xml)
        self.buffer.place_cursor(self.buffer.get_start_iter())
        self.view.scroll_to_mark(self.buffer.get_insert(), 0, False, 0, 0)
        self.find_matches()

    def span_iters(self, start, end):
        return self.buffer.get_iter_at_offset(start), self.buffer.get_iter_at_offset(end)

    def color_spans(self, spans, still_current):
        # A long, single-line XML can have thousands of tags. Yield between frames.
        def paint(*_):
            if not still_current():
                return False
            deadline = GLib.get_monotonic_time() + 5000
            for start, end, kind in spans:
                self.buffer.apply_tag_by_name(kind, *self.span_iters(start, end))
                if GLib.get_monotonic_time() >= deadline:
                    return True
            return False

        if paint():
            self.view.add_tick_callback(paint)

    def find_matches(self):
        start, end = self.buffer.get_bounds()
        self.buffer.remove_tag(self.hit, start, end)
        self.buffer.remove_tag(self.current_hit, start, end)
        query = self.search_entry.get_text()
        matches = [m.span() for m in re.finditer(re.escape(query), self.xml, re.IGNORECASE)] if query else []
        self.matches = matches
        self.index = None
        self.color_spans(((a, b, "match") for a, b in matches), lambda: self.matches is matches)
        for button in self.buttons:
            button.set_sensitive(bool(self.matches))
        if self.matches:
            self.move_match(1)
        else:
            self.count.set_text(tr("No matches") if query else "")

    def move_match(self, step):
        if not self.matches:
            return
        if self.index is None:
            self.index = 0
        else:
            self.buffer.remove_tag(self.current_hit, *self.span_iters(*self.matches[self.index]))
            self.index = (self.index + step) % len(self.matches)
        start, end = self.span_iters(*self.matches[self.index])
        self.buffer.apply_tag(self.current_hit, start, end)
        self.buffer.place_cursor(start)
        self.view.scroll_to_mark(self.buffer.get_insert(), 0.1, False, 0, 0)
        self.count.set_text(f"{self.index + 1} / {len(self.matches)}")

    def clear_search(self):
        self.search_entry.set_text("")

    def stop_search(self, _entry):
        self.clear_search()
        self.view.grab_focus()

    def search_key(self, _controller, key, _code, mods):
        mods &= Gtk.accelerator_get_default_mod_mask()
        if key == Gdk.KEY_F3 and mods in (0, Gdk.ModifierType.SHIFT_MASK):
            self.move_match(-1 if mods else 1)
            return True
        return False
