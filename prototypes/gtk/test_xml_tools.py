from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from document import Document, row_at
from comparison import comparison
from i18n import tr
from xml_tools import load_schema, schema_issues, xpath_result


class XmlToolsTest(unittest.TestCase):
    def test_comparison_distinguishes_byte_identity_encoding_endings_and_edits(self):
        self.assertEqual(comparison(b"<r/>", b"<r/>", "a", "b"), (tr("Files are byte-identical."), []))
        header, lines = comparison(b"<r/>", "<r/>".encode("utf-16"), "a", "b")
        self.assertIn("UTF-16", header)
        self.assertTrue(lines)
        _, lines = comparison(b"<r/>\r\n", b"<r/>\n", "a", "b")
        self.assertIn("-<r/>  ⟨CRLF⟩", lines)
        self.assertIn("+<r/>  ⟨LF⟩", lines)
        _, lines = comparison(b"<r>\n<a/>\n</r>", b"<r>\n<b/>\n</r>", "a", "b")
        self.assertIn("-<a/>", lines)
        self.assertIn("+<b/>", lines)

    def test_xpath_namespaces_mixed_content_attributes_and_scalars(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "含 空格.xml"
            original = "<?xml version='1.0' encoding='UTF-16'?><?top cmd?><r xmlns='urn:test' xmlns:p='urn:tag'><a p:v='茶'>前<b/>后</a><!--尾--></r>"
            path.write_bytes(original.encode("utf-16"))
            doc = Document(path)
            for query, bindings, name, value in (
                ("//default:a/@p:v", "", "@p:v", "茶"),
                ("//x:a/text()[last()]", "x=urn:test", "#text", "后"),
                ("//comment()", "", "#comment", "尾"),
                ("/processing-instruction()", "", "top", "cmd"),
            ):
                rows, scalar = xpath_result(doc, query, bindings)
                self.assertIsNone(scalar)
                self.assertEqual([(row.name, row.value) for row in rows], [(name, value)])
            row = xpath_result(doc, "//*[@p:v]/@p:v")[0][0]
            doc.edit(row, "更新")
            self.assertEqual(xpath_result(doc, "string(//*[@p:v]/@p:v)"), ([], "更新"))
            self.assertEqual(xpath_result(doc, "count(//default:a)"), ([], "1.0"))
            self.assertEqual(xpath_result(doc, "//missing"), ([], None))
            with self.assertRaises(ValueError):
                xpath_result(doc, "//[")

    def test_local_schema_includes_multiple_errors_and_jump_lines(self):
        with TemporaryDirectory() as temp:
            base = Path(temp) / "模型 甲"
            base.mkdir()
            types = base / "类型.xsd"
            types.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:simpleType name="number"><xs:restriction base="xs:integer"/></xs:simpleType></xs:schema>')
            main = base / "main.xsd"
            main.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="类型.xsd"/><xs:element name="r"><xs:complexType><xs:sequence><xs:element name="n" type="number" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element></xs:schema>')
            schema = load_schema(main)
            xml = base / "input.xml"
            xml.write_text("<r>\n<n>no</n>\n<n>bad</n>\n</r>")
            doc = Document(xml)
            issues = schema_issues(schema, doc.render())
            self.assertEqual([n for _, n, _ in issues], [2, 3])
            doc.edit_values([(row_at(doc.roots, (0, i)), "5") for i in (0, 1)])
            self.assertEqual(schema_issues(schema, doc.render()), [])
            (base.parent / "outside.xsd").write_bytes(types.read_bytes())
            for location in ("../outside.xsd", "https://invalid.example/test.xsd"):
                main.write_text(main.read_text().replace("类型.xsd", location))
                with self.assertRaises((ValueError, OSError)):
                    load_schema(main)
                main.write_text(main.read_text().replace(location, "类型.xsd"))


if __name__ == "__main__":
    unittest.main()
