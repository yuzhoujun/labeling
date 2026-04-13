# 独立数据标注工具 (Labeling Tool) - 学习交流开源版

[![环境](https://img.shields.io/badge/环境-Python%203.9%20%7C%20PyQt5-brightgreen.svg)](environment.yml)
[![开源许可证](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

本项目是一个轻量级、完全本地化的计算机视觉数据标注应用程序，基于 Python 和 PyQt5 构建。这是一个纯开源、以学习和交流为目的的个人项目。

这里展示了如何从零开始利用 PyQt5 搭建一个具有完整生命周期管理的桌面级图像打标软件，涵盖了画布坐标系转换、多线程后台任务、自定义表格委托（Delegate）及底层文件解析等丰富的 PyQt5 实践技巧。

## ✨ 核心特性与技术看点

- **多格式解析器 (Format Parsers)**
  - 演示了如何手写解析及封装 **YOLO (.txt)**、**COCO (.json)**、**Pascal VOC (.xml)** 格式，实现多标准之间的无缝互转。
- **自定义绘图与交互 (Custom QWidget Canvas)**
  - 基于绘制事件 (`paintEvent`) 和鼠标坐标映射，实现原生级别的 **矩形框 (Bounding Box)** 标注。
  - 处理了包围盒的手柄拖拽伸缩、边界检测以及图层重叠选取逻辑。
- **现代化暗黑 UI (QSS & Styled Delegates)**
  - 完全由 QSS 驱动的暗黑风格界面，附带丰富的自定义 UI 控件（如带三角指示器的下拉框、悬浮筛选漏斗等）。
  - 利用 `QStyledItemDelegate` 与 `QTableWidget` 实现了自定义表格单元格渲染以及拖拽排序 (Drag & Drop) 数据交换。
- **核心功能栈**
  - **高级条件分析器**: 演示如何构建支持复杂逻辑表达式（包含、时间、类别匹配）的数据筛选器。
  - **多线程工作流**: 利用 `QThread` 封装大量数据的后台导出任务，通过 `pyqtSignal` 进行进度条实时通讯，避免阻塞主 UI 线程。
  - **自动序列化**: 利用 JSON 格式实现了当前工作台（类别、图片及对应坐标信息）的工程状态封存与恢复。

## 📦 环境依赖

若需从源码阅读或运行体验，您的设备上需要具备以下环境：

- **Python**: `3.9` 或以上
- **核心包**: `PyQt5`, `xml.etree.ElementTree` (标准库)

## 🚀 启动指引

激活具备上述依赖的 Python 虚拟环境后，通过以下命令直接启动应用程序主入口：

```bash
python labeling_app_v1.0.py
```

## 🛠️ 打包编译 (可选研究)

本项目还提供了如何将复杂的 PyQt5 工程打包为独立程序的示例命令，如果您对此感兴趣可以参考源码顶层的注释部分：

1. **PyInstaller**: 展现了常规的 `--add-data` 资源挂载打包方案。
2. **Nuitka**: 展现了基于 C++ 环境进行源码级加密及性能优化的独立编译方案 (支持 Windows & Linux/Mac)。

## 👨‍💻 开发者信息

本项目仅作为学习 Python GUI 编程及计算机视觉辅助工具开发的探讨交流之用。

- **作者:** yuzhoujun
- **Github:** [https://github.com/yuzhoujun/labeling](https://github.com/yuzhoujun/labeling)
- **邮箱:** <zxy2445665133@outlook.com>

---
*声明：本仓库代码属个人开源学习项目，欢迎分发、研究与修改。使用本代码造成的任何后果与作者无关。*
