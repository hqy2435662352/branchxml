"""XML values and their original source ranges, for local edits without reformatting."""

from dataclasses import dataclass
import re
from pathlib import Path
from xml.parsers import expat
from xml.sax.saxutils import escape

from gi.repository import Gio, GObject

from i18n import tr


class DocumentError(ValueError):
    def __init__(self, message, **values):
        super().__init__(message)
        self.values = values

    def __str__(self):
        return tr(self.args[0], **self.values)


def error_text(error):
    if isinstance(error, expat.ExpatError):
        return tr("{reason} (line {line}, column {column})", reason=tr(expat.ErrorString(error.code)),
                  line=error.lineno, column=error.offset + 1)
    return str(error)


class XmlRow(GObject.Object):
    def __init__(self, name, value=None, span=None):
        super().__init__()
        self.name = name
        self.value = self.original = value
        self.span = span
        self.bounds = span[:2] if span else None
        self.element = False
        self.children = Gio.ListStore.new(XmlRow)


def validate(data):
    """Check XML and namespace rules before using source offsets or writing bytes."""
    encoding = "utf-8"

    def declaration(version, declared, standalone):
        nonlocal encoding
        encoding = declared or encoding

    def reject_dtd(*args):
        raise DocumentError("XML documents with a DTD are not supported.")

    parser = expat.ParserCreate(namespace_separator=" ")
    parser.XmlDeclHandler = declaration
    parser.StartDoctypeDeclHandler = reject_dtd
    parser.Parse(data, True)
    if data.startswith((b"\xff\xfe", b"<\0")):
        return "utf-16-le"
    if data.startswith((b"\xfe\xff", b"\0<")):
        return "utf-16-be"
    return encoding


ATTRIBUTE = re.compile(rb"""\s+[^\s=]+\s*=\s*(["'])(.*?)\1""", re.S)


def parse_rows(source):
    # Expat supplies tag offsets and decoded values. Only attribute offsets need scanning.
    parser = expat.ParserCreate("UTF-8")
    parser.ordered_attributes = True
    roots = Gio.ListStore.new(XmlRow)
    stack = []
    chunks = []
    text_start = 0
    cdata = False

    def append(row):
        (stack[-1].children if stack else roots).append(row)

    def text(value):
        nonlocal text_start
        if not chunks and not cdata:
            text_start = parser.CurrentByteIndex
        chunks.append(value)

    def flush():
        if chunks or cdata:
            kind = "cdata" if cdata else "text"
            row = XmlRow("#cdata-section" if cdata else "#text", "".join(chunks),
                         (text_start, parser.CurrentByteIndex, kind))
            if cdata:
                row.bounds = (text_start - 9, parser.CurrentByteIndex + 3)
            append(row)
            chunks.clear()

    def start(name, attrs):
        flush()
        row = XmlRow(name)
        row.element = True
        row.open_start = parser.CurrentByteIndex
        append(row)
        stack.append(row)
        pos = parser.CurrentByteIndex + 1 + len(name.encode())
        for key, value in zip(attrs[::2], attrs[1::2]):
            match = ATTRIBUTE.match(source, pos)
            if match is None:
                raise DocumentError("Could not locate attribute {attribute} on {element}.", attribute=key, element=name)
            first, last = match.span(2)
            attr = XmlRow("@" + key, value, (first, last, match[1].decode()))
            attr.bounds = (match.end() - len(match[0].lstrip()), match.end())
            row.children.append(attr)
            pos = match.end()
        end = source.index(b">", pos)
        row.empty_span = ((end - 1, end + 1, "empty") if source[end - 1:end] == b"/"
                          else (end + 1, end + 1, "text"))

    def end(name):
        flush()
        row = stack.pop()
        short = row.empty_span[2] == "empty"
        row.close_start = row.empty_span[0] if short else parser.CurrentByteIndex
        row.bounds = (row.open_start, parser.CurrentByteIndex if short else source.index(b">", row.close_start) + 1)
        children = row.children
        if not children.get_n_items():
            row.value = row.original = ""
            row.span = row.empty_span
        elif children.get_n_items() == 1 and children.get_item(0).name in ("#text", "#cdata-section"):
            child = children.get_item(0)
            row.value = row.original = child.value
            row.span = child.span
            children.remove_all()
        else:
            for i in reversed(range(children.get_n_items())):
                child = children.get_item(i)
                if child.name == "#text" and not child.value.strip():
                    children.remove(i)

    def begin_cdata():
        nonlocal cdata, text_start
        flush()
        cdata = True
        text_start = parser.CurrentByteIndex + len(b"<![CDATA[")

    def end_cdata():
        nonlocal cdata
        flush()
        cdata = False

    def comment(value):
        flush()
        start = parser.CurrentByteIndex + 4
        end = source.index(b"-->", start)
        row = XmlRow("#comment", value, (start, end, "comment"))
        row.bounds = (start - 4, end + 3)
        append(row)

    def instruction(name, value):
        flush()
        start = parser.CurrentByteIndex + 2 + len(name.encode())
        end = source.index(b"?>", start)
        value_start = start
        while value_start < end and source[value_start] in b" \t\r\n":
            value_start += 1
        row = XmlRow(name, value, (value_start, end, "pi" if value_start > start else "pi-space"))
        row.bounds = (parser.CurrentByteIndex, end + 2)
        append(row)

    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.CharacterDataHandler = text
    parser.StartCdataSectionHandler, parser.EndCdataSectionHandler = begin_cdata, end_cdata
    parser.CommentHandler, parser.ProcessingInstructionHandler = comment, instruction
    parser.Parse(source, True)
    pending = [(roots, ())]
    while pending:
        children, parent_path = pending.pop()
        for index, row in enumerate(children):
            row.path = parent_path + (index,)
            if row.children.get_n_items():
                pending.append((row.children, row.path))
    return roots


