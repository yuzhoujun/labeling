# 独立数据标注工具 (Labeling Tool) v1.0

![版本](https://img.shields.io/badge/版本-v1.0-blue.svg) ![环境](https://img.shields.io/badge/环境-Python%203.9%20%7C%20PyQt5-brightgreen.svg)

独立数据标注工具是一款轻量级、完全本地化的计算机视觉数据标注应用程序。本项目为正式版本 `v1.0`，从 v0.1 迭代至今，集成了一套完善的照片标注、标签管理及数据导出流程。支持矩形绘制、复杂的筛选选项及多种业内主流数据集格式转换。

## ✨ 核心特性

- **多格式兼容**
  - **导入/导出** 支持无缝接入 **YOLO**、**COCO**、**Pascal VOC (XML)** 格式，灵活串联各类深度学习目标检测/分割模型的训练前道工序。
- **丰富的标注模式**
  - 原生支持 **矩形框 (BBox)** 标注。
- **现代化 UI 与交互**
  - 界面采用统一样式的暗色风格，降低视觉疲劳。
  - 支持画布元素的拖拽修改、节点调整、不同类别高亮联动。
- **高级筛选与项目管理**
  - 内置**条件筛选与分析器**（例如：按标注类型、标注数量规则来过滤数据集）。
  - 支持标签类的实时增删改查及颜色自定义。
  - 支持自动保存/读取工作区 `JSON` 工程文件，随时中断并恢复数据标注进度。
- **性能飞跃**
  - 大量数据（成千上万张图片）环境下的列表渲染优化。
  - 导出流程引入了**多线程工作流**，并配备实时进度条，导出大体量数据集时不再造成界面卡顿。

## 📦 环境依赖

若需从源码运行，必须确保您的设备上已具备以下环境：

- **Python**: `3.9` 或以上建议
- **PyQt5**
- 基础图像处理与解析库（如有报错请按需使用 pip 补齐）

## 🚀 启动指引

### 源码直接运行

您可以在激活配置好的 Python 虚拟环境 (如 `yolo-soft`) 后，直接执行以下命令：

```bash
python labeling_app_v1.0.py
```

### 独立程序打包编译

如果需要将该程序打包为独立的 `exe` 或 `app` 以在无环境的机器上运行，可以选择以下两种方案：

#### [方案一] PyInstaller（推荐作为轻量级分发）

适用于 PyInstaller 6.0+（单文件免安装版）：

- **Windows:**

  ```bash
  pyinstaller --noconsole --onefile --icon=assets/app_icon_colored.png --name="LabelingToolN_v1.0" --add-data "assets;assets" labeling_app_v1.0.py
  ```

- **Linux / Mac:**

  ```bash
  pyinstaller --noconsole --onefile --icon=assets/app_icon_colored.png --name="LabelingToolN_v1.0" --add-data "assets:assets" labeling_app_v1.0.py
  ```

#### [方案二] Nuitka 编译（源码级加密编译，安全性高）

编译后的程序运行效率高，能够抵御常规的反编译手段。

1. **准备与安装:**

   ```bash
   pip install nuitka
   ```

   > 提示：在 Windows 平台下如果首次运行，Nuitka 可能会提示下载 C++ 编译器（如 MinGW64），输入 `Yes` 等待下载即可。另外，Windows 下 `--windows-icon-from-ico` 需要使用 `.ico` 格式图标。

2. **Windows 编译指令:**

   ```bash
   nuitka --standalone --onefile --enable-plugin=pyqt5 --windows-disable-console --windows-icon-from-ico=assets/app_icon_colored.ico --output-filename=LabelingTool_v1.0.exe --include-data-dir=assets=assets labeling_app_v1.0.py
   ```

3. **Linux / Mac 编译指令:**

   ```bash
   nuitka --standalone --onefile --enable-plugin=pyqt5 --macos-create-app-bundle --macos-app-icon=assets/app_icon_colored.icns --output-filename=LabelingTool_v1.0.app --include-data-dir=assets=assets labeling_app_v1.0.py
   ```

## 🎮 使用方法

1. **导入资源:**
   启动软件后，在界面顶部菜单栏寻找“打开文件夹”/“导入”等字样将需要标注的图像目录加载进软件列表。
2. **标定类别:**
   在右侧面板配置您的分类标签 (Classes)，可动态修该标签的名称与颜色配置。
3. **开始标注:**
   在中央画布对图片目标进行标绘。标注好的对象会在右侧图层列表中显示，随时点击均可激活与二次编辑。
4. **工作区保存:**
   工程中途可通过“保存工程”按钮将当前状态封存，免惧意外闪退。
5. **多格式导出:**
   选择"自动导出"或在顶部菜单内触发"导出为(YOLO/COCO/VOC...)"，在弹出窗口内跟随配置向导导出标准的机器学习数据集。导出过程会在弹框进度条中展示。

## 👨‍💻 开发者信息

- **作者:** yuzhoujun
- **Github:** [https://github.com/yuzhoujun/labeling](https://github.com/yuzhoujun/labeling)
- **邮箱:** <zxy2445665133@outlook.com>

---
*版权所有 © 2026 yuzhoujun. 保留所有权利。*
