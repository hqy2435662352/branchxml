#include "editor.h"
#include <QApplication>
#include <QCloseEvent>
#include <QFileDialog>
#include <QHeaderView>
#include <QKeyEvent>
#include <QMenuBar>
#include <QMessageBox>
#include <QSet>
#include <QRegularExpression>
#include <QSaveFile>
#include <QStatusBar>
#include <QTimer>
#include <QXmlStreamReader>
#include <algorithm>

namespace {
class CellEditor : public QPlainTextEdit {
public:
    using QPlainTextEdit::QPlainTextEdit;
    QSize sizeHint() const override {
        const int lines = std::clamp(document()->blockCount(), 1, 5);
        return QSize(100, std::max(28, fontMetrics().lineSpacing() * lines + 8));
    }
};

bool simple(const QDomNode &node) {
    const auto child = node.firstChild();
    return node.isElement() && (child.isNull() ||
        ((child.nodeType() == QDomNode::TextNode || child.isCDATASection()) && child.nextSibling().isNull()));
}
bool editable(const QDomNode &node, int column) {
    if (!column) return node.isElement() || (node.isAttr() && node.nodeName() != "xmlns" &&
                                              !node.nodeName().startsWith("xmlns:"));
    return simple(node) || node.isAttr() || node.isCharacterData() || node.isProcessingInstruction();
}
QString value(const QDomNode &node) {
    return node.isElement() ? node.firstChild().nodeValue() : node.nodeValue();
}
QString label(const QDomNode &node) {
    if (node.isAttr()) return "@" + node.nodeName();
    return node.nodeName();
}
// Validate namespaces separately: the DOM keeps the original qualified names for editing.
QString checkXml(const QByteArray &bytes) {
    QXmlStreamReader xml(bytes);
    while (!xml.atEnd()) {
        const auto token = xml.readNext();
        if (token == QXmlStreamReader::DTD) return "原型暂不支持含 DTD 的文档。";
        if (token == QXmlStreamReader::StartDocument && !xml.documentEncoding().isEmpty() &&
            xml.documentEncoding().compare(u"UTF-8", Qt::CaseInsensitive) != 0)
            return "原型支持 UTF-8 编码，请将副本转换为 UTF-8 后打开。";
    }
    if (xml.hasError())
        return QString("第 %1 行，第 %2 列：%3").arg(xml.lineNumber()).arg(xml.columnNumber()).arg(xml.errorString());
    return {};
}
QList<int> rowPath(QTreeWidgetItem *row) {
    QList<int> result;
    while (row && row->treeWidget()) {
        auto *parent = row->parent();
        result.prepend(parent ? parent->indexOfChild(row) : row->treeWidget()->indexOfTopLevelItem(row));
        row = parent;
    }
    return result;
}
QString uniqueName(const QDomElement &parent, QString base) {
    QString name = base;
    for (int i = 2; parent.hasAttribute(name); ++i) name = base + QString::number(i);
    return name;
}
}

Editor::Editor() : tree(new QTreeWidget(this)) {
    setCentralWidget(tree);
    resize(900, 600);
    tree->setColumnCount(2);
    tree->setHeaderLabels({"节点", "值"});
    tree->setAccessibleName("XML 节点与值");
    tree->setColumnWidth(0, 350);
    tree->header()->setSectionsMovable(false);
    tree->setSelectionBehavior(QAbstractItemView::SelectItems);
    tree->setEditTriggers(QAbstractItemView::NoEditTriggers);
    tree->setExpandsOnDoubleClick(false);
    tree->setAlternatingRowColors(true);
    tree->setStyleSheet("QTreeView::item { padding: 3px 2px; } QHeaderView::section { padding: 5px; }");
    tree->installEventFilter(this);
    tree->viewport()->installEventFilter(this);
    connect(tree, &QTreeWidget::itemDoubleClicked, this, [this](QTreeWidgetItem *, int) { beginEdit(); });

    auto *file = menuBar()->addMenu("文件(&F)");
    file->addAction("打开…", QKeySequence::Open, this, [this] {
        const auto name = QFileDialog::getOpenFileName(this, "打开 XML", path, "XML (*.xml *.xsd *.svg);;所有文件 (*)");
        if (!name.isEmpty() && confirmChanges() && !loadFile(name)) QMessageBox::warning(this, "打开 XML", error);
    });
    file->addAction("保存", QKeySequence::Save, this, [this] { save(false); });
    file->addAction("另存为…", QKeySequence::SaveAs, this, [this] { save(true); });
    auto *edit = menuBar()->addMenu("编辑(&E)");
    // Keep typing undo local to the active text editor.
    edit->addAction("撤销", this, [this] { if (input) input->undo(); else history(false); });
    edit->addAction("重做", this, [this] { if (input) input->redo(); else history(true); });
    auto addCommand = [this, edit](QString name, int key, Qt::KeyboardModifiers mods) {
        edit->addAction(name, this, [this, key, mods] { if (endEdit(true)) structure(key, mods); });
    };
    addCommand("插入同类节点    Ins", Qt::Key_Insert, {});
    addCommand("添加子元素    Ctrl+Ins", Qt::Key_Insert, Qt::ControlModifier);
    addCommand("添加属性    Alt+Ins", Qt::Key_Insert, Qt::AltModifier);
    addCommand("复制节点    Ctrl+D", Qt::Key_D, Qt::ControlModifier);
    addCommand("删除节点    Del", Qt::Key_Delete, {});
    doc.appendChild(doc.createElement("root"));
    populate({}, 0, true);
    tree->setFocus();
    title();
    statusBar()->showMessage("Tab 切换名称与值　·　Enter / F2 编辑　·　Esc 取消　·　Ctrl+O 打开");
}

