#include "editor.h"
#include <QApplication>
#include <QMessageBox>

int main(int argc, char **argv) {
    QApplication app(argc, argv);
    QApplication::setApplicationName("XML Notepad");
    Editor window;
    const auto args = app.arguments();
    if (args.size() > 1 && !window.loadFile(args.at(1)))
        QMessageBox::warning(&window, "打开 XML", window.lastError());
    window.show();
    return app.exec();
}
