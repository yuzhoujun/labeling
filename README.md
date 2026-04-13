# 独立数据标注工具 (Labeling Tool) v1.0 用户手册

![版本](https://img.shields.io/badge/版本-v1.0-blue.svg) ![环境](https://img.shields.io/badge/环境-Python%203.9%20%7C%20PyQt5-brightgreen.svg)

## 📖 简介

**独立数据标注工具** 是一款基于 `Python 3.9|PyQt5` 开发的轻量级、独立的图像目标检测数据标注软件。本工具集成了完整的标注工作流，专注于矩形框（Bounding Box）打标，专门为需要快速进行目标检测数据集制作和管理的用户打造。

当前版本（v1.0）为正式发布版本，整合了前期所有的特性与修复，针对大量数据渲染进行了多线程优化，并统一了全新的深色护眼 UI 风格。

## ✨ 主要功能

- **多格式支持**：完整支持 **YOLO**、**COCO**、**VOC (XML)** 格式的导入与导出。
- **目标打框标注**：支持快速且精准的矩形包围盒（Bounding Box）绘制与调整。
- **标签管理**：系统化的标签创建、修改及管理系统。
- **自动保存**：提供标注进度的自动保存机制，防止数据意外丢失。
- **高级筛选导出**：
  - 支持复杂条件的高级筛选（例如包含、等于、时间维度等）。
  - 支持多线程批量导出筛选结果并展示进度详情，即使大量文件也不会卡顿。
  - 支持随时中止导出任务，并在导出过程中查看详细的运行日志。
- **全局撤销/重做与快捷键**：提供系统级的右键菜单与快捷指令（复制、剪切、粘贴、全选等），提升纯文本框填写的效率（画布操作撤销暂时不会做）。

## 🚀 环境依赖与运行方式

### 环境要求
- Python 3.9+ 
- PyQt5

### 运行方式

**方式一：直接运行可执行文件（推荐 Windows 用户）**
无需配置任何环境，直接双击下载的 `.exe` 应用程序运行即可：
```bash
./LabelingToolN_v1.0.exe
```

**方式二：通过源码运行**
如果需要基于源码运行或进行二次开发，请确保已安装所需依赖：
```bash
# 激活你的 Python 环境 (例如 conda activate yolov)
python labeling_app_v1.0.py
```

## 🛠️ 使用指南

### 1. 启动与初始化
打开软件后，可以通过界面按钮加载你的图片文件夹或具体图片。软件采用深色主题设计，长时间标注保护视力。

### 2. 进行标注
- 点击/拖拽鼠标在图像中的目标上绘制**矩形标注框**。
- 为画好的框分配对应的**分类标签**。
- 可以随时通过标签管理器来新增或调整你的类别信息。

### 3. 数据集筛选
点击菜单中的筛选功能，可通过各种条件（如标签名、特定时间、文本等）对当前的数据集进行可视化的高级筛选，快速定位你需要检查或导出的那部分数据。

### 4. 导出与格式转换
- 确认标注完毕或筛选完成后，点击**导出**按钮。
- 选择你需要的格式（YOLO、COCO、VOC）。
- 软件会弹出对应的进度条悬浮窗进行**多线程导出**，支持查看明细以及中途**中止**操作。

## 📦 编译与打包说明

如果你修改了源码并希望自己将其打包为独立的可执行文件，我们在脚本内置了两种推荐的打包方式：

### 方案一：PyInstaller（常规打包，文件名带 `N` 代表无加密）
*适用版本: PyInstaller 6.0+*
```powershell
# Windows
pyinstaller --noconsole --onefile --icon=assets/app_icon_colored.png --name="LabelingToolN_v1.0" --add-data "assets;assets" labeling_app_v1.0.py

# Linux/Mac
pyinstaller --noconsole --onefile --icon=assets/app_icon_colored.png --name="LabelingToolN_v1.0" --add-data "assets:assets" labeling_app_v1.0.py
```

### 方案二：Nuitka 编译（高安全性/防反编译，推荐）
由于包含了C++级别的编译，此方案生成的 exe 性能更好且更难被逆向工程。
1. 安装：`pip install nuitka`
2. 环境要求：需要 C++ 编译器（首次运行 Nuitka 会提示下载 MinGW64，选 Yes 下载即可）。
3. **注意**：Windows 环境下 Nuitka 必须使用 `.ico` 格式图标，请提前进行转换。
```powershell
# Windows
nuitka --standalone --onefile --enable-plugin=pyqt5 --windows-disable-console --windows-icon-from-ico=assets/app_icon_colored.ico --output-filename=LabelingTool_v1.0.exe --include-data-dir=assets=assets labeling_app_v1.0.py

# Linux/Mac
nuitka --standalone --onefile --enable-plugin=pyqt5 --macos-create-app-bundle --macos-app-icon=assets/app_icon_colored.icns --output-filename=LabelingTool_v1.0.app --include-data-dir=assets=assets labeling_app_v1.0.py
```

## 👨‍💻 开发者信息

- **作者**: yuzhoujun
- **GitHub**: [https://github.com/yuzhoujun/labeling](https://github.com/yuzhoujun/labeling)
- **联系邮箱**: zxy2445665133@outlook.com