def replacement(row):
    value = row.value
    kind = row.span[2]
    if kind in ("'", '"'):
        return escape(value, {kind: "&apos;" if kind == "'" else "&quot;", "\t": "&#9;", "\r": "&#13;", "\n": "&#10;"})
    if kind == "empty":
        return ">" + escape(value) + "</" + row.name + ">"
    if kind == "text":
        return escape(value)
    if kind == "cdata":
        return value.replace("]]>", "]]]]><![CDATA[>")
    if kind == "comment" and ("--" in value or value.endswith("-")):
        raise DocumentError("An XML comment cannot contain -- or end with -.")
    if kind.startswith("pi") and "?>" in value:
        raise DocumentError("An XML processing instruction cannot contain ?>.")
    return (" " if kind == "pi-space" else "") + value


def row_at(roots, path):
    for index in path:
        row = roots.get_item(index)
        roots = row.children
    return row


def row_at_offset(roots, offset):
    # Simple text and CDATA can appear on their containing element's row.
    found = None
    while roots.get_n_items():
        row = next((r for r in roots if r.bounds[0] <= offset < r.bounds[1]), None)
        if row is None:
            break
        found, roots = row, row.children
    return found


@dataclass
class TreeChange:
    before: tuple
    after: tuple


def line_indent(xml, row, parent, roots):
    if parent is None or parent.value is not None or any(
            c.name in ("#text", "#cdata-section") for c in parent.children):
        return b""
    for depth in range(len(parent.path), 0, -1):
        ancestor = row_at(roots, parent.path[:depth])
        space = next((c for c in ancestor.children if c.name == "@xml:space"), None)
        if space:
            if space.value == "preserve":
                return b""
            break
    pos = row.bounds[0]
    start = pos
    while start and xml[start - 1] in b" \t":
        start -= 1
    if start and xml[start - 1] in b"\r\n":
        start -= 2 if xml[max(0, start - 2):start] == b"\r\n" else 1
        return xml[start:pos]
    return b""


