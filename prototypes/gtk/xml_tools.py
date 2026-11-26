"""XPath selection and local XSD validation for the current document."""
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from document import DocumentError, validate


def xml_library():
    try:
        from lxml import etree
    except ImportError as error:
        raise DocumentError("Install python3-lxml to use XPath and XML Schema.") from error
    return etree


def markup_rows(children):
    return (row for row in children if row.element or
            (row.span and row.span[2] in ("comment", "pi", "pi-space")))


def xpath_result(document, expression, bindings=""):
    etree = xml_library()
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, strip_cdata=False)
    try:
        tree = etree.fromstring(document.render(), parser).getroottree()
        prefixes = {}
        default = None
        for node in tree.iter():
            if not isinstance(node.tag, str):
                continue
            for prefix, uri in node.nsmap.items():
                if prefix:
                    prefixes.setdefault(prefix, uri)
                elif uri and default is None:
                    default = uri
        if default:
            prefix = "default"
            while prefix in prefixes:
                prefix += "_"
            prefixes[prefix] = default
        for entry in bindings.split():
            prefix, sep, uri = entry.partition("=")
            if not prefix or not sep or not uri:
                raise DocumentError("Enter namespace bindings as prefix=URI.")
            prefixes[prefix] = uri
        result = tree.xpath(expression, namespaces=prefixes)
    except etree.Error as error:
        raise ValueError(str(error)) from error

    if not isinstance(result, list):
        return [], str(result)
    if not result:
        return [], None
    # libxml2 and the editor both expose markup nodes in document order.
    # Map identities rather than relying on element names or source line numbers.
    pairs = list(zip(tree.xpath("/node()"), markup_rows(document.roots), strict=True))
    owners = {}
    while pairs:
        element, row = pairs.pop()
        owners[element] = row
        pairs.extend(zip(element, markup_rows(row.children), strict=True))
    rows, values = [], []
    seen = set()
    for item in result:
        if isinstance(item, etree._Element):
            row = owners[item]
        elif isinstance(item, etree._ElementUnicodeResult) and item.getparent() is not None:
            parent = item.getparent()
            row = owners[parent]
            if item.is_attribute:
                key = item.attrname
                if key.startswith("{"):
                    uri, local = key[1:].split("}", 1)
                    names = {prefix + ":" + local for prefix, ns in parent.nsmap.items() if prefix and ns == uri}
                    if uri == "http://www.w3.org/XML/1998/namespace":
                        names.add("xml:" + local)
                else:
                    names = {key}
                row = next(child for child in row.children if child.name.startswith("@") and child.name[1:] in names)
            elif item.is_text or item.is_tail:
                start = 0
                if item.is_tail:
                    start = row.path[-1] + 1
                    row = owners[parent.getparent()]
                for child in list(row.children)[start:]:
                    if child.element or child.name == "#comment":
                        break
                    if child.name in ("#text", "#cdata-section") and child.value == item:
                        row = child
                        break
        else:
            values.append(str(item))
            continue
        if row.path not in seen:
            rows.append(row)
            seen.add(row.path)
    return rows, "\n".join(values) if values else None


def load_schema(path):
    etree = xml_library()
    path = Path(path).resolve()
    base = path.parent

    def schema_document(filename):
        data = filename.read_bytes()
        validate(data)
        root = etree.fromstring(data, parser, base_url=filename.as_uri())
        # libxml2 expects URI-escaped file references, including non-ASCII names.
        for item in root.iter():
            location = item.get("schemaLocation")
            if location:
                item.set("schemaLocation", quote(location, safe="/:%?#[]@!$&'()*+,;="))
        return root

    class LocalSchemaFiles(etree.Resolver):
        def resolve(self, url, public_id, context):
            parts = urlsplit(url)
            target = (base / unquote(parts.path)).resolve()
            if parts.scheme not in ("", "file") or parts.netloc or not target.is_relative_to(base):
                raise DocumentError("Schema includes must be local files inside the selected schema folder.")
            return self.resolve_string(etree.tostring(schema_document(target)), context, base_url=target.as_uri())

    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    parser.resolvers.add(LocalSchemaFiles())
    try:
        return etree.XMLSchema(schema_document(path))
    except etree.Error as error:
        raise ValueError(str(error)) from error


def schema_issues(schema, data):
    etree = xml_library()
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    try:
        document = etree.fromstring(data, parser)
        if schema.validate(document):
            return []
    except etree.Error as error:
        raise ValueError(str(error)) from error
    return [(entry.message, entry.line, entry.column) for entry in schema.error_log]