Row *Editor::current() const { return static_cast<Row *>(tree->currentItem()); }

Row *Editor::addRow(const QDomNode &node, QTreeWidgetItem *parent) {
    auto *row = new Row(node);
    parent->addChild(row);
    row->setText(0, label(node));
    if (editable(node, 1)) row->setText(1, value(node));
    else row->setBackground(1, palette().alternateBase());
    if (node.isElement()) {
        const auto attrs = node.attributes();
        QList<QDomNode> sorted;
        for (int i = 0; i < attrs.count(); ++i) sorted << attrs.item(i);
        std::sort(sorted.begin(), sorted.end(), [](const auto &a, const auto &b) { return a.nodeName() < b.nodeName(); });
        for (const auto &attr : sorted) addRow(attr, row);
        if (!simple(node)) {
            static const QRegularExpression nonSpace("[^ \\t\\r\\n]");
            bool showWhitespace = false;
            for (auto ancestor = node.toElement(); !ancestor.isNull(); ancestor = ancestor.parentNode().toElement()) {
                if (ancestor.hasAttribute("xml:space")) {
                    showWhitespace = ancestor.attribute("xml:space") == "preserve";
                    break;
                }
            }
            for (auto n = node.firstChild(); !showWhitespace && !n.isNull(); n = n.nextSibling())
                showWhitespace = n.isCDATASection() || (n.isText() && n.nodeValue().contains(nonSpace));
            for (auto child = node.firstChild(); !child.isNull(); child = child.nextSibling()) {
                // Hide indentation rows, but keep whitespace inside mixed or space-preserving content.
                if (child.nodeType() == QDomNode::TextNode && !child.nodeValue().contains(nonSpace) &&
                    !showWhitespace) continue;
                addRow(child, row);
            }
        }
    }
    return row;
}

void Editor::populate(QDomNode selected, int column, bool initial) {
    QSet<QList<int>> open;
    if (!initial) {
        for (QTreeWidgetItemIterator it(tree); *it; ++it)
            if ((*it)->isExpanded()) open << rowPath(*it);
    }
    tree->clear();
    for (auto n = doc.firstChild(); !n.isNull(); n = n.nextSibling()) {
        if (n.isProcessingInstruction() && n.nodeName() == "xml") continue;
        addRow(n, tree->invisibleRootItem());
    }
    auto *choice = tree->topLevelItem(0);
    for (QTreeWidgetItemIterator it(tree); *it; ++it) {
        auto *row = static_cast<Row *>(*it);
        if (row->node == selected || (selected.isNull() && row->node == doc.documentElement())) choice = row;
        if (initial ? rowPath(row).size() <= 2 : open.contains(rowPath(row))) row->setExpanded(true);
    }
    if (initial) {
        int count = 0;
        for (QTreeWidgetItemIterator it(tree); *it && count <= 55; ++it) ++count;
        if (count <= 55) tree->expandAll();
    }
    tree->setCurrentItem(choice, column);
    if (choice) tree->scrollToItem(choice);
    if (initial) tree->scrollToTop();
}

bool Editor::report(const QString &message) {
    error = message;
    statusBar()->showMessage(message);
    return false;
}
void Editor::title() {
    setWindowTitle(QString("%1%2 — XML Notepad").arg(revision == savedRevision ? "" : "*",
        path.isEmpty() ? QString("未命名") : QFileInfo(path).fileName()));
}

