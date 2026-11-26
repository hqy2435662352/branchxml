"""XML values and their original source ranges, for local edits without reformatting."""

from dataclasses import dataclass
import re
from pathlib import Path
from xml.parsers import expat
from xml.sax.saxutils import escape, quoteattr

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
    def __init__(self, name, value=None, span=None, element=False):
        super().__init__()
        self.name = name
        self.value = self.original = value
        self.span = span
        self.bounds = span[:2] if span else None
        self.element = element
        self.children = Gio.ListStore.new(XmlRow) if element else EMPTY_CHILDREN


# Only elements can acquire children while a document is being parsed.
EMPTY_CHILDREN = Gio.ListStore.new(XmlRow)


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
CLIPBOARD_ATTRIBUTE = re.compile(r"""^\s*[^\s<>&/'"=?!]+\s*=\s*['"]""")


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
        row = XmlRow(name, element=True)
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


def walk_rows(roots):
    """All rows in document order, independent of which branches are open."""
    pending = [iter(roots)]
    while pending:
        row = next(pending[-1], None)
        if row is None:
            pending.pop()
            continue
        yield row
        if row.children.get_n_items():
            pending.append(iter(row.children))


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


def namespaces(roots, path):
    bindings = {}
    for depth in range(1, len(path) + 1):
        for attr in row_at(roots, path[:depth]).children:
            if attr.name == "@xmlns" or attr.name.startswith("@xmlns:"):
                bindings[attr.name[1:]] = attr.value
    return bindings


def pasted_attributes(xml, roots, owner, fragment):
    wrapped = b"<clip " + fragment + b"/>"
    clip = parse_rows(wrapped).get_item(0)
    if clip.bounds != (0, len(wrapped)) or clip.empty_span[2] != "empty":
        raise DocumentError("Paste an attribute or a balanced XML fragment.")
    scope = namespaces(roots, owner.path)
    pieces = []
    for attr in clip.children:
        name = attr.name[1:]
        if name in scope:
            if scope[name] != attr.value:
                raise DocumentError("The namespace {name} already has a different binding here.", name=name)
            continue
        start, end = attr.bounds
        pieces.append(wrapped[start:end])
    if not pieces:
        raise DocumentError("The selected element already has these namespace declarations.")
    pos = owner.open_start + 1 + len(owner.name.encode())
    for attr in owner.children:
        if not attr.name.startswith("@"):
            break
        pos = attr.bounds[1]
    return pos, pos, b" " + b" ".join(pieces), pos + 1


def clipboard_fragment(text, default_namespace):
    data = re.sub(rb"^(?:\xef\xbb\xbf)?<\?xml\s+[^?]*\?>[\r\n]*", b"", text.encode(), count=1)
    if not data:
        raise DocumentError("The clipboard is empty.")
    prefix = b"<clip>"
    try:
        wrapped = parse_rows(prefix + data + b"</clip>").get_item(0)
    except expat.ExpatError:
        if b"<" in data:
            raise
        return escape(text).encode()
    if default_namespace:
        # An unqualified subtree copied from a document with no default namespace
        # must keep those expanded names in a default-namespaced destination.
        for child in reversed(list(wrapped.children)):
            if child.element and not any(a.name == "@xmlns" for a in child.children):
                pos = child.open_start - len(prefix) + len(child.name.encode()) + 1
                data = data[:pos] + b' xmlns=""' + data[pos:]
    return data


def content_xml(kind, value, target=""):
    if kind == "text":
        if not value:
            raise DocumentError("Enter some text to add.")
        return escape(value)
    if kind == "cdata":
        return "<![CDATA[" + value.replace("]]>", "]]]]><![CDATA[>") + "]]>"
    if kind == "comment":
        if "--" in value or value.endswith("-"):
            raise DocumentError("An XML comment cannot contain -- or end with -.")
        return "<!--" + value + "-->"
    if kind == "pi":
        if not re.fullmatch(r"""[^\s<>&/'"=?!]+""", target):
            raise DocumentError("Enter a valid XML name.")
        if "?>" in value:
            raise DocumentError("An XML processing instruction cannot contain ?>.")
        return "<?" + target + (" " + value if value else "") + "?>"
    raise DocumentError("Unknown node operation.")