def move_neighbor(roots, row, operation):
    siblings = row_at(roots, row.path[:-1]).children if len(row.path) > 1 else roots
    index = row.path[-1] + (-1 if operation == "move-up" else 1)
    if 0 <= index < siblings.get_n_items():
        neighbor = siblings.get_item(index)
        if row.name.startswith("@") == neighbor.name.startswith("@"):
            return neighbor
    return None


def node_splice(xml, roots, row, operation, name):
    """Return the range, replacement bytes and selection offset in the result."""
    start, end = row.bounds
    if operation in ("move-up", "move-down"):
        neighbor = move_neighbor(roots, row, operation)
        if neighbor is None:
            raise DocumentError("There is no sibling to move past in this direction.")
        left, right = (neighbor, row) if operation == "move-up" else (row, neighbor)
        first, first_end = left.bounds
        second, last = right.bounds
        # The gap belongs to the layout, including whitespace between attributes.
        gap = xml[first_end:second]
        swapped = xml[second:last] + gap + xml[first:first_end]
        selected = first if operation == "move-up" else first + (last - second) + len(gap)
        return first, last, swapped, selected

    parent = row_at(roots, row.path[:-1]) if len(row.path) > 1 else None
    attr = row.name.startswith("@")
    if operation in ("duplicate", "sibling", "delete") and row.element and parent is None:
        raise DocumentError("The document must keep one root element. Select a child or add a child to the root.")
    if operation in ("child", "attribute") and not row.element:
        raise DocumentError("Select the element to add content to.")
    if operation in ("sibling", "child", "attribute"):
        if not re.fullmatch(r"""[^\s<>&/'"=?!]+""", name):
            raise DocumentError("Enter a valid XML name.")
        tag = name.encode()

    if attr and operation in ("sibling", "duplicate", "delete"):
        sep = start
        while xml[sep - 1] in b" \r\n\t":
            sep -= 1
        if operation == "delete":
            return sep, end, b"", parent.bounds[0]
        if operation == "duplicate":
            names = {c.name for c in parent.children}
            base = row.name[1:] + "_copy"
            candidate = base
            n = 2
            while "@" + candidate in names:
                candidate = base + str(n)
                n += 1
            attribute = candidate.encode() + xml[start + len(row.name[1:].encode()):end]
        else:
            attribute = tag + b'=""'
        return end, end, xml[sep:start] + attribute, end + start - sep
    if operation == "attribute":
        pos = start + 1 + len(row.name.encode())
        for child in row.children:
            if not child.name.startswith("@"):
                break
            pos = child.bounds[1]
        return pos, pos, b" " + tag + b'=""', pos + 1
    if operation == "delete":
        padding = line_indent(xml, row, parent, roots)
        # A top-level comment or processing instruction can precede the root element.
        selection = parent.bounds[0] if parent else 0
        return start - len(padding), end, b"", selection
    if operation == "child":
        child_xml = b"<" + tag + b"/>"
        pos = row.close_start
        if row.empty_span[2] == "empty":
            return pos, end, b">" + child_xml + b"</" + row.name.encode() + b">", pos + 1
        content = [c for c in row.children if not c.name.startswith("@")]
        padding = b""
        if content:
            padding = line_indent(xml, content[-1], row, roots)
            if padding:
                pos = content[-1].bounds[1]
        return pos, pos, padding + child_xml, pos + len(padding)
    if operation in ("duplicate", "sibling"):
        padding = line_indent(xml, row, parent, roots)
        fragment = xml[start:end] if operation == "duplicate" else b"<" + tag + b"/>"
        return end, end, padding + fragment, end + len(padding)
    raise DocumentError("Unknown node operation.")