bool Editor::loadFile(const QString &name) {
    QFile file(name);
    if (!file.open(QIODevice::ReadOnly)) return report(file.errorString());
    const auto bytes = file.readAll();
    if (file.error() != QFileDevice::NoError) return report(file.errorString());
    const auto problem = checkXml(bytes);
    if (!problem.isEmpty()) return report(problem);
    if (!bytes.isValidUtf8() || bytes.contains('\0')) return report("原型只支持 UTF-8 编码。");
    QDomDocument loaded;
    const auto result = loaded.setContent(bytes, QDomDocument::ParseOption::PreserveSpacingOnlyNodes);
    if (!result) return report(result.errorMessage);
    endEdit(false);
    doc = loaded;
    path = QFileInfo(file).canonicalFilePath();
    diskBytes = bytes;
    undo.clear(); redo.clear();
    revision = savedRevision = ++sequence;
    populate({}, 0, true);
    title();
    statusBar()->showMessage("已打开 " + path);
    return true;
}

bool Editor::saveFile(const QString &name) {
    if (!endEdit(true)) return false;
    const QFileInfo info(name);
    const auto target = info.exists() ? info.canonicalFilePath() : info.absoluteFilePath();
    if (!path.isEmpty() && target == path) {
        QFile original(path);
        if (!original.open(QIODevice::ReadOnly) || original.readAll() != diskBytes || original.error())
            return report("磁盘上的文件已变更或无法读取。请另存为，再核对两个文件。");
    }
    QByteArray bytes = diskBytes;
    if (revision != savedRevision || path.isEmpty()) {
        bytes = doc.toByteArray(-1);
        if (diskBytes.startsWith("\xEF\xBB\xBF")) bytes.prepend("\xEF\xBB\xBF");
    }
    const auto problem = checkXml(bytes);
    if (!problem.isEmpty()) return report(problem);
    QSaveFile out(target);
    if (!out.open(QIODevice::WriteOnly) || out.write(bytes) != bytes.size() || !out.commit())
        return report(out.errorString());
    path = target; diskBytes = bytes; savedRevision = revision;
    title();
    statusBar()->showMessage("已保存 " + path);
    return true;
}

bool Editor::save(bool chooseName) {
    if (!endEdit(true)) return false;
    const auto name = (chooseName || path.isEmpty()) ? QFileDialog::getSaveFileName(this, "保存 XML", path, "XML (*.xml);;所有文件 (*)") : path;
    if (name.isEmpty()) return false;
    if (saveFile(name)) return true;
    QMessageBox::warning(this, "保存 XML", error);
    return false;
}
bool Editor::confirmChanges() {
    if (!endEdit(true)) return false;
    if (revision == savedRevision) return true;
    const auto answer = QMessageBox::question(this, "保存修改", "是否先保存当前文档？",
        QMessageBox::Save | QMessageBox::Discard | QMessageBox::Cancel, QMessageBox::Save);
    return answer == QMessageBox::Discard || (answer == QMessageBox::Save && save(false));
}
void Editor::closeEvent(QCloseEvent *event) {
    if (confirmChanges()) event->accept(); else event->ignore();
}

Editor::State Editor::snapshot() const {
    return {doc.cloneNode(true).toDocument(), rowPath(current()), tree->currentColumn(), revision};
}
void Editor::changed(State before) {
    undo << std::move(before);
    if (undo.size() > 32) undo.removeFirst();
    redo.clear();
    revision = ++sequence;
    title();
}
void Editor::history(bool forward) {
    auto &from = forward ? redo : undo;
    auto &to = forward ? undo : redo;
    if (from.isEmpty()) return;
    to << snapshot();
    const auto state = from.takeLast();
    doc = state.doc;
    revision = state.revision;
    populate();
    auto *item = tree->invisibleRootItem();
    for (int i : state.selection) {
        if (!item || i >= item->childCount()) break;
        item = item->child(i);
    }
    if (item != tree->invisibleRootItem()) tree->setCurrentItem(item, state.column);
    title();
}