def element_fragment(xml, roots, row, destination):
    start, end = row.bounds
    inherited = namespaces(roots, row.path[:-1])
    if destination.get("xmlns"):
        inherited.setdefault("xmlns", "")
    local = {attr.name[1:] for attr in row.children if attr.name.startswith("@")}
    bindings = "".join(" " + key + "=" + quoteattr(value) for key, value in inherited.items()
                       if key not in local and destination.get(key) != value).encode()
    pos = start + len(row.name.encode()) + 1
    return xml[start:pos] + bindings + xml[pos:end]


def append_child(xml, roots, row, fragment, indent=True):
    pos = row.close_start
    if row.empty_span[2] == "empty":
        return pos, row.bounds[1], b">" + fragment + b"</" + row.name.encode() + b">", pos + 1
    padding = b""
    if indent:
        last = next((c for c in reversed(list(row.children)) if not c.name.startswith("@")), None)
        if last:
            padding = line_indent(xml, last, row, roots)
            if padding:
                pos = last.bounds[1]
    return pos, pos, padding + fragment, pos + len(padding)


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
    if operation in ("child", "attribute", "content") and not row.element:
        raise DocumentError("Select the element to add content to.")
    if operation in ("sibling", "child", "attribute", "rename"):
        if not re.fullmatch(r"""[^\s<>&/'"=?!]+""", name):
            raise DocumentError("Enter a valid XML name.")
        tag = name.encode()

    if operation == "rename":
        if attr:
            return start, start + len(row.name[1:].encode()), tag, start
        if not row.element:
            raise DocumentError("Select an element or attribute to rename.")
        old_length = len(row.name.encode())
        if row.empty_span[2] == "empty":
            return start + 1, start + 1 + old_length, tag, start
        close_name = row.close_start + 2
        middle = xml[start + 1 + old_length:close_name]
        return start + 1, close_name + old_length, tag + middle + tag, start

    if operation in ("paste", "paste-after"):
        owner = row if row.element else parent
        if CLIPBOARD_ATTRIBUTE.match(name):
            if owner is None:
                raise DocumentError("Select the element to add content to.")
            return pasted_attributes(xml, roots, owner, name.strip().encode())
        as_child = operation == "paste" and row.element
        if attr:
            row, as_child = parent, True
            start, end = row.bounds
        scope = namespaces(roots, row.path if as_child else row.path[:-1])
        fragment = clipboard_fragment(name, scope.get("xmlns"))
        if not as_child:
            padding = line_indent(xml, row, parent, roots)
            return end, end, padding + fragment, end + len(padding)

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
    if operation in ("child", "content", "paste", "paste-after"):
        if operation == "child":
            child_xml = b"<" + tag + b"/>"
        elif operation == "content":
            child_xml = content_xml(*name).encode()
        else:
            child_xml = fragment
        return append_child(xml, roots, row, child_xml, indent=operation != "content")
    if operation in ("duplicate", "sibling"):
        padding = line_indent(xml, row, parent, roots)
        fragment = xml[start:end] if operation == "duplicate" else b"<" + tag + b"/>"
        return end, end, padding + fragment, end + len(padding)
    raise DocumentError("Unknown node operation.")


