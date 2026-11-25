"""Byte-for-byte save checks, independent of the graphical display."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.parsers.expat import ExpatError

from document import Document, row_at
from i18n import tr


class SaveTest(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "in.xml"
        self.copy = self.path.with_name("copy.xml")

    def test_attribute_only_then_save_as_and_revert(self):
        original = (b"\xef\xbb\xbf<?xml version='1.0'?>\r\n<r a = 'x&#x26;y' b=\"x&amp;y\">"
                    b"<!-- x&amp;y --><e />\r\n</r>")
        self.path.write_bytes(original)
        doc = Document(self.path)
        attr = doc.roots.get_item(0).children.get_item(0)
        doc.edit(attr, "x&y")
        self.assertFalse(doc.dirty)
        doc.save(self.copy)
        self.assertEqual(self.copy.read_bytes(), original)
        doc.edit(attr, "茶'&<")
        doc.save(self.copy)
        expected = original.replace(b"x&#x26;y", "茶&apos;&amp;&lt;".encode())
        self.assertEqual(self.copy.read_bytes(), expected)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(Document(self.copy).roots.get_item(0).children.get_item(0).value, "茶'&<")
        doc.edit(attr, "x&y")
        doc.save(self.copy)
        self.assertEqual(self.copy.read_bytes(), original)

    def test_history_across_save_and_diverging_edits(self):
        original = b"\xef\xbb\xbf<r a = 'A&#38;B'><b><![CDATA[tea]]></b></r>\r\n"
        self.path.write_bytes(original)
        doc = Document(self.path)
        a, b = doc.roots.get_item(0).children
        doc.edit(a, "first")
        doc.edit(b, "second")
        doc.edit(a, "third")
        doc.save(self.copy)
        for row, expected in ((a, "first"), (b, "tea"), (a, "A&B")):
            self.assertIs(doc.step_history(False), row)
            self.assertEqual(row.value, expected)
        self.assertIsNone(doc.step_history(False))
        self.assertTrue(doc.dirty)
        doc.save(self.copy)
        self.assertEqual(self.copy.read_bytes(), original)
        doc.edit(b, "tea")  # Passing through a field keeps the redo chain.
        for row, expected in ((a, "first"), (b, "second"), (a, "third")):
            self.assertIs(doc.step_history(True), row)
            self.assertEqual(row.value, expected)
        self.assertIsNone(doc.step_history(True))
        doc.step_history(False)
        doc.edit(b, "different")
        self.assertIsNone(doc.step_history(True))

    def test_cdata_empty_element_and_text_in_utf16(self):
        original = "<?xml version='1.0' encoding='UTF-16'?><r><a><![CDATA[]]></a><b /><c>A&amp;B</c></r>"
        self.path.write_bytes(original.encode("utf-16"))
        doc = Document(self.path)
        a, b, c = doc.roots.get_item(0).children
        doc.edit(a, "茶 & 水")
        doc.edit(b, "<")
        doc.edit(c, "A&B2")
        doc.save(self.path)
        expected = original.replace("CDATA[]", "CDATA[茶 & 水]").replace("<b />", "<b >&lt;</b>").replace("B</c>", "B2</c>")
        self.assertEqual(self.path.read_bytes(), expected.encode("utf-16"))
        self.assertEqual([r.value for r in Document(self.path).roots.get_item(0).children], ["茶 & 水", "<", "A&B2"])

    def test_invalid_xml_and_external_change_preserve_both_versions(self):
        self.path.write_bytes(b"<r>old</r>")
        doc = Document(self.path)
        row = doc.roots.get_item(0)
        doc.edit(row, "bad\x01value")
        with self.assertRaises(ExpatError):
            doc.save(self.path)
        self.assertEqual(self.path.read_bytes(), b"<r>old</r>")
        self.assertTrue(doc.dirty)
        doc.edit(row, "mine")
        self.path.write_bytes(b"<r>theirs</r>")
        with self.assertRaises(ValueError) as conflict:
            doc.save(self.path)
        self.assertEqual(str(conflict.exception), tr("The file on disk has changed. Use Save As to keep both versions."))
        self.assertTrue(doc.dirty)
        doc.save(self.copy)
        self.assertEqual(self.copy.read_bytes(), b"<r>mine</r>")
        self.assertEqual(self.path.read_bytes(), b"<r>theirs</r>")

    def test_structural_and_value_history_share_one_timeline(self):
        original = (b"\xef\xbb\xbf<r>\r\n  <task n='&#49;'><s><![CDATA[A&B]]></s></task>"
                    b"\r\n</r>")
        self.path.write_bytes(original)
        doc = Document(self.path)
        task = row_at(doc.roots, (0, 0))
        doc.edit(task.children.get_item(0), "longer")
        clone = doc.structure(task, "duplicate")
        self.assertEqual(clone.path, (0, 1))
        doc.edit(clone.children.get_item(0), "copy")
        doc.save(self.copy)
        copy_xml = self.copy.read_bytes()
        expected = (b"\xef\xbb\xbf<r>\r\n  <task n='longer'><s><![CDATA[A&B]]></s></task>"
                    b"\r\n  <task n='copy'><s><![CDATA[A&B]]></s></task>\r\n</r>")
        self.assertEqual(copy_xml, expected)
        doc.structure(clone, "delete")
        self.assertEqual(doc.step_history(False).children.get_item(0).value, "copy")
        self.assertFalse(doc.dirty)
        self.assertEqual(doc.step_history(False).value, "longer")
        self.assertEqual(doc.step_history(False).path, (0, 0))
        self.assertEqual(doc.step_history(False).value, "1")
        doc.save(self.copy)
        self.assertEqual(self.copy.read_bytes(), original)
        for _ in range(4):
            doc.step_history(True)
        doc.save(self.copy)
        self.assertEqual(self.copy.read_bytes(), original.replace(b"&#49;", b"longer"))

    def test_add_in_self_closing_element_and_duplicate_attribute(self):
        original = "<?xml version='1.0' encoding='UTF-16'?><r xmlns:p='urn:test'><p:e /></r>"
        self.path.write_bytes(original.encode("utf-16"))
        doc = Document(self.path)
        child = doc.structure(row_at(doc.roots, (0, 1)), "child", "p:茶")
        attr = doc.structure(child, "attribute", "温度")
        doc.edit(attr, "80")
        clone = doc.structure(attr, "duplicate")
        self.assertEqual((clone.name, clone.value), ("@温度_copy", "80"))
        doc.edit(clone, "90")
        doc.save(self.copy)
        reopened = Document(self.copy)
        elem = row_at(reopened.roots, child.path)
        self.assertEqual([(a.name, a.value) for a in elem.children], [("@温度", "80"), ("@温度_copy", "90")])
        doc.structure(clone, "delete")
        for _ in range(6):
            doc.step_history(False)
        doc.save(self.copy)
        self.assertEqual(self.copy.read_bytes(), self.path.read_bytes())

    def test_invalid_structure_is_atomic(self):
        self.path.write_bytes(b"<r a='1'><child/></r>")
        doc = Document(self.path)
        root = doc.roots.get_item(0)
        child = root.children.get_item(1)
        doc.structure(child, "duplicate")
        doc.step_history(False)
        root = doc.roots.get_item(0)
        for op, name in (("delete", ""), ("duplicate", ""), ("child", 'x a="1"'),
                         ("attribute", "a"), ("child", "unbound:child")):
            with self.assertRaises((ValueError, ExpatError)):
                doc.structure(root, op, name)
        self.assertFalse(doc.dirty)
        self.assertEqual(doc.step_history(True).path, (0, 2))

    def test_significant_whitespace_survives_structural_edit(self):
        for body in (b"<r xml:space='preserve'>\r\n  <x/>\r\n</r>",
                     b"<r>before\n  <x/> after</r>"):
            self.path.write_bytes(body)
            doc = Document(self.path)
            node = next(c for c in doc.roots.get_item(0).children if c.name == "x")
            clone = doc.structure(node, "duplicate")
            self.assertEqual(doc.render(), body.replace(b"<x/>", b"<x/><x/>"))
            doc.structure(clone, "delete")
            self.assertEqual(doc.render(), body)

    def test_move_subtree_with_pending_edit_and_undo_after_save(self):
        first = b"<task id='a'><s><![CDATA[A&B]]></s></task>"
        second = b'<task id="b"><param v="&#49;"/></task>'
        gap = b"\r\n\t"
        original = b"<r>" + first + gap + second + b"</r>"
        self.path.write_bytes(original)
        doc = Document(self.path)
        doc.edit(row_at(doc.roots, (0, 0, 0)), "longer")
        selected = doc.structure(row_at(doc.roots, (0, 1)), "move-up")
        self.assertEqual(selected.path, (0, 0))
        changed_first = first.replace(b"'a'", b"'longer'")
        doc.save(self.copy)
        self.assertEqual(self.copy.read_bytes(), b"<r>" + second + gap + changed_first + b"</r>")
        self.assertEqual(doc.step_history(False).path, (0, 1))
        self.assertEqual(doc.render(), original.replace(first, changed_first))
        self.assertEqual(doc.step_history(True).path, (0, 0))
        self.assertFalse(doc.dirty)
        reopened = Document(self.copy)
        moved = reopened.structure(row_at(reopened.roots, (0, 0)), "move-down")
        self.assertEqual(moved.path, (0, 1))
        reopened.save(self.copy)
        self.assertEqual(self.copy.read_bytes(), original.replace(first, changed_first))

    def test_attribute_order_and_move_boundaries(self):
        self.path.write_bytes(b"<r a = '1'\n  b=\"2\"><c/></r>")
        doc = Document(self.path)
        moved = doc.structure(row_at(doc.roots, (0, 0)), "move-down")
        self.assertEqual(moved.name, "@a")
        self.assertEqual(doc.render(), b"<r b=\"2\"\n  a = '1'><c/></r>")
        for path, operation in (((0, 1), "move-down"), ((0, 2), "move-up"), ((0,), "move-up")):
            with self.assertRaises(ValueError):
                doc.structure(row_at(doc.roots, path), operation)
        self.assertEqual(len(doc.undo_stack), 1)
        doc.structure(moved, "move-up")
        self.assertFalse(doc.dirty)

    def test_dtd_rejected_during_open(self):
        self.path.write_bytes(b'<!DOCTYPE r [<!ENTITY item "text">]><r>&item;</r>')
        with self.assertRaisesRegex(ValueError, "DTD"):
            Document(self.path)


if __name__ == "__main__":
    unittest.main()
