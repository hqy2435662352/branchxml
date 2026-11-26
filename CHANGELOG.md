# BranchXML releases

## 0.1.0

BranchXML opens local XML documents in a two-column GTK 4 editor on Ubuntu. A new document starts with a root element. The application menu, file manager and `branchxml FILE` command open the same editor.

- Edit values in the tree, use Tab to move between fields, or open a multiline editor for text and CDATA. Rename elements and attributes, insert mixed content, move siblings and transfer XML fragments with the clipboard. Changes share one undo history.
- Search collapsed branches by name or value. Replace literal text or regular expressions in one value or across the document. XPath 1.0 queries navigate to matching nodes and display scalar results.
- Drag complete subtrees onto or between elements, preserving namespace bindings. Jump between the selected tree node and its source position.
- Inspect highlighted XML source, compare unsaved edits or another local file, and attach an XSD 1.0 schema for live diagnostics. Selecting a diagnostic line opens the corresponding source location.
- Preserve original bytes outside edits and check for external changes before overwriting a file. The interface supports English and Simplified Chinese.
- Install with the architecture-independent Ubuntu package or run `./install.py` from the source archive for a user-level installation. The release includes SHA-256 checksums and the MIT license.

The source view is read-only. BranchXML supports XML documents without a DTD and schemas loaded from local files.