class Document:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        if self.path is None:
            self.disk_bytes = b'<?xml version="1.0" encoding="UTF-8"?>\n<root/>\n'
        else:
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
        self.edit_values([(row, value)])

    def edit_values(self, updates):
        changes = [(row, row.value, value) for row, value in updates if row.value != value]
        if changes:
            self.undo_stack.append([(row.path, before, after) for row, before, after in changes])
            self.redo_stack.clear()
            for row, before, after in changes:
                self._set_value(row, after)
        return len(changes)

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
            for path, before, after in change:
                self._set_value(row_at(self.roots, path), after if redo else before)
            row = row_at(self.roots, change[0][0])
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

    def current_node(self, row):
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
        return xml, roots, row

    def copy_node(self, row):
        xml, roots, row = self.current_node(row)
        start, end = row.bounds
        fragment = xml[start:end]
        if row.element:
            fragment = element_fragment(xml, roots, row, {})
        elif row.name.startswith("@") and ":" in row.name and not row.name.startswith("@xmlns:"):
            inherited = namespaces(roots, row.path[:-1])
            key = "xmlns:" + row.name[1:].split(":", 1)[0]
            if key in inherited:
                fragment = (key + "=" + quoteattr(inherited[key]) + " ").encode() + fragment
        fragment = fragment.decode()
        if row.name == "#text" and CLIPBOARD_ATTRIBUTE.match(fragment):
            # A character reference keeps assignment-shaped text distinct from an attribute on paste.
            return f"&#{ord(fragment[0])};" + fragment[1:]
        return fragment

    def row_at_source_position(self, offset):
        # Source view offsets include pending replacements. Map gaps back into
        # the original byte stream and hits inside a replacement to its editor row.
        delta = 0
        for row in sorted(self.modified, key=lambda item: item.span[:2]):
            start, end, _ = row.span
            if offset < start + delta:
                break
            length = len(replacement(row).encode())
            if offset < start + delta + length:
                return row
            delta += length - (end - start)
        return row_at_offset(self.roots, offset - delta)

    def structure(self, row, operation, name=""):
        if operation == "rename" and name == row.name.removeprefix("@") and (row.element or row.name.startswith("@")):
            return row
        old_path = row.path
        xml, roots, row = self.current_node(row)
        start, end, fragment, offset = node_splice(xml, roots, row, operation, name)
        updated = xml[:start] + fragment + xml[end:]
        return self.apply_structure(updated, offset, old_path)

    def move_element(self, source, target, position):
        if position not in ("before", "inside", "after") or not source.element or not target.element:
            raise DocumentError("Choose two elements to move a subtree.")
        if len(source.path) == 1 or (len(target.path) == 1 and position != "inside"):
            raise DocumentError("The document must keep one root element. Select a child or add a child to the root.")
        if target.path[:len(source.path)] == source.path:
            raise DocumentError("An element cannot be moved inside itself.")
        old_path = source.path
        parent_path = target.path if position == "inside" else target.path[:-1]
        if source.path[:-1] == parent_path:
            if ((position == "inside" and source.path[-1] == target.children.get_n_items() - 1)
                or (position == "before" and source.path[-1] + 1 == target.path[-1])
                or (position == "after" and source.path[-1] - 1 == target.path[-1])):
                return source
        xml, roots, source = self.current_node(source)
        _, _, target = self.current_node(target)
        dest_scope = namespaces(roots, target.path if position == "inside" else target.path[:-1])
        fragment = element_fragment(xml, roots, source, dest_scope)
        start, end, _, _ = node_splice(xml, roots, source, "delete", "")
        cut = xml[:start] + xml[end:]
        offset = target.bounds[0]
        if end <= offset:
            offset -= end - start
        cut_roots = parse_rows(cut)
        target = row_at_offset(cut_roots, offset)
        if position == "inside":
            start, end, fragment, selected = append_child(cut, cut_roots, target, fragment)
        else:
            padding = line_indent(cut, target, row_at(cut_roots, target.path[:-1]), cut_roots)
            if position == "before":
                start = end = selected = target.bounds[0]
                fragment += padding
            else:
                start = end = target.bounds[1]
                selected = start + len(padding)
                fragment = padding + fragment
        return self.apply_structure(cut[:start] + fragment + cut[end:], selected, old_path)

    def apply_structure(self, updated, offset, old_path):
        validate(updated.decode().encode(self.encoding))
        roots = parse_rows(updated)
        selected = row_at_offset(roots, offset) or roots.get_item(0)
        before = self.source, [(r.path, r.value) for r in self.modified], old_path
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
        same = self.path is not None and path.resolve() == self.path.resolve()
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
