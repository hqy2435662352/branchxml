#include "editor.h"
#include <QApplication>
#include <QFile>
#include <QXmlStreamReader>
#include <QTemporaryDir>
#include <QtTest/QTest>
#include <cstdlib>

#define CHECK(condition) do { if (!(condition)) qFatal("line %d: %s", __LINE__, #condition); } while (false)
static QByteArray readFile(const QString &path) {
    QFile file(path); CHECK(file.open(QIODevice::ReadOnly)); return file.readAll();
}
static void writeFile(const QString &path, const QByteArray &bytes) {
    QFile file(path); CHECK(file.open(QIODevice::WriteOnly)); CHECK(file.write(bytes) == bytes.size());
}

// Include whitespace, CDATA boundaries and comments in the comparison. Attribute order is immaterial.
static QStringList recipeContents(const QByteArray &bytes, bool expectEdit) {
    QXmlStreamReader reader(bytes);
    QStringList result;
    bool root = true;
    int depth = 0;
    while (!reader.atEnd()) {
        reader.readNext();
        if (reader.isStartElement()) {
            ++depth;
            result << "<" + reader.qualifiedName().toString();
            QMap<QString, QString> attrs;
            for (const auto &attr : reader.attributes())
                attrs.insert(attr.qualifiedName().toString(), attr.value().toString());
            if (root) {
                CHECK(reader.name() == u"recipe" && attrs.contains("name"));
                if (expectEdit) CHECK(attrs["name"] == "测试副本 & <>");
                attrs.remove("name");
                root = false;
            }
            for (auto it = attrs.begin(); it != attrs.end(); ++it) result << it.key() << it.value();
        } else if (reader.isEndElement()) {
            --depth;
            result << "</" + reader.qualifiedName().toString();
        } else if (depth && reader.isCharacters()) {
            result << (reader.isCDATA() ? "CDATA" : "text") << reader.text().toString();
        } else if (reader.isComment()) {
            result << "comment" << reader.text().toString();
        }
    }
    CHECK(!reader.hasError());
    return result;
}

