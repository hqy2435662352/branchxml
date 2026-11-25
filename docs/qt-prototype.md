# Qt 6 对照原型

这是 BranchXML 早期的 C++ / Qt 6 实现。它保留了节点名和值两栏的键盘导航，供对照桌面编辑手感。当前 GTK 编辑器的启动方式见[项目首页](../README.md)。

## 构建和运行

需要 C++17、CMake、Qt 6.5 或更高版本的 Widgets、Xml 和 Test 模块。以下命令均在仓库根目录运行。

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
./build/xml-notepad examples/demo.xml
```

左栏展开节点和属性，右栏双击就地改值。属性以 `@` 开头。仅含文本或单段 CDATA 的元素直接在该行显示内容，混合内容按子节点显示。展开第二个 `step`，双击右栏的 `summary` 可以编辑「加入薄荷 & 柠檬」，按 Enter 提交。

## 键盘操作

| 按键 | 操作 |
| --- | --- |
| Tab / Shift+Tab | 从名称到同行的值，再到下一可见节点的名称，或反向移动。在名称编辑框按 Tab 会继续编辑该行的值。 |
| ↑ / ↓、Home / End、Page Up / Down | 在可见节点间移动。 |
| ← / → | 折叠或展开树。在值栏按 ← 返回名称，在无子节点的名称上按 → 转到值。 |
| F6 / Shift+F6 | 在同一行的两栏之间切换。 |
| Enter / F2、直接输入 | 编辑当前单元格。直接键入文字会替换原内容。 |
| Enter / Esc、Shift+Enter | 提交或取消编辑。在值中按 Shift+Enter 插入换行。 |
| Insert、Ctrl+Insert、Alt+Insert | 插入同类节点、添加子元素、添加属性。 |
| Ctrl+D / Delete | 复制或删除节点。文档保留一个根元素。 |
| Ctrl+Z / Ctrl+Shift+Z 或 Ctrl+Y | 撤销或重做。编辑框内先处理文本输入历史。 |
| Ctrl+O / Ctrl+S / Ctrl+Shift+S | 打开、保存、另存为。 |

键盘交互参考微软 XML Notepad。[XmlTreeView 源码](https://github.com/microsoft/XmlNotepad/blob/master/src/XmlNotepad/XmlTreeView.cs) · [原版键盘说明](https://microsoft.github.io/XmlNotepad/help/keyboard/)

## 保存与测试

Qt 原型读取 UTF-8 XML，含 DTD 的文档会在打开时提示错误。未改动时保存沿用原始字节，编辑后由 Qt DOM 重新序列化，属性顺序、引号、换行和空元素写法可能变化。撤销历史保留最近 32 次文档修改。保存使用临时文件替换目标，发现原文件在磁盘上已被其他程序改动时会提示另存为。

测试通过 Qt 的键盘和鼠标事件操作窗口，在临时目录中验证保存、重载与取消。还可以将以 `recipe` 为根且以 `name` 为首个显示属性的 XML 路径传给 `QT_QPA_PLATFORM=offscreen ./build/editor-test`，检查原样保存的字节以及改值后的节点、属性、CDATA 和文本。
