"""Byte-for-byte save checks, independent of the graphical display."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.parsers.expat import ExpatError

from document import Document


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
        with self.assertRaisesRegex(ValueError, "磁盘文件"):
            doc.save(self.path)
        self.assertTrue(doc.dirty)
        doc.save(self.copy)
        self.assertEqual(self.copy.read_bytes(), b"<r>mine</r>")
        self.assertEqual(self.path.read_bytes(), b"<r>theirs</r>")

    def test_dtd_rejected_during_open(self):
        self.path.write_bytes(b'<!DOCTYPE r [<!ENTITY item "text">]><r>&item;</r>')
        with self.assertRaisesRegex(ValueError, "DTD"):
            Document(self.path)


if __name__ == "__main__":
    unittest.main()
