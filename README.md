# BranchXML

面向 Ubuntu 的桌面 XML 阅读与编辑器。本分支提供 Python + GTK 4 编辑器，保留 Qt 6 原型供对照。GTK 的启动方式与保存行为见下方「GTK 编辑器」。

## Qt 对照原型

左栏展开节点和属性，右栏双击就地改值。属性以 `@` 开头。仅含文本或单段 CDATA 的元素直接在该行显示内容，混合内容按子节点显示。

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

## GTK 编辑器

此分支额外提供 Python 3 + GTK 4 的独立入口。使用系统 Python、PyGObject 和 GTK 4.12 或更高版本。运行以下命令打开内置示例，或在命令末尾加上自己的 XML 路径。

```sh
/usr/bin/python3 prototypes/gtk/branchxml.py
```

点击右栏单行值，或选中行后按 F2。Tab 提交并继续编辑下一个可见值，Shift+Tab 反向，容器行自动跳过。Enter 提交当前值，Esc 还原本次编辑。中文候选期间由系统输入法先处理按键。

选中左栏的节点后，可从标题栏「节点」菜单操作，也可以使用快捷键。

| 按键 | 操作 |
| --- | --- |
| Insert | 在选中节点后新增同级元素，在属性行则新增同级属性。输入名称后按 Enter 确认。 |
| Ctrl+Insert / Alt+Insert | 在选中元素内新增子元素 / 属性。 |
| Ctrl+D | 紧接原节点复制整棵子树，保留属性、文本和 CDATA。复制属性时自动取可用的新名称。 |
| Delete | 删除选中节点及其子节点。根元素保留，值输入框中的 Delete 仍用于删字。 |

复制、改值和删除各占一步撤销历史。复制元素沿用全部属性值，包括配方里的序号。普通文本紧邻普通文本时，XML 会将两段文字读成一个文本节点。

Ctrl+Z 撤销，Ctrl+Shift+Z 或 Ctrl+Y 重做。连续按 Tab 改值时，每个实际改动的字段算一步。刚跳到下一字段就按 Ctrl+Z，会撤回上一字段的修改。正在输入时，先撤销或重做输入框里的文字。保存后仍能继续撤销，打开其他文件后从空历史开始。

标题栏提供「打开」(Ctrl+O)、「保存」(Ctrl+S) 和「另存为」(Ctrl+Shift+S)。保存会一并提交当前输入框的内容。另存为后继续编辑新文件。打开其他文件或关闭窗口时，如有未保存的修改，可选择保存、放弃或取消。

GTK 版记录每个值在 XML 源文件中的位置。改值时只替换该值的字节。节点操作在对应位置插入或移除 XML 片段。独占一行的元素沿用同级缩进。其他属性的引号、实体写法、CDATA、BOM 和换行都保留。给自闭合元素填写文本时，会将该元素展开成一对标签。写入前校验 XML，通过 GIO 替换本机文件。如果磁盘内容已被其他程序修改，编辑器会提示另存为。

本机隔离 Wayland 会话中，使用 Fcitx 4 和搜狗拼音验证了连续两行拼音选词、候选期间 Enter 和 Esc、取消字段编辑，以及十个值的往返导航。两个字段共用一个原生输入框，按 Tab 时保留输入法上下文。图形会话中可运行 `/usr/bin/python3 prototypes/gtk/test_branchxml.py` 检查字段提交、取消和滚动到视口外的行。运行 `/usr/bin/python3 prototypes/gtk/test_document.py` 可检查保存前后的字节、另存为和冲突处理。

## 构建和验证

需要 C++17、CMake、Qt 6.5 或更高版本的 Widgets、Xml 和 Test 模块。已在本机 Ubuntu 26.04.1、Qt 6.10.2 编译。

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

测试通过 Qt 的键盘和鼠标事件操作窗口，在临时目录中验证保存、重载与取消。可以把其他以 `recipe` 为根且以 `name` 为首个显示属性的示例路径传给 `QT_QPA_PLATFORM=offscreen ./build/editor-test`，逐份检查未编辑副本的字节以及改一个属性后的节点、属性、CDATA 和文本。

交互参考微软的 [XmlTreeView 源码](https://github.com/microsoft/XmlNotepad/blob/master/src/XmlNotepad/XmlTreeView.cs) 和[键盘说明](https://microsoft.github.io/XmlNotepad/help/keyboard/)。本原型独立实现了上述按键。原版的节点剪贴板、节点拖放、XPath 查找和 XSD 校验尚未实现。
