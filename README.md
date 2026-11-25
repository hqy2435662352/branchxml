# BranchXML

**English** · [简体中文](README.zh-CN.md)

BranchXML is a desktop XML reader and editor for Ubuntu, built with Python and GTK 4. Browse the tree on the left and edit attribute values or text on the right. Saving a change preserves the original formatting everywhere else in the file.

![Editing the second step’s summary in the value column. Its XML path appears below the tree.](docs/screenshots/tree-editing-en.png)

## Quick start

Use the system Python 3 with GTK 4.12 or later, PyGObject and Pygments. The corresponding Ubuntu packages are `python3`, `gir1.2-gtk-4.0`, `python3-gi` and `python3-pygments`.

From the repository root, run the following command to open the included herbal tea recipe.

```sh
/usr/bin/python3 prototypes/gtk/branchxml.py
```

BranchXML follows your desktop language preferences and falls back to English. Choose **View → Language** (**视图 → 语言**) to switch between **System Default**, **English** and **简体中文**. The interface updates immediately and remembers your choice. The system file chooser follows your desktop’s language settings.

In the second `step`, click the `5` next to `@minutes` and type a new steeping time. Press **Tab** to commit it and start editing the next value, the `summary` that reads “加入薄荷 & 柠檬” (add mint and lemon). Press **Esc** to discard edits to the summary and keep the new time.

To open your own XML file, pass its path on the command line or press **Ctrl+O** in the editor. **Ctrl+L** focuses the address bar. Relative paths resolve from the current document’s directory.

## Working in the tree

Icons and colors distinguish node types. A row stays under the pointer when you collapse or expand it, even at the end of a document. Reopening a parent restores each descendant’s previous expansion state.

| Action | How to use it |
| --- | --- |
| Edit a single-line value | Click the value or select its row and press **F2**. **Enter** commits the edit and **Esc** cancels it. |
| Edit consecutive values | **Tab** commits and advances to the next visible editable value. **Shift+Tab** moves back. A Chinese input method handles candidate selection first. |
| Open the node menu | Right-click either column on the target row, or select the row and press **Shift+F10** or the **Menu** key. |
| Add a node | **Insert** adds a sibling element or attribute. **Ctrl+Insert** adds a child element and **Alt+Insert** adds an attribute. Type the name and press **Enter**. |
| Duplicate or delete | **Ctrl+D** copies the selected node and its descendants immediately after the original. **Delete** removes the selected subtree. |
| Reorder siblings | **Alt+↑** or **Alt+↓** swaps the selection with the previous or next sibling. Child nodes move with their parent. |

Copying or moving an element preserves all its attribute values, including any sequence numbers in a recipe. Duplicating a single attribute gives the copy an available name. XML treats adjacent text nodes as one text node.

## Reading and searching the source

The **XML Source** tab shows a read-only view of the document, including committed edits you have yet to save. Element names, attribute names, strings, numbers and booleans have distinct colors.

Press **Ctrl+F** from either view to search for text, a tag name or an attribute value. Search is literal and case-insensitive. Every match is highlighted, and the counter shows which match you are reading. **Enter** or **F3** moves to the next match and **Shift+F3** moves to the previous one. Both directions wrap around. In the search field, **Esc** clears the query and returns focus to the source.

![Searching the XML source for “minutes”. Both occurrences are highlighted and the counter shows the second of two matches.](docs/screenshots/source-search-en.png)

In the lower pane, **Check XML** checks document syntax and namespaces. Errors include the line and column when the parser supplies them. **Node Info** shows the selected node’s path and its value or child count. Drag the dividers to adjust the width of the node column or the height of the lower pane.

## Saving and undoing changes

**Ctrl+S** saves the file. **Ctrl+Shift+S** saves a copy and continues editing that file. Both actions commit the active field and check the XML before writing. If another program has changed the original on disk, BranchXML prompts you to save a separate copy. Opening another file or closing the window with unsaved edits gives you the choice to save, discard or cancel.

Changing one value preserves the indentation, attribute quotes, entity spellings, CDATA, byte order mark and line endings outside that edit. Structural edits also affect only the relevant XML fragments. Adding text to a self-closing element produces a matching pair of tags. Reading and saving have been tested with UTF-8 and UTF-16 files. Opening a document with a DTD reports an error.

**Ctrl+Z** undoes a change. **Ctrl+Shift+Z** or **Ctrl+Y** redoes it. Each value changed with Tab and each node operation is a separate undo step. While typing, undo acts on the active field first. Saving keeps the undo history, and opening another file starts a new history.

## Running the tests

From the repository root in an Ubuntu graphical session, run the full suite for keyboard editing, tree folding, source search and byte-for-byte save behavior.

```sh
/usr/bin/python3 -m unittest discover -s prototypes/gtk
```

For document I/O and undo tests alone, run `/usr/bin/python3 prototypes/gtk/test_document.py`. Chinese candidate selection, Tab navigation and Esc cancellation have also been checked on Wayland with Fcitx 4 and Sogou Pinyin.
