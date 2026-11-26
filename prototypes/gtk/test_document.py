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

    def test_new_document_rename_and_grouped_value_undo(self):
        doc = Document()
        self.assertIsNone(doc.path)
        root = doc.structure(doc.roots.get_item(0), "rename", "配方")
        a = doc.structure(root, "attribute", "n")
        b = doc.structure(a, "duplicate")
        a = row_at(doc.roots, a.path)
        self.assertEqual(doc.edit_values([(a, "茶"), (b, "水")]), 2)
        doc.save(self.copy)
        self.assertIn('n="茶" n_copy="水"', self.copy.read_text())
        doc.step_history(False)
        self.assertIn(b'n="" n_copy=""', doc.render())
        doc.step_history(True)
        doc.structure(row_at(doc.roots, a.path), "rename", "数量")
        with self.assertRaises((ValueError, ExpatError)):
            doc.structure(row_at(doc.roots, a.path), "rename", "n_copy")
        self.assertIn('数量="茶"', doc.render().decode())

    def test_clipboard_preserves_namespaces_layout_and_undo(self):
        original = b"<r xmlns:p='urn:one'><p:a k='1'><plain/><!--note--></p:a></r>"
        self.path.write_bytes(original)
        src = Document(self.path)
        src.edit(row_at(src.roots, (0, 1, 0)), "changed")
        branch = src.copy_node(row_at(src.roots, (0, 1)))
        self.copy.write_bytes(b"<dest xmlns='urn:other' xmlns:p='urn:two'/>")
        dst = Document(self.copy)
        original_dest = dst.render()
        pasted = dst.structure(dst.roots.get_item(0), "paste", branch)
        from xml.etree.ElementTree import fromstring
        child = fromstring(dst.render())[0]
        self.assertEqual((child.tag, child[0].tag, child.get("k")), ("{urn:one}a", "plain", "changed"))
        renamed = dst.structure(pasted, "rename", "p:b")
        self.assertEqual(renamed.name, "p:b")
        self.assertIn(b"</p:b>", dst.render())
        for _ in range(2):
            dst.step_history(False)
        self.assertEqual(dst.render(), original_dest)
        dst.step_history(True)
        self.assertIn(b"<!--note-->", dst.render())
        previous = dst.render()
        with self.assertRaises((ValueError, ExpatError)):
            dst.structure(dst.roots.get_item(0), "paste", "</dest><other/>")
        self.assertEqual(dst.render(), previous)
        self.assertEqual(self.path.read_bytes(), original)

    def test_clipboard_attribute_bindings(self):
        self.path.write_bytes(b"<r xmlns:p='urn:id'><a p:id='8'/><b/></r>")
        doc = Document(self.path)
        clip = doc.copy_node(row_at(doc.roots, (0, 1, 0)))
        self.assertIn("xmlns:p", clip)
        attr = doc.structure(row_at(doc.roots, (0, 2)), "paste", clip)
        self.assertEqual(attr.name, "@p:id")
        self.assertIn(b"<b p:id='8'/>", doc.render())
        prev = doc.render()
        with self.assertRaises(ValueError):
            doc.structure(row_at(doc.roots, (0, 2)), "paste", "xmlns:p='urn:other' p:id='9'")
        self.assertEqual(doc.render(), prev)

    def test_clipboard_preserves_text_that_looks_like_an_attribute_and_whitespace(self):
        self.path.write_text("<r><a/>颜色='绿'<b/></r>")
        doc = Document(self.path)
        text = doc.copy_node(row_at(doc.roots, (0, 1)))
        pasted = doc.structure(row_at(doc.roots, (0, 2)), "paste", text)
        self.assertEqual((pasted.name, pasted.value), ("b", "颜色='绿'"))
        doc.structure(row_at(doc.roots, (0, 0)), "paste", "  ")
        self.assertIn(b"<a>  </a>", doc.render())
        doc.step_history(False)
        doc.step_history(False)
        self.assertEqual(doc.render(), self.path.read_bytes())

    def test_create_mixed_content_then_undo_to_exact_original(self):
        original = b"<r a='1' />"
        self.path.write_bytes(original)
        doc = Document(self.path)
        for fields in (("text", "A & B", ""), ("cdata", "茶]]>水", ""),
                       ("comment", "note", ""), ("pi", "one", "step")):
            doc.structure(doc.roots.get_item(0), "content", fields)
        self.assertIn(b"A &amp; B", doc.render())
        self.assertIn(b"<!--note--><?step one?>", doc.render())
        self.assertIn(b"]]]]><![CDATA[>", doc.render())
        for fields in (("comment", "--", ""), ("pi", "bad?>", "p"), ("pi", "x", "invalid target")):
            with self.assertRaises(ValueError):
                doc.structure(doc.roots.get_item(0), "content", fields)
        for _ in range(4):
            doc.step_history(False)
        self.assertEqual(doc.render(), original)

    def test_drag_subtree_is_one_edit_with_namespace_fixup(self):
        from xml.etree.ElementTree import fromstring
        original = b"<r>\r\n  <a xmlns:p='urn:one'><p:task id='x'><plain/></p:task></a>\r\n  <b xmlns='urn:two'/>\r\n</r>"
        self.path.write_bytes(original)
        doc = Document(self.path)
        a, b = doc.roots.get_item(0).children
        task = a.children.get_item(1)
        doc.edit(task.children.get_item(0), "longer")
        moved = doc.move_element(task, b, "inside")
        self.assertEqual(moved.name, "p:task")
        tree = fromstring(doc.render())
        self.assertEqual((tree[1][0].tag, tree[1][0][0].tag, tree[1][0].get("id")),
                         ("{urn:one}task", "plain", "longer"))
        with self.assertRaises(ValueError):
            doc.move_element(row_at(doc.roots, (0, 1)), moved, "inside")
        self.assertEqual(len(doc.undo_stack), 2)
        doc.step_history(False)
        self.assertEqual(doc.render(), original.replace(b"id='x'", b"id='longer'"))
        doc.step_history(True)
        doc.save(self.copy)
        self.assertEqual(fromstring(self.copy.read_bytes())[1][0].tag, "{urn:one}task")
        doc.step_history(False)
        doc.step_history(False)
        self.assertEqual(doc.render(), original)

    def test_drag_before_and_after_keep_sibling_layout(self):
        self.path.write_bytes(b"<r xmlns='ns'>\n  <a/>\n  <b/>\n  <c/>\n</r>")
        doc = Document(self.path)
        attr, a, b, c = doc.roots.get_item(0).children
        doc.move_element(c, a, "before")
        self.assertEqual(doc.render(), b"<r xmlns='ns'>\n  <c/>\n  <a/>\n  <b/>\n</r>")
        attr, c, a, b = doc.roots.get_item(0).children
        doc.move_element(c, b, "after")
        self.assertEqual(doc.render(), self.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
