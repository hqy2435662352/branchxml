"""XML values and their original source ranges, for local edits without reformatting."""

import re
from pathlib import Path
from xml.parsers import expat
from xml.sax.saxutils import escape

from gi.repository import Gio, GObject


class XmlRow(GObject.Object):
    def __init__(self, name, value=None, span=None):
        super().__init__()
        self.name = name
        self.value = self.original = self.saved = value
        self.span = span
        self.children = Gio.ListStore.new(XmlRow)


def validate(data):
    """Check XML and namespace rules before using source offsets or writing bytes."""
    encoding = "utf-8"

    def declaration(version, declared, standalone):
        nonlocal encoding
        encoding = declared or encoding

    def reject_dtd(*args):
        raise ValueError("不支持含 DTD 的 XML")

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
            append(XmlRow("#cdata-section" if cdata else "#text", "".join(chunks),
                          (text_start, parser.CurrentByteIndex, kind)))
            chunks.clear()

    def start(name, attrs):
        flush()
        row = XmlRow(name)
        append(row)
        stack.append(row)
        pos = parser.CurrentByteIndex + 1 + len(name.encode())
        for key, value in zip(attrs[::2], attrs[1::2]):
            match = ATTRIBUTE.match(source, pos)
            if match is None:
                raise ValueError(f"无法定位 {name} 的属性 {key}")
            first, last = match.span(2)
            row.children.append(XmlRow("@" + key, value, (first, last, match[1].decode())))
            pos = match.end()
        end = source.index(b">", pos)
        row.empty_span = ((end - 1, end + 1, "empty") if source[end - 1:end] == b"/"
                          else (end + 1, end + 1, "text"))

    def end(name):
        flush()
        row = stack.pop()
        children = row.children
        if not children.get_n_items():
            row.value = row.original = row.saved = ""
            row.span = row.empty_span
        elif children.get_n_items() == 1 and children.get_item(0).name in ("#text", "#cdata-section"):
            child = children.get_item(0)
            row.value = row.original = row.saved = child.value
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
        append(XmlRow("#comment", value, (start, source.index(b"-->", start), "comment")))

    def instruction(name, value):
        flush()
        start = parser.CurrentByteIndex + 2 + len(name.encode())
        end = source.index(b"?>", start)
        value_start = start
        while value_start < end and source[value_start] in b" \t\r\n":
            value_start += 1
        append(XmlRow(name, value, (value_start, end, "pi" if value_start > start else "pi-space")))

    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.CharacterDataHandler = text
    parser.StartCdataSectionHandler, parser.EndCdataSectionHandler = begin_cdata, end_cdata
    parser.CommentHandler, parser.ProcessingInstructionHandler = comment, instruction
    parser.Parse(source, True)
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
        raise ValueError("XML 注释不能含有 -- 或以 - 结尾")
    if kind.startswith("pi") and "?>" in value:
        raise ValueError("XML 处理指令不能含有 ?>")
    return (" " if kind == "pi-space" else "") + value


class Document:
    def __init__(self, path):
        self.path = Path(path)
        _, self.disk_bytes, _ = Gio.File.new_for_path(str(path)).load_contents(None)
        self.encoding = validate(self.disk_bytes)
        decoded = self.disk_bytes.decode(self.encoding)
        if decoded.encode(self.encoding) != self.disk_bytes:
            raise ValueError("此文件的编码无法逐字节往返转换")
        self.source = decoded.encode("utf-8")
        self.roots = parse_rows(self.source)
        self.modified = set()
        self.dirty = set()
        self.undo_stack = []
        self.redo_stack = []

    def edit(self, row, value):
        if row.value == value:
            return
        self.undo_stack.append((row, row.value, value))
        self.redo_stack.clear()
        self._set_value(row, value)

    def step_history(self, redo):
        source, target = (self.redo_stack, self.undo_stack) if redo else (self.undo_stack, self.redo_stack)
        if not source:
            return None
        change = source.pop()
        row, before, after = change
        self._set_value(row, after if redo else before)
        target.append(change)
        return row

    def _set_value(self, row, value):
        row.value = value
        for rows, baseline in ((self.modified, row.original), (self.dirty, row.saved)):
            if value == baseline:
                rows.discard(row)
            else:
                rows.add(row)

    def render(self):
        pieces = []
        pos = 0
        for row in sorted(self.modified, key=lambda row: row.span[:2]):
            start, end, _ = row.span
            pieces.extend((self.source[pos:start], replacement(row).encode()))
            pos = end
        pieces.append(self.source[pos:])
        data = b"".join(pieces).decode("utf-8").encode(self.encoding)
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
                raise ValueError("磁盘文件已被修改。请另存为新文件以保留两份内容。")
        data = self.render() if self.dirty else self.disk_bytes
        if not same or data != self.disk_bytes:
            target.replace_contents(data, etag, False, Gio.FileCreateFlags.NONE, None)
        self.path, self.disk_bytes = path, data
        for row in self.dirty:
            row.saved = row.value
        self.dirty.clear()