void Editor::beginEdit(const QString &replacement) {
    if (input || !current()) return;
    editing = current();
    editColumn = tree->currentColumn();
    if (!editable(editing->node, editColumn)) {
        editing = nullptr;
        report("此单元格没有可编辑的名称或值。");
        return;
    }
    auto *box = new CellEditor(tree);
    input = box;
    box->setAccessibleName(editColumn ? "编辑节点值" : "编辑节点名称");
    box->setFrameStyle(QFrame::NoFrame);
    box->setTabChangesFocus(false);
    box->document()->setDocumentMargin(2);
    box->setPlainText(editColumn ? value(editing->node) : editing->node.nodeName());
    box->selectAll();
    if (!replacement.isNull()) box->insertPlainText(replacement);
    editing->setSizeHint(editColumn, box->sizeHint());
    connect(box, &QPlainTextEdit::blockCountChanged, box, [this, box] {
        if (input == box && editing) {
            box->updateGeometry();
            editing->setSizeHint(editColumn, box->sizeHint());
        }
    });
    tree->setItemWidget(editing, editColumn, box);
    box->installEventFilter(this);
    box->setFocus();
    statusBar()->showMessage("Enter 提交　·　Esc 取消　·　Tab 提交并前进　·　Shift+Enter 换行");
}

bool Editor::endEdit(bool accept) {
    if (!input) return true;
    auto &node = editing->node;
    const auto old = editColumn ? value(node) : node.nodeName();
    const auto text = input->toPlainText();
    if (accept && old != text) {
        if (!editColumn) {
            QXmlStreamReader nameCheck("<" + text + "/>");
            nameCheck.setNamespaceProcessing(false);
            if (!nameCheck.readNextStartElement() || nameCheck.qualifiedName() != text ||
                text.count(':') > 1 || text.startsWith(':') || text.endsWith(':'))
                return report("名称无效，请输入合法的 XML 名称，或按 Esc 取消。");
            if (node.isAttr() && node.toAttr().ownerElement().hasAttribute(text))
                return report("此元素已有同名属性。");
        } else {
            for (char32_t c : text.toUcs4())
                if ((c < 32 && c != 9 && c != 10 && c != 13) || c == 0xfffe || c == 0xffff)
                    return report("值中包含 XML 1.0 不允许的字符。");
            if ((node.isComment() && (text.contains("--") || text.endsWith('-'))) ||
                ((node.isCDATASection() || (simple(node) && node.firstChild().isCDATASection())) && text.contains("]]>")) ||
                (node.isProcessingInstruction() && text.contains("?>")))
                return report("该节点的值包含 XML 不允许的结束标记。");
        }
        const auto originalChild = node.firstChild();
        auto set = [&](const QString &s) {
            if (!editColumn && node.isElement()) node.toElement().setTagName(s);
            else if (!editColumn) {
                auto elem = node.toAttr().ownerElement();
                const auto attrValue = node.nodeValue();
                elem.removeAttribute(node.nodeName());
                elem.setAttribute(s, attrValue);
                node = elem.attributeNode(s);
            } else if (node.isElement()) {
                if (node.firstChild().isNull()) node.appendChild(doc.createTextNode(s));
                else node.firstChild().setNodeValue(s);
            } else node.setNodeValue(s);
        };
        auto before = snapshot();
        set(text);
        const auto problem = checkXml(doc.toByteArray(-1));
        if (!problem.isEmpty()) {
            set(old);
            if (node.isElement() && editColumn && originalChild.isNull()) node.removeChild(node.firstChild());
            return report(problem);
        }
        editing->setText(editColumn, editColumn ? text : label(node));
        changed(std::move(before));
    }
    auto *box = input.data();
    input.clear();
    box->removeEventFilter(this);
    tree->removeItemWidget(editing, editColumn);
    editing->setSizeHint(editColumn, {});
    editing = nullptr;
    statusBar()->showMessage("Tab 切换名称与值　·　Enter / F2 编辑　·　Ctrl+S 保存");
    return true;
}

void Editor::step(bool backward, bool continueEdit) {
    auto *row = current();
    if (!row) return;
    const int column = tree->currentColumn();
    QTreeWidgetItem *next = row;
    if (!column && backward) next = tree->itemAbove(row);
    if (column && !backward) next = tree->itemBelow(row);
    tree->setCurrentItem(next ? next : row, 1 - column);
    tree->setFocus();
    if (continueEdit && !column && !backward && editable(current()->node, 1)) beginEdit();
}

