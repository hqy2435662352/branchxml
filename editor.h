#pragma once
#include <QDomDocument>
#include <QMainWindow>
#include <QTreeWidget>
#include <QPointer>
#include <QPlainTextEdit>

class Row : public QTreeWidgetItem {
public:
    explicit Row(QDomNode node) : node(node) {}
    QDomNode node;
};

class Editor : public QMainWindow {
public:
    Editor();
    bool loadFile(const QString &name);
    bool saveFile(const QString &name);
    QString lastError() const { return error; }

protected:
    bool eventFilter(QObject *target, QEvent *event) override;
    void closeEvent(QCloseEvent *event) override;

private:
    struct State {
        QDomDocument doc;
        QList<int> selection;
        int column;
        quint64 revision;
    };
    QTreeWidget *tree;
    QPointer<QPlainTextEdit> input;
    Row *editing = nullptr;
    int editColumn = 0;
    QDomDocument doc;
    QString path, error;
    QByteArray diskBytes;
    quint64 revision = 0, savedRevision = 0, sequence = 0;
    QList<State> undo, redo;

    Row *current() const;
    void populate(QDomNode selected = {}, int column = 0, bool initial = false);
    Row *addRow(const QDomNode &node, QTreeWidgetItem *parent);
    void beginEdit(const QString &replacement = {});
    bool endEdit(bool accept);
    void step(bool backward, bool continueEdit = false);
    void structure(int key, Qt::KeyboardModifiers mods);
    State snapshot() const;
    void changed(State before);
    void history(bool forward);
    bool report(const QString &message);
    bool confirmChanges();
    bool save(bool chooseName);
    void title();
};