class Document:
    def __init__(self, path):
        self.path = Path(path)
        _, self.disk_bytes, _ = Gio.File.new_for_path(str(path)).load_contents(None)
        self.encoding = validate(self.disk_bytes)
        decoded = self.disk_bytes.decode(self.encoding)
        if decoded.encode(self.encoding) != self.disk_bytes:
            raise DocumentError("This file cannot be read and written byte for byte in its original encoding.")
        self.source = decoded.encode("utf-8")
        self.roots = parse_rows(self.source)
        self.modified = set()
        self.saved_xml = self.source
        self.undo_stack = []
        self.redo_stack = []

    def edit(self, row, value):
        if row.value == value:
            return
        self.undo_stack.append((row.path, row.value, value))
        self.redo_stack.clear()
        self._set_value(row, value)

    def step_history(self, redo):
        source, target = (self.redo_stack, self.undo_stack) if redo else (self.undo_stack, self.redo_stack)
        if not source:
            return None
        change = source.pop()
        if isinstance(change, TreeChange):
            xml, edits, selection = change.after if redo else change.before
            self.source, self.roots = xml, parse_rows(xml)
            self.modified.clear()
            for path, value in edits:
                self._set_value(row_at(self.roots, path), value)
            row = row_at(self.roots, selection)
        else:
            path, before, after = change
            row = row_at(self.roots, path)
            self._set_value(row, after if redo else before)
        target.append(change)
        return row

    def _set_value(self, row, value):
        row.value = value
        if value == row.original:
            self.modified.discard(row)
        else:
            self.modified.add(row)

    @property
    def dirty(self):
        if self.source == self.saved_xml:
            return bool(self.modified)
        try:
            return self.xml_bytes() != self.saved_xml
        except ValueError:
            return True

    def structure(self, row, operation, name=""):
        edits = [(r.path, r.value) for r in self.modified]
        before = self.source, edits, row.path
        xml = self.xml_bytes()
        roots = self.roots
        if self.modified:
            start = row.bounds[0]
            offset = start + sum(len(replacement(r).encode()) - (r.span[1] - r.span[0])
                                 for r in self.modified if r.span[1] <= start)
            roots = parse_rows(xml)
            current = row_at_offset(roots, offset)
            if current is None or current.bounds[0] != offset or current.name != row.name:
                raise DocumentError("This value has been merged or removed. Select its parent element.")
            row = current
        start, end, fragment, offset = node_splice(xml, roots, row, operation, name)
        updated = xml[:start] + fragment + xml[end:]
        validate(updated.decode().encode(self.encoding))
        roots = parse_rows(updated)
        selected = row_at_offset(roots, offset) or roots.get_item(0)
        self.undo_stack.append(TreeChange(before, (updated, (), selected.path)))
        self.redo_stack.clear()
        self.source, self.roots = updated, roots
        self.modified.clear()
        return selected

    def xml_bytes(self):
        if not self.modified:
            return self.source
        pieces = []
        pos = 0
        for row in sorted(self.modified, key=lambda row: row.span[:2]):
            start, end, _ = row.span
            pieces.extend((self.source[pos:start], replacement(row).encode()))
            pos = end
        pieces.append(self.source[pos:])
        return b"".join(pieces)

    def render(self):
        data = self.xml_bytes().decode("utf-8").encode(self.encoding)
        validate(data)
        return data

    def save(self, path):
        path = Path(path)
        target = Gio.File.new_for_path(str(path))
        same = path.resolve() == self.path.resolve()
        etag = None
        if same:
            _, current, etag = target.load_contents(None)
            if current != self.disk_bytes:
                raise DocumentError("The file on disk has changed. Use Save As to keep both versions.")
        data = self.render() if self.dirty else self.disk_bytes
        if not same or data != self.disk_bytes:
            target.replace_contents(data, etag, False, Gio.FileCreateFlags.NONE, None)
        self.path, self.disk_bytes = path, data
        self.saved_xml = self.xml_bytes()
