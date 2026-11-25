# BranchXML

面向 Ubuntu 的桌面 XML 阅读与编辑器。当前原型使用 Qt 6。左栏展开节点和属性，右栏双击就地改值。属性以 `@` 开头。仅含文本或单段 CDATA 的元素直接在该行显示内容，混合内容按子节点显示。

在本项目目录下打开公开示例：

```sh
./build/xml-notepad examples/demo.xml
```

展开第二个 `step`，在右栏双击 `summary` 可以编辑“加入薄荷 & 柠檬”，按 Enter 提交。也可以按 Ctrl+O 打开其他文件。

| 按键 | 操作 |
| --- | --- |
| Tab / Shift+Tab | 名称 → 同行的值 → 下一可见节点的名称，或反向移动。在名称编辑框按 Tab 会继续编辑该行的值。 |
| ↑ / ↓、Home / End、Page Up / Down | 在可见节点间移动 |
| ← / → | 折叠或展开树；在值栏按 ← 返回名称，在无子节点的名称上按 → 转到值 |
| F6 / Shift+F6 | 在同一行的两栏之间切换 |
| Enter / F2、直接输入 | 编辑当前单元格；直接键入文字会替换原内容 |
| Enter / Esc、Shift+Enter | 提交 / 取消；在值中插入换行 |
| Insert、Ctrl+Insert、Alt+Insert | 插入同类节点、添加子元素、添加属性 |
| Ctrl+D / Delete | 复制节点 / 删除节点；文档保留一个根元素 |
| Ctrl+Z / Ctrl+Shift+Z 或 Ctrl+Y | 撤销 / 重做；编辑框内先处理文本输入历史 |
| Ctrl+O / Ctrl+S / Ctrl+Shift+S | 打开 / 保存 / 另存为 |

支持 UTF-8 XML，不加载 DTD。未改动时保存沿用原始字节；编辑后由 Qt DOM 重新序列化，属性顺序、引号、换行和空元素写法可能变化。撤销历史保留最近 32 次文档修改。保存使用临时文件替换目标，发现原文件在磁盘上已被其他程序改动时会提示另存为。

## 构建和验证

需要 C++17、CMake、Qt 6.5 或更高版本的 Widgets、Xml 和 Test 模块。已在本机 Ubuntu 26.04.1、Qt 6.10.2 编译。

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

测试通过 Qt 的键盘和鼠标事件操作窗口，在临时目录中验证保存、重载与取消。可以把其他以 `recipe` 为根且以 `name` 为首个显示属性的示例路径传给 `QT_QPA_PLATFORM=offscreen ./build/editor-test`，逐份检查未编辑副本的字节以及改一个属性后的节点、属性、CDATA 和文本。

交互参考微软的 [XmlTreeView 源码](https://github.com/microsoft/XmlNotepad/blob/master/src/XmlNotepad/XmlTreeView.cs) 和[键盘说明](https://microsoft.github.io/XmlNotepad/help/keyboard/)。本原型独立实现了上述按键。原版的节点剪贴板、节点拖放、XPath 查找和 XSD 校验尚未实现。