void Editor::structure(int key, Qt::KeyboardModifiers mods) {
    if (!current()) return;
    auto node = current()->node;
    auto parent = node.isAttr() ? QDomNode(node.toAttr().ownerElement()) : node.parentNode();
    const bool child = key == Qt::Key_Insert && mods != Qt::NoModifier;
    const bool attr = child ? mods == Qt::AltModifier : node.isAttr();
    if (child) parent = node.isElement() ? node : parent;
    if (!parent.isElement()) { report("该操作需要父元素，文档必须保留一个根元素。"); return; }
    auto before = snapshot();
    QDomNode selected;
    if (key == Qt::Key_Delete) {
        if (node.isAttr()) parent.toElement().removeAttributeNode(node.toAttr());
        else parent.removeChild(node);
        selected = parent;
    } else if (attr) {
        auto elem = parent.toElement();
        const auto name = uniqueName(elem, key == Qt::Key_D ? node.nodeName() : "attribute");
        elem.setAttribute(name, key == Qt::Key_D ? node.nodeValue() : QString());
        selected = elem.attributeNode(name);
    } else {
        QDomNode added;
        if (key == Qt::Key_D) added = node.cloneNode(true);
        else if (child || node.isElement()) added = doc.createElement("element");
        else if (node.isComment()) added = doc.createComment("comment");
        else if (node.isCDATASection()) added = doc.createCDATASection("text");
        else if (node.isProcessingInstruction()) added = doc.createProcessingInstruction("instruction", "");
        else added = doc.createTextNode("text");
        selected = child ? parent.appendChild(added) : parent.insertAfter(added, node);
    }
    const auto problem = checkXml(doc.toByteArray(-1));
    if (!problem.isEmpty()) {
        doc = before.doc;
        populate();
        report(problem);
        return;
    }
    changed(std::move(before));
    populate(selected, selected.isCharacterData() || selected.isProcessingInstruction() ? 1 : 0);
    if (key == Qt::Key_Insert && current()) beginEdit();
}

bool Editor::eventFilter(QObject *target, QEvent *event) {
    if (target == tree->viewport()) {
        if (input && event->type() == QEvent::MouseButtonPress && !endEdit(true)) {
            input->setFocus();
            return true;
        }
        return false;
    }
    if (input && target == input && event->type() == QEvent::FocusOut) {
        auto *focus = static_cast<QFocusEvent *>(event);
        if (focus->reason() != Qt::PopupFocusReason && focus->reason() != Qt::ActiveWindowFocusReason) {
            if (!endEdit(true)) {
                auto *box = input.data();
                QTimer::singleShot(0, box, [box] { box->setFocus(); });
            }
        }
        return false;
    }
    if (event->type() != QEvent::KeyPress) return false;
    auto *k = static_cast<QKeyEvent *>(event);
    const int key = k->key();
    const auto mods = k->modifiers();
    const bool tab = key == Qt::Key_Tab || key == Qt::Key_Backtab;
    const bool backward = key == Qt::Key_Backtab || mods.testFlag(Qt::ShiftModifier);
    const bool enter = key == Qt::Key_Enter || key == Qt::Key_Return;
    if (input && target == input) {
        if (enter && mods == Qt::ShiftModifier && editColumn) { input->insertPlainText("\n"); return true; }
        if (tab || enter || key == Qt::Key_Escape) {
            if (!endEdit(key != Qt::Key_Escape)) return true;
            tree->setFocus();
            if (tab) step(backward, true);
            return true;
        }
        return false;
    }
    if (target != tree || !current() || input) return false;
    if (tab) { step(backward); return true; }
    if (key == Qt::Key_F6) { tree->setCurrentItem(current(), 1 - tree->currentColumn()); return true; }
    if (enter || key == Qt::Key_F2) { beginEdit(); return true; }
    if (k->matches(QKeySequence::Undo)) { history(false); return true; }
    if (k->matches(QKeySequence::Redo) || (mods == Qt::ControlModifier && key == Qt::Key_Y)) { history(true); return true; }
    if ((key == Qt::Key_Insert && (mods == Qt::NoModifier || mods == Qt::ControlModifier || mods == Qt::AltModifier)) ||
        (key == Qt::Key_Delete && mods == Qt::NoModifier) || (key == Qt::Key_D && mods == Qt::ControlModifier)) {
        structure(key, mods); return true;
    }
    if (mods == Qt::NoModifier && key == Qt::Key_Left && tree->currentColumn() == 1) {
        tree->setCurrentItem(current(), 0); return true;
    }
    if (mods == Qt::NoModifier && key == Qt::Key_Right && tree->currentColumn() == 0 && !current()->childCount()) {
        tree->setCurrentItem(current(), 1); return true;
    }
    if (!(mods & (Qt::ControlModifier | Qt::AltModifier | Qt::MetaModifier)) &&
        !k->text().isEmpty() && k->text().front().isPrint()) {
        beginEdit(k->text()); return true;
    }
    return false;
}