int main(int argc, char **argv) {
    QApplication app(argc, argv);
    QTemporaryDir dir;
    CHECK(dir.isValid());
    const auto path = dir.filePath("input.xml");
    const QByteArray original = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<root xmlns:p=\"urn:p\">\n  <p:item a=\"1\">old</p:item>\n  <mixed>A<b/>B</mixed><!--ok--><![CDATA[raw]]></root>";
    writeFile(path, original);
    Editor editor;
    CHECK(editor.loadFile(path));
    editor.show();
    auto *tree = editor.findChild<QTreeWidget *>();
    tree->setFocus();
    QCoreApplication::processEvents();
    auto key = [&](Qt::Key k, Qt::KeyboardModifiers m = {}) {
        CHECK(app.focusWidget());
        QTest::keyClick(app.focusWidget(), k, m);
        QCoreApplication::processEvents();
    };
    auto namedRows = [&](const QString &name) { return tree->findItems(name, Qt::MatchExactly | Qt::MatchRecursive, 0); };
    auto *item = namedRows("p:item").value(0);
    CHECK(item);
    CHECK(item->text(0) == "p:item" && item->text(1) == "old");
    CHECK(editor.saveFile(path) && readFile(path) == original);
    tree->setCurrentItem(item, 0);
    key(Qt::Key_Return);
    auto box = [&]() { return qobject_cast<QPlainTextEdit *>(app.focusWidget()); };
    CHECK(box() && tree->visualItemRect(item).height() < 65);
    box()->insertPlainText("renamed");
    key(Qt::Key_Tab);
    CHECK(box() && box()->toPlainText() == "old" && tree->currentColumn() == 1);
    box()->insertPlainText("温度 & 值");
    key(Qt::Key_Tab);
    CHECK(tree->currentItem()->text(0) == "@a" && tree->currentColumn() == 0);
    key(Qt::Key_Backtab, Qt::ShiftModifier);
    CHECK(tree->currentItem() == item && tree->currentColumn() == 1);
    key(Qt::Key_F2);
    CHECK(box()); box()->insertPlainText("discard"); key(Qt::Key_Escape);
    CHECK(item->text(1) == "温度 & 值");
    key(Qt::Key_9); CHECK(box() && box()->toPlainText() == "9");
    key(Qt::Key_Return); key(Qt::Key_Z, Qt::ControlModifier);
    CHECK(tree->currentItem()->text(1) == "温度 & 值");
    key(Qt::Key_Y, Qt::ControlModifier);
    CHECK(tree->currentItem()->text(1) == "9");
    key(Qt::Key_Left);
    key(Qt::Key_Insert, Qt::AltModifier);
    CHECK(box()); box()->insertPlainText("limit"); key(Qt::Key_Tab);
    CHECK(box()); box()->insertPlainText("3&4"); key(Qt::Key_Return);
    key(Qt::Key_F6); key(Qt::Key_F2);
    CHECK(box()); box()->insertPlainText("a"); key(Qt::Key_Return);
    CHECK(box() && editor.lastError().contains("同名")); key(Qt::Key_Escape);
    CHECK(editor.saveFile(path));
    const auto saved = readFile(path);
    CHECK(saved.contains("limit=\"3&amp;4\"") && saved.contains("<mixed>A<b/>B</mixed>"));
    CHECK(saved.contains("<!--ok--><![CDATA[raw]]>"));
    CHECK(editor.loadFile(path));
    item = namedRows("renamed").value(0);
    CHECK(item);
    tree->setCurrentItem(item, 0);
    key(Qt::Key_D, Qt::ControlModifier);
    CHECK(tree->currentItem()->text(0) == "renamed" && namedRows("renamed").size() == 2 && tree->currentItem() == namedRows("renamed").last());
    key(Qt::Key_Delete);
    key(Qt::Key_Insert, Qt::ControlModifier);
    CHECK(box()); box()->insertPlainText("newChild"); key(Qt::Key_Tab);
    CHECK(box()); box()->insertPlainText("one"); key(Qt::Key_Return, Qt::ShiftModifier);
    box()->insertPlainText("two"); key(Qt::Key_S, Qt::ControlModifier);
    CHECK(readFile(path).contains("<newChild>one\ntwo</newChild>"));
    auto *newChild = tree->currentItem();
    tree->setCurrentItem(newChild, 1);
    const auto rect = tree->visualItemRect(newChild);
    const QPoint cell(tree->columnWidth(0) + 20, rect.center().y());
    QTest::mouseClick(tree->viewport(), Qt::LeftButton, {}, cell);
    QTest::mouseDClick(tree->viewport(), Qt::LeftButton, {}, cell);
    QCoreApplication::processEvents();
    CHECK(box()); box()->insertPlainText("鼠标编辑"); key(Qt::Key_Return);
    CHECK(newChild->text(1) == "鼠标编辑");
    writeFile(path, "<external/>");
    CHECK(!editor.saveFile(path) && readFile(path) == "<external/>");
    const auto copy = dir.filePath("copy.xml");
    CHECK(editor.saveFile(copy) && readFile(copy).contains("鼠标编辑"));
    writeFile(path, "<!DOCTYPE root><root/>");
    CHECK(!editor.loadFile(path) && editor.lastError().contains("DTD"));
    writeFile(path, "<bad>"); CHECK(!editor.loadFile(path));
    CHECK(tree->currentItem() == newChild);
    const auto recipes = app.arguments().mid(1);
    for (const auto &recipe : recipes) {
        const auto originalBytes = readFile(recipe);
        CHECK(editor.loadFile(recipe));
        CHECK(editor.saveFile(copy) && readFile(copy) == originalBytes);
        auto *name = tree->topLevelItem(0)->child(0);
        CHECK(name->text(0) == "@name");
        tree->setCurrentItem(name, 1);
        key(Qt::Key_Return); CHECK(box()); box()->insertPlainText("测试副本 & <>"); key(Qt::Key_Return);
        CHECK(editor.saveFile(copy));
        CHECK(recipeContents(originalBytes, false) == recipeContents(readFile(copy), true));
        CHECK(editor.loadFile(copy));
        CHECK(tree->topLevelItem(0)->child(0)->text(1) == "测试副本 & <>");
        if (QFileInfo(recipe).fileName() == "demo.xml") {
            auto summary = tree->findItems("summary", Qt::MatchExactly | Qt::MatchRecursive, 0);
            CHECK(summary.size() >= 2 && summary[1]->text(1).contains("薄荷"));
            tree->setCurrentItem(summary[1], 1);
            key(Qt::Key_Up); CHECK(tree->currentColumn() == 1);
            key(Qt::Key_Down); CHECK(tree->currentItem() == summary[1] && tree->currentColumn() == 1);
            key(Qt::Key_Return); CHECK(box());
            box()->insertPlainText("示例 <临时>"); key(Qt::Key_Return);
            CHECK(editor.saveFile(copy));
            CHECK(readFile(copy).contains("<summary><![CDATA[示例 <临时>]]></summary>"));
        }
    }
    qInfo() << "Recipe files checked:" << recipes.size();
}
