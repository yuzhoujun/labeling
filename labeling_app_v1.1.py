"""
项目名称: 独立数据标注工具 (Labeling Tool)
版本: v1.1
开发环境: Python 3.9.25 | PyQt5

功能说明:
    独立数据标注工具正式版。集成了COCO/YOLO/VOC格式支持、矩形标注、标签管理、自动保存、高级筛选导出等功能。
    当前仅作为目标检测打框专用，后续功能待定中，不一定更新。

使用说明:
    1. 运行: python labeling_app_v1.1.py
    2. 导出: 点击导出按钮将自动弹出进度窗口。

更新日志 (v1.1):
    [功能] 初步完善撤回重做。
    [界面] 优化了撤销重做按钮的显示和交互。
    [调试] 增加操作池。

开发者信息:
    作者: yuzhoujun
    Github: https://github.com/yuzhoujun/labeling
    邮箱: zxy2445665133@outlook.com
"""

import sys
import os
import json
import random
from datetime import datetime
import xml.etree.ElementTree as ET

SHOW_ACTION_POOL_DEBUG = True

# Global App Info
APP_NAME = "LabelingTool"
APP_NAME_FULL = "独立数据标注工具 (Labeling Tool)"
APP_VERSION = "1.1"

from xml.dom import minidom
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QLineEdit, QFileDialog, 
                             QMessageBox, QSplitter, QTableWidget, QTableWidgetItem,
                             QFrame, QSizePolicy, QInputDialog, QMenu, QAction, QHeaderView,
                             QColorDialog, QDialog, QComboBox, QAbstractItemView, QCheckBox,
                             QScrollArea, QStyledItemDelegate, QStyle, QStyleOptionViewItem,
                             QProgressBar, QTextEdit, QToolButton)
from PyQt5.QtCore import Qt, QSize, QPoint, QPointF, QRectF, QRect, QEvent, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor, QPen, QBrush, QPolygonF

# ============================================
# 操作池与撤销系统 (Action Pool & Undo System)
# ============================================

class ActionLevel:
    VIEW = 0       # 视图变化：筛选、选中，一般静默
    MINOR = 1      # 轻微修改：比如移动框
    NORMAL = 2     # 普通修改：新增框、修改类别等
    MAJOR = 3      # 重大修改：删除标注框、删除类别
    CRITICAL = 4   # 极危险修改：文件切换时的状态重置等

class BaseAction:
    def __init__(self, description, level=ActionLevel.NORMAL):
        self.description = description
        self.level = level
        
    def do(self):
        """执行该动作并将其记录在状态中"""
        pass
        
    def undo(self):
        """撤销该动作"""
        pass

class ActionPool:
    def __init__(self, main_app):
        self.main_app = main_app
        self.image_stacks = {}
        self.current_context = None
        self.action_log = []
        self.max_history = 50  # 限制历史记录数量

    @property
    def undo_stack(self):
        if not self.current_context:
            return []
        return self.image_stacks.setdefault(self.current_context, {"undo": [], "redo": []})["undo"]

    @property
    def redo_stack(self):
        if not self.current_context:
            return []
        return self.image_stacks.setdefault(self.current_context, {"undo": [], "redo": []})["redo"]

    def switch_context(self, context_id):
        self.current_context = context_id
        if hasattr(self.main_app, "update_undo_redo_ui"):
            self.main_app.update_undo_redo_ui()

    def _log_action(self, action, op_type="EXECUTE"):
        log_entry = f"[{datetime.now().strftime('%H:%M:%S')}] {op_type} | Level: {action.level} | Desc: {action.description} | Context: {self.current_context}"
        self.action_log.append(log_entry)
        if len(self.action_log) > 500:
            self.action_log.pop(0)
        
    def execute(self, action: BaseAction):
        """执行一个动作，并记录到撤销栈"""
        if action.level >= ActionLevel.MAJOR:
            reply = DarkDialogHelper.ask_yes_no(
                self.main_app, "重要操作提示", 
                f"您即将执行一项重要操作:\n[{action.description}]\n\n是否继续？"
            )
            if not reply:
                return False
                
        try:
            action.do()
        except Exception as e:
            DarkDialogHelper.show_error(self.main_app, "操作执行失败", str(e))
            return False
            
        self._log_action(action, "EXECUTE")

        if action.level > ActionLevel.VIEW and self.current_context:
            undo_list = self.undo_stack
            undo_list.append(action)
            self.redo_stack.clear()
            
            if len(undo_list) > self.max_history:
                undo_list.pop(0)
                
            self.main_app.update_undo_redo_ui()
        return True

    def undo(self):
        undo_list = self.undo_stack
        if not undo_list:
            return
            
        action = undo_list[-1]
        
        if action.level >= ActionLevel.MAJOR:
            reply = DarkDialogHelper.ask_yes_no(
                self.main_app, "撤销确认", 
                f"撤销即将影响重要数据:\n[{action.description}]\n\n是否确认撤销？"
            )
            if not reply:
                return
                
        undo_list.pop()
        action.undo()
        self.redo_stack.append(action)
        self._log_action(action, "UNDO")
        self.main_app.refresh_annotation_table()
        self.main_app.canvas.update()
        self.main_app.update_undo_redo_ui()

    def redo(self):
        redo_list = self.redo_stack
        if not redo_list:
            return
            
        action = redo_list[-1]
        
        if action.level >= ActionLevel.MAJOR:
            reply = DarkDialogHelper.ask_yes_no(
                self.main_app, "重做确认", 
                f"重做即将影响重要数据:\n[{action.description}]\n\n是否确认重做？"
            )
            if not reply:
                return
                
        redo_list.pop()
        action.do()
        self.undo_stack.append(action)
        self._log_action(action, "REDO")
        self.main_app.refresh_annotation_table()
        self.main_app.canvas.update()
        self.main_app.update_undo_redo_ui()

    def clear(self):
        if self.current_context and self.current_context in self.image_stacks:
            self.image_stacks[self.current_context]["undo"].clear()
            self.image_stacks[self.current_context]["redo"].clear()
        if hasattr(self.main_app, "update_undo_redo_ui"):
            self.main_app.update_undo_redo_ui()

class AddShapeAction(BaseAction):
    def __init__(self, main_app, shape_dict):
        super().__init__("添加标注框", level=ActionLevel.NORMAL)
        self.main_app = main_app
        self.shape_dict = shape_dict
        self.added_index = -1

    def do(self):
        shapes = self.main_app.canvas.get_shapes()
        self.added_index = len(shapes)
        shapes.append(self.shape_dict)
        self.main_app.canvas.set_shapes(shapes)
        self.main_app.save_current_annotations()
        self.main_app.refresh_annotation_table()
        self.main_app.canvas.update()

    def undo(self):
        shapes = self.main_app.canvas.get_shapes()
        if 0 <= self.added_index < len(shapes):
            shapes.pop(self.added_index)
            self.main_app.canvas.set_shapes(shapes)
            self.main_app.save_current_annotations()
            self.main_app.refresh_annotation_table()
            self.main_app.canvas.update()

class DeleteShapesAction(BaseAction):
    def __init__(self, main_app, indices_to_delete):
        super().__init__("删除所选标注框", level=ActionLevel.MAJOR)
        self.main_app = main_app
        self.indices = sorted(list(indices_to_delete), reverse=True)
        self.deleted_shapes = []

        shapes = self.main_app.canvas.get_shapes()
        for i in self.indices:
            if 0 <= i < len(shapes):
                self.deleted_shapes.append((i, shapes[i]))
        # deleted_shapes is now sorted by descending index

    def do(self):
        shapes = self.main_app.canvas.get_shapes()
        for i in self.indices:
            if 0 <= i < len(shapes):
                shapes.pop(i)
        self.main_app.canvas.set_shapes(shapes)
        self.main_app.save_current_annotations()
        self.main_app.canvas.selected_indices.clear()
        self.main_app.refresh_annotation_table()
        self.main_app.canvas.update()

    def undo(self):
        shapes = self.main_app.canvas.get_shapes()
        for idx, shape in reversed(self.deleted_shapes):
            shapes.insert(idx, shape)

        self.main_app.canvas.set_shapes(shapes)
        self.main_app.save_current_annotations()
        self.main_app.refresh_annotation_table()
        self.main_app.canvas.update()

class ModifyShapeClassAction(BaseAction):
    def __init__(self, main_app, shape_index, old_class_idx, new_class_idx):
        super().__init__("修改标注类别", level=ActionLevel.NORMAL)
        self.main_app = main_app
        self.shape_index = shape_index
        self.old_class_idx = old_class_idx
        self.new_class_idx = new_class_idx

    def do(self):
        shapes = self.main_app.canvas.get_shapes()
        if 0 <= self.shape_index < len(shapes):
            shapes[self.shape_index]['class_index'] = self.new_class_idx
            self.main_app.canvas.set_shapes(shapes)
            self.main_app.save_current_annotations()
            self.main_app.refresh_annotation_table()
            self.main_app.canvas.update()

    def undo(self):
        shapes = self.main_app.canvas.get_shapes()
        if 0 <= self.shape_index < len(shapes):
            shapes[self.shape_index]['class_index'] = self.old_class_idx
            self.main_app.canvas.set_shapes(shapes)
            self.main_app.save_current_annotations()
            self.main_app.refresh_annotation_table()
            self.main_app.canvas.update()

class BulkModifyShapeRectAction(BaseAction):
    def __init__(self, main_app, changes_dict):
        super().__init__("批量修改标注框位置/大小", level=ActionLevel.MINOR)
        self.main_app = main_app
        self.changes = changes_dict

    def do(self):
        shapes = self.main_app.canvas.get_shapes()
        for idx, (old_rect, new_rect) in self.changes.items():
            if 0 <= idx < len(shapes):
                shapes[idx]['rect'] = new_rect
        self.main_app.canvas.set_shapes(shapes)
        self.main_app.save_current_annotations()
        self.main_app.canvas.update()

    def undo(self):
        shapes = self.main_app.canvas.get_shapes()
        for idx, (old_rect, new_rect) in self.changes.items():
            if 0 <= idx < len(shapes):
                shapes[idx]['rect'] = old_rect
        self.main_app.canvas.set_shapes(shapes)
        self.main_app.save_current_annotations()
        self.main_app.canvas.update()

# ============================================
# 工具函数与类
# ============================================

# Optimize: Calculate base path once
BASE_PATH = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

def resource_path(relative_path):
    return os.path.join(BASE_PATH, relative_path)

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class ComboBoxWithArrow(QComboBox):
    """
    QComboBox with a custom painted arrow to indicate state clearly.
    Replacing the default drop-down arrow style with a simple painted one usually requires QStyle,
    but we can patch it via styleSheet or painting.
    User requested: Green small triangle on right side.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Using Stylesheet for arrow is easier than paintEvent override for standard widgets
        # The down-arrow subcontrol
        self.setStyleSheet("""
            QComboBox {
                border: 1px solid #555;
                border-radius: 3px;
                padding: 1px 18px 1px 3px;
                min-width: 6em;
                background: #333;
                color: #eee;
            }
            QComboBox:hover {
                border: 1px solid #00aaff;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 0px;
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
            }
            /* Custom Green Triangle */
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #00ff00; /* Green Down Triangle */
                margin-right: 5px;
            }
            QComboBox::down-arrow:on { /* When popup is open */
               border-top: none;
               border-bottom: 5px solid #00ff00; /* Green Up Triangle */
            }
        """)

class CustomInputDialog(QDialog):
    """ Custom Input Dialog using ComboBoxWithArrow for consistent UI """
    def __init__(self, parent=None, title="", label="", items=None, current=0, editable=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(label))
        
        self.combo = ComboBoxWithArrow()
        if items:
            self.combo.addItems(items)
            if 0 <= current < len(items):
                self.combo.setCurrentIndex(current)
        self.combo.setEditable(editable)
        layout.addWidget(self.combo)
        
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        
        self.btn_ok = QPushButton("确定")
        self.btn_ok.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_ok)
        
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_box)

    def textValue(self):
        return self.combo.currentText()
        
class DarkDialogHelper:
    """ 深色主题对话框辅助类 """
    @staticmethod
    def get_text(parent, title, label, text=""):
        dialog = QInputDialog(parent)
        dialog.setOptions(QInputDialog.UseListViewForComboBoxItems)
        dialog.setWindowTitle(title)
        dialog.setLabelText(label)
        dialog.setTextValue(text)
        dialog.setOkButtonText("确定")
        dialog.setCancelButtonText("取消")
        dialog.setStyleSheet(parent.styleSheet())
        ret = dialog.exec_()
        return dialog.textValue(), ret == QDialog.Accepted

    @staticmethod
    def get_item(parent, title, label, items, current=0, editable=False):
        # Use custom dialog for consistent dropdown style (Green Arrow)
        dialog = CustomInputDialog(parent, title, label, items, current, editable)
        ret = dialog.exec_()
        return dialog.textValue(), ret == QDialog.Accepted

    @staticmethod
    def get_color(parent, initial=QColor(255, 255, 255), title="选择颜色"):
        dialog = QColorDialog(initial, parent)
        dialog.setWindowTitle(title)
        dialog.setOption(QColorDialog.DontUseNativeDialog, True) 
        dialog.setStyleSheet(parent.styleSheet() + "QWidget{background-color: #2b2b2b; color: #e0e0e0;}")
        if dialog.exec_() == QDialog.Accepted:
            return dialog.selectedColor()
        return QColor()

    @staticmethod
    def get_int(parent, title, label, value=0, min_val=0, max_val=9999):
        dialog = QInputDialog(parent)
        dialog.setWindowTitle(title)
        dialog.setLabelText(label)
        dialog.setIntValue(value)
        dialog.setIntRange(min_val, max_val)
        dialog.setOkButtonText("确定")
        dialog.setCancelButtonText("取消")
        dialog.setStyleSheet(parent.styleSheet())
        ret = dialog.exec_()
        return dialog.intValue(), ret == QDialog.Accepted

    @staticmethod
    def show_info(parent, title, text):
        msg = QMessageBox(parent)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QMessageBox.Information)
        msg.addButton("确定", QMessageBox.AcceptRole)
        msg.setStyleSheet(parent.styleSheet())
        msg.exec_()

    @staticmethod
    def show_warning(parent, title, text):
        msg = QMessageBox(parent)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QMessageBox.Warning)
        msg.addButton("确定", QMessageBox.AcceptRole)
        msg.setStyleSheet(parent.styleSheet())
        msg.exec_()

    @staticmethod
    def show_critical(parent, title, text):
        msg = QMessageBox(parent)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QMessageBox.Critical)
        msg.addButton("确定", QMessageBox.AcceptRole)
        msg.setStyleSheet(parent.styleSheet())
        msg.exec_()

    @staticmethod
    def ask_yes_no(parent, title, text):
        msg = QMessageBox(parent)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QMessageBox.Question)
        yes_btn = msg.addButton("是", QMessageBox.YesRole)
        msg.addButton("否", QMessageBox.NoRole)
        msg.setStyleSheet(parent.styleSheet())
        msg.exec_()
        return msg.clickedButton() == yes_btn

    @staticmethod
    def ask_yes_no_cancel(parent, title, text):
        msg = QMessageBox(parent)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QMessageBox.Question)
        yes_btn = msg.addButton("是", QMessageBox.YesRole)
        no_btn = msg.addButton("否", QMessageBox.NoRole)
        msg.addButton("取消", QMessageBox.RejectRole)
        msg.setStyleSheet(parent.styleSheet())
        msg.exec_()
        
        if msg.clickedButton() == yes_btn: return QMessageBox.Yes
        if msg.clickedButton() == no_btn: return QMessageBox.No
        return QMessageBox.Cancel

class ChineseLineEdit(QLineEdit):
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        
        # 撤销
        a_undo = menu.addAction("撤销")
        if a_undo:
            a_undo.setShortcut("Ctrl+Z")
            a_undo.triggered.connect(self.undo)
            a_undo.setEnabled(self.isUndoAvailable())
        
        # 重做
        a_redo = menu.addAction("重做")
        if a_redo:
            a_redo.setShortcut("Ctrl+Y")
            a_redo.triggered.connect(self.redo)
            a_redo.setEnabled(self.isRedoAvailable())
        
        menu.addSeparator()
        
        # 剪切
        a_cut = menu.addAction("剪切")
        if a_cut:
            a_cut.setShortcut("Ctrl+X")
            a_cut.triggered.connect(self.cut)
            a_cut.setEnabled(self.hasSelectedText())
        
        # 复制
        a_copy = menu.addAction("复制")
        if a_copy:
            a_copy.setShortcut("Ctrl+C")
            a_copy.triggered.connect(self.copy)
            a_copy.setEnabled(self.hasSelectedText())
        
        # 粘贴
        a_paste = menu.addAction("粘贴")
        if a_paste:
            a_paste.setShortcut("Ctrl+V")
            a_paste.triggered.connect(self.paste)
            clipboard = QApplication.clipboard()
            a_paste.setEnabled(bool(clipboard.text() if clipboard else False))

        # 删除
        a_del = menu.addAction("删除")
        if a_del:
            a_del.triggered.connect(self.backspace) # backspace 删除选中文本
            a_del.setEnabled(self.hasSelectedText())
        
        menu.addSeparator()
        
        # 全选
        a_all = menu.addAction("全选")
        if a_all:
            a_all.setShortcut("Ctrl+A")
            a_all.triggered.connect(self.selectAll)
        
        menu.exec_(event.globalPos())



# ============================================
# 导出工具类
# ============================================

class ExportWorker(QThread):
    progress = pyqtSignal(int)
    log_msg = pyqtSignal(str, str) # level, msg
    finished_sig = pyqtSignal(bool, str) # success, result_msg
    
    def __init__(self, files, fmt, out_dir, func_load, func_save):
        super().__init__()
        self.files = files
        self.fmt = fmt
        self.out_dir = out_dir
        self.func_load = func_load
        self.func_save = func_save
        self._is_aborted = False
        
    def abort(self):
        self._is_aborted = True
        
    def run(self):
        total = len(self.files)
        success_count = 0
        self.log_msg.emit("INFO", f"开始导出 {total} 个文件...")
        
        for i, f in enumerate(self.files):
            if self._is_aborted:
                self.log_msg.emit("WARNING", "导出任务已被用户中止。")
                self.finished_sig.emit(False, "导出已中止")
                return
                
            try:
                # Load
                shapes = self.func_load(f, self.fmt)
                
                # Save
                self.func_save(shapes, f, self.fmt, self.out_dir)
                
                success_count += 1
                self.log_msg.emit("INFO", f"成功: {f}")
            except Exception as e:
                import traceback
                self.log_msg.emit("ERROR", f"失败 {f}: {str(e)}")
            
            self.progress.emit(i + 1)
            
        self.finished_sig.emit(True, f"导出完成。成功: {success_count}/{total}。路径: {self.out_dir}")

class ExportProgressDialog(QDialog):
    def __init__(self, parent, worker):
        super().__init__(parent)
        self.setWindowTitle("导出进度")
        self.setMinimumWidth(600)
        # self.setFixedSize(600, 450) # Removed fixed size to allow resizing
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint | Qt.WindowCloseButtonHint)
        self.worker = worker
        
        layout = QVBoxLayout(self)
        
        # Status
        self.status_label = QLabel("正在初始化...")
        self.status_label.setWordWrap(True) # Allow text wrapping
        layout.addWidget(self.status_label)
        
        # Progress
        self.pbar = QProgressBar()
        self.pbar.setRange(0, len(worker.files))
        self.pbar.setValue(0)
        layout.addWidget(self.pbar)
        
        # Detail Expander
        self.detail_chk = QCheckBox("显示详细信息")
        self.detail_chk.setChecked(True) # Default checked
        self.detail_chk.stateChanged.connect(self.toggle_details)
        layout.addWidget(self.detail_chk)
        
        # Log Area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setVisible(True) # Default visible
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #ccc; font-family: Consolas; font-size: 12px;")
        layout.addWidget(self.log_text)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.abort_btn = QPushButton("中止")
        self.abort_btn.clicked.connect(self.on_abort)
        self.abort_btn.setStyleSheet("background-color: #c0392b; color: white;")
        btn_layout.addWidget(self.abort_btn)
        
        self.ok_btn = QPushButton("确认")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setEnabled(False) # Disabled until finished
        btn_layout.addWidget(self.ok_btn)
        
        layout.addLayout(btn_layout)
        
        # Connect Worker
        worker.progress.connect(self.update_progress)
        worker.log_msg.connect(self.append_log)
        worker.finished_sig.connect(self.on_finished)
        worker.start()
        
    def toggle_details(self, state):
        visible = (state == Qt.Checked)
        self.log_text.setVisible(visible)
        
        # v0.5.2: Use resize + minimumHeight hint instead of behavior-dependent adjustSize for stability
        if visible:
            self.resize(self.width(), 450)
        else:
            self.resize(self.width(), 150) # Compact height
        
    def update_progress(self, val):
        self.pbar.setValue(val)
        self.status_label.setText(f"正在导出... ({val}/{self.pbar.maximum()})")
        
    def append_log(self, level, msg):
        color = "#cccccc"
        if level == "INFO": color = "#55aa55"
        elif level == "WARNING": color = "#ffaa00"
        elif level == "ERROR": color = "#ff5555"
        
        html = f'<div style="color:{color}"><b>[{level}]</b> {msg}</div>'
        self.log_text.append(html)
        
    def on_finished(self, success, result_msg):
        self.status_label.setText(result_msg)
        self.ok_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)
        self.pbar.setValue(self.pbar.maximum())
        if success:
             mb = QMessageBox(self)
             mb.setWindowTitle("导出完成")
             mb.setText(result_msg)
             mb.exec_()

    def on_abort(self):
        if QMessageBox.question(self, "确认中止", "确定要中止导出任务吗？", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.worker.abort()
            self.status_label.setText("正在中止...")
            self.abort_btn.setEnabled(False)
            
    def closeEvent(self, event):
        if self.worker.isRunning():
             if QMessageBox.question(self, "确认退出", "导出正在进行中，关闭窗口将中止任务。确定退出吗？", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                 self.worker.abort()
                 self.worker.wait()
                 event.accept()
             else:
                 event.ignore()
        else:
            event.accept()

# ============================================
# 筛选逻辑相关
# ============================================

class FilterCondition:
    TYPE_TEXT = "text"
    TYPE_NUMBER = "number"
    TYPE_DATETIME = "datetime"
    
    OP_EQ = "等于"
    OP_CONTAINS = "包含"
    OP_NEQ = "不等于"
    OP_NOT_CONTAINS = "不包含"
    OP_GT = "大于"
    OP_LT = "小于"
    OP_GTE = "大于等于"
    OP_LTE = "小于等于"
    
    # 逻辑关系
    LOGIC_AND = "与"
    LOGIC_OR = "或"

    # 日期维度
    DT_YEAR = "年"
    DT_MONTH = "月"
    DT_DAY = "日"
    DT_HOUR = "时"
    DT_MINUTE = "分"
    DT_SECOND = "秒"
    
    def __init__(self, col_idx, col_type, operator, value, dt_dim=None, logic="与"):
        self.col_idx = col_idx
        self.col_type = col_type
        self.operator = operator
        self.value = value
        self.dt_dim = dt_dim # 仅用于 DateTime
        self.logic = logic # 与上一条的关系


class AdvancedFilterDialog(QDialog):
    def __init__(self, parent, columns, current_filters=None):
        super().__init__(parent)
        self.setWindowTitle("高级筛选设置")
        self.setMinimumWidth(800)
        self.setMinimumHeight(400)
        self.columns = columns # list of (name, type)
        self.filters = []
        self.rows = []
        
        layout = QVBoxLayout(self)
        
        # Scroll Area for rows
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.form_layout = QVBoxLayout(self.scroll_content)
        self.form_layout.setContentsMargins(10, 10, 10, 10)
        self.form_layout.setSpacing(10)
        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll)
        
        # Red Add Button Widget (inside scroll area, at bottom)
        self.add_btn_widget = QWidget()
        add_btn_layout = QHBoxLayout(self.add_btn_widget)
        # Add bottom margin to prevent visual truncation
        add_btn_layout.setContentsMargins(0, 0, 0, 5)
        
        self.add_btn = QPushButton()
        self.add_btn.setFixedSize(32, 32)
        self.add_btn.setCursor(Qt.PointingHandCursor)
        
        icon_path_add = resource_path("assets/icon_add.png")
        if os.path.exists(icon_path_add):
            self.add_btn.setIcon(QIcon(icon_path_add))
            self.add_btn.setIconSize(QSize(20, 20))
            # Green rounded background
            self.add_btn.setStyleSheet("""
                QPushButton {
                    background-color: #43a047; 
                    border-radius: 6px; 
                    border: none;
                    padding: 0px;
                    min-width: 32px;
                    min-height: 32px;
                }
                QPushButton:hover {
                    background-color: #66bb6a;
                }
                QPushButton:pressed {
                    background-color: #2e7d32;
                }
            """)
        else:
             self.add_btn.setText("+")
             self.add_btn.setStyleSheet("""
                QPushButton {
                    background-color: #43a047; 
                    color: white; 
                    font-size: 20px; 
                    font-weight: bold;
                    border-radius: 16px;
                    border: none;
                }
             """)

        self.add_btn.clicked.connect(lambda: self.add_filter_row())
        
        # Place Add Button to the left (below previous logic)
        # Add some spacing to align with logic combo column if needed, or just left align
        # The logic combo is 45px wide + margins. Let's precise positioning later
        add_btn_layout.addWidget(self.add_btn)
        add_btn_layout.addStretch()
        
        self.form_layout.addWidget(self.add_btn_widget)
        self.form_layout.addStretch() # Push everything up
        
        # Bottom Actions
        action_layout = QHBoxLayout()
        clear_btn = QPushButton("清除所有")
        clear_btn.clicked.connect(self.clear_all_rows)
        
        action_layout.addWidget(clear_btn)
        action_layout.addStretch()
        
        confirm_btn = QPushButton("确认筛选")
        confirm_btn.clicked.connect(self.accept)
        confirm_btn.setStyleSheet("background-color: #007acc; color: white; padding: 6px 20px;")
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        
        action_layout.addWidget(confirm_btn)
        action_layout.addWidget(cancel_btn)
        layout.addLayout(action_layout)
        
        # Initialize
        if current_filters:
            for f in current_filters:
                self.add_filter_row(initial_data=f)
        
        if not self.rows:
            self.add_filter_row() # Add one empty row by default

    def add_filter_row(self, initial_data=None):
        row_widget = QFrame()
        row_widget.setFrameShape(QFrame.StyledPanel)
        row_widget.setStyleSheet("QFrame { background-color: #333; border-radius: 4px; border: 1px solid #444; }")
        
        h_layout = QHBoxLayout(row_widget)
        h_layout.setContentsMargins(8, 8, 8, 8)
        
        # Logic Selector (AND/OR)
        logic_combo = ComboBoxWithArrow()
        logic_combo.setFixedWidth(40) # Even smaller
        # Override min-width from class style
        logic_combo.setStyleSheet(logic_combo.styleSheet() + """
            QComboBox { min-width: 0px; padding: 1px 0px 1px 4px; } 
            QComboBox::drop-down { width: 14px; }
        """)
        logic_combo.addItems([FilterCondition.LOGIC_AND, FilterCondition.LOGIC_OR])
        
        # Enable retain size when hidden for perfect alignment
        sp = logic_combo.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        logic_combo.setSizePolicy(sp)

        # Removed spacer approach to fix alignment issues
        # first_row_spacer = QWidget() ... 

        is_first_row = len(self.rows) == 0
        
        if is_first_row:
             logic_combo.setVisible(False)
        else:
             logic_combo.setVisible(True)
             if initial_data and hasattr(initial_data, 'logic'):
                 logic_idx = logic_combo.findText(initial_data.logic)
                 if logic_idx != -1: logic_combo.setCurrentIndex(logic_idx)

        # Add logic_combo to layout
        h_layout.addWidget(logic_combo)
        
        # Column Select
        col_combo = ComboBoxWithArrow()
        for name, _ in self.columns:
            col_combo.addItem(name)
        h_layout.addWidget(col_combo, 1)

        # DateTime Dimension Select (Hidden by default)
        dt_dim_combo = ComboBoxWithArrow()
        dt_dim_combo.addItems(["整串匹配", FilterCondition.DT_YEAR, FilterCondition.DT_MONTH, FilterCondition.DT_DAY, 
                               FilterCondition.DT_HOUR, FilterCondition.DT_MINUTE, FilterCondition.DT_SECOND])
        dt_dim_combo.setVisible(False)
        h_layout.addWidget(dt_dim_combo)

        # Operator Select
        op_combo = ComboBoxWithArrow()
        # Default operators (Text)
        op_combo.addItems([FilterCondition.OP_EQ, FilterCondition.OP_CONTAINS, FilterCondition.OP_NEQ, FilterCondition.OP_NOT_CONTAINS])
        h_layout.addWidget(op_combo, 1)
        
        # Value Input
        val_input = ChineseLineEdit()
        val_input.setPlaceholderText("输入筛选值...")
        h_layout.addWidget(val_input, 2)
        
        # Remove Button
        rm_btn = QPushButton()
        rm_btn.setFixedSize(28, 28)
        icon_path = resource_path("assets/icon_trash.png")
        if os.path.exists(icon_path):
            rm_btn.setIcon(QIcon(icon_path))
            rm_btn.setIconSize(QSize(18, 18))
        else:
            rm_btn.setText("X")
            
        rm_btn.setObjectName("removeButton")
        rm_btn.setCursor(Qt.PointingHandCursor) # type: ignore
        rm_btn.clicked.connect(lambda: self.remove_row(row_widget))
        h_layout.addWidget(rm_btn)
        
        # Logic to update operators based on column
        def on_col_changed(idx):
            name, ctype = self.columns[idx]
            dt_dim_combo.setVisible(False)
            op_combo.clear()
            val_input.clear()
            
            if ctype == FilterCondition.TYPE_NUMBER:
                op_combo.addItems([FilterCondition.OP_EQ, FilterCondition.OP_CONTAINS, FilterCondition.OP_NEQ, FilterCondition.OP_NOT_CONTAINS, 
                                   FilterCondition.OP_GT, FilterCondition.OP_LT, FilterCondition.OP_GTE, FilterCondition.OP_LTE])
                val_input.setPlaceholderText("输入数值...")
            elif ctype == FilterCondition.TYPE_DATETIME:
                dt_dim_combo.setVisible(True)
                op_combo.addItems([FilterCondition.OP_EQ, FilterCondition.OP_CONTAINS, FilterCondition.OP_NEQ, FilterCondition.OP_NOT_CONTAINS, 
                                   FilterCondition.OP_GT, FilterCondition.OP_LT, FilterCondition.OP_GTE, FilterCondition.OP_LTE])
                val_input.setPlaceholderText("输入时间 (如 2023)")
            else: # Text
                op_combo.addItems([FilterCondition.OP_EQ, FilterCondition.OP_CONTAINS, FilterCondition.OP_NEQ, FilterCondition.OP_NOT_CONTAINS])
                val_input.setPlaceholderText("输入文本...")
                
        col_combo.currentIndexChanged.connect(on_col_changed)
        
        # Initial Set
        if initial_data:
            col_idx = initial_data.col_idx
            # Find combo index
            if 0 <= col_idx < col_combo.count():
                col_combo.setCurrentIndex(col_idx)
                on_col_changed(col_idx) # Force update ops
                
                # Set dimension if DT
                if initial_data.col_type == FilterCondition.TYPE_DATETIME and initial_data.dt_dim:
                    dt_idx = dt_dim_combo.findText(initial_data.dt_dim)
                    if dt_idx != -1: dt_dim_combo.setCurrentIndex(dt_idx)
                
                # Set Op
                op_idx = op_combo.findText(initial_data.operator)
                if op_idx != -1: op_combo.setCurrentIndex(op_idx)
                
                # Set Val
                val_input.setText(str(initial_data.value))

        # Add to layout: Insert before the add_btn_widget (which is at count-2)
        # form_layout items: [row1, row2, ..., add_btn_widget, stretch]
        insert_idx = self.form_layout.count() - 2
        if insert_idx < 0: insert_idx = 0
        self.form_layout.insertWidget(insert_idx, row_widget)
        
        self.rows.append({
            "widget": row_widget,
            "logic_combo": logic_combo,
            "col_combo": col_combo,
            "dt_dim_combo": dt_dim_combo,
            "op_combo": op_combo,
            "val_input": val_input
        })
        
        # Trigger default logic for new empty row
        if not initial_data:
             on_col_changed(col_combo.currentIndex())

    def remove_row(self, widget):
        for i, r in enumerate(self.rows):
            if r["widget"] == widget:
                widget.deleteLater()
                self.rows.pop(i)
                # If removed first row, update next row to be first (no logic combo)
                if i == 0 and self.rows:
                   # New first row: Hide Logic Combo (but retain size)
                   self.rows[0]["logic_combo"].hide()
                break

    def clear_all_rows(self):
        for r in self.rows:
            r["widget"].deleteLater()
        self.rows = []

    def get_filters(self):
        res = []
        for i, r in enumerate(self.rows):
            col_idx = r["col_combo"].currentIndex()
            if col_idx == -1: continue
            
            col_name, col_type = self.columns[col_idx]
            operator = r["op_combo"].currentText()
            value = r["val_input"].text().strip()
            
            logic = FilterCondition.LOGIC_AND
            if i > 0:
                logic = r["logic_combo"].currentText()
            
            if not value and operator not in [FilterCondition.OP_EQ, FilterCondition.OP_CONTAINS]: 
                 pass
            
            # Special Handling for DateTime Dimensions
            dt_dim = None
            if col_type == FilterCondition.TYPE_DATETIME:
                 dt_text = r["dt_dim_combo"].currentText()
                 if dt_text != "整串匹配":
                     dt_dim = dt_text
            
            res.append(FilterCondition(col_idx, col_type, operator, value, dt_dim, logic))
        return res

# ============================================
# Modified CustomHeader
# ============================================

class CustomHeader(QHeaderView):
    """ 自定义表头，支持 排序图标 + 筛选漏斗 """
    def __init__(self, orientation=Qt.Horizontal, parent=None): # type: ignore
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        # 跟踪哪些列有筛选
        self.active_filters = set() # Store logical indices of columns with active filters

    def set_filter_state(self, logicalIndex, is_active):
        if is_active:
            self.active_filters.add(logicalIndex)
        else:
            if logicalIndex in self.active_filters:
                self.active_filters.remove(logicalIndex)
        vp = self.viewport()
        if vp: vp.update()

    def paintSection(self, painter, rect, logicalIndex):
        if not painter: return
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()

        # 常量定义
        icon_size = 8
        margin = 5
        
        # 右侧区域 rect
        right_rect_w = icon_size + margin * 2
        # clear_rect: 盖住原本可能绘制在此处的文字末尾
        clear_rect = QRectF(rect.right() - right_rect_w, rect.top(), right_rect_w, rect.height())
        
        # Draw Background for icons area
        # backgroundRole usually works, but we hardcode matching theme header color to be safe
        bg_color = QColor(51, 51, 51) 
        painter.save()
        painter.setPen(Qt.NoPen) # type: ignore
        painter.setBrush(bg_color)
        painter.drawRect(clear_rect)
        painter.restore()
        
        cx = rect.right() - margin - icon_size/2
        
        # 1. 绘制排序图标 (三角形) - 位置：垂直居中偏下
        if self.isSortIndicatorShown() and self.sortIndicatorSection() == logicalIndex:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            
            # 下移一些: cy_sort
            cy_sort = rect.center().y() + 7
            
            painter.setBrush(QColor(0, 120, 215)) # 蓝色
            painter.setPen(Qt.NoPen) # type: ignore
            
            path = QPolygonF()
            if self.sortIndicatorOrder() == Qt.AscendingOrder: # type: ignore
                # 上三角形
                p1 = QPointF(cx, cy_sort - icon_size/2)
                p2 = QPointF(cx - icon_size/2, cy_sort + icon_size/2)
                p3 = QPointF(cx + icon_size/2, cy_sort + icon_size/2)
                path.append(p1); path.append(p2); path.append(p3)
            else:
                # 下三角形
                p1 = QPointF(cx - icon_size/2, cy_sort - icon_size/2)
                p2 = QPointF(cx + icon_size/2, cy_sort - icon_size/2)
                p3 = QPointF(cx, cy_sort + icon_size/2)
                path.append(p1); path.append(p2); path.append(p3)
                
            painter.drawPolygon(path)
            painter.restore()

        # 2. 绘制筛选漏斗 - 位置：垂直居中偏上
        # 始终为位置预留，如果有 active filter 则高亮
        has_filter = (logicalIndex in self.active_filters)
        
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 颜色: 如果激活则 橙色/亮色，否则 灰色
        filter_color = QColor(255, 140, 0) if has_filter else QColor(100, 100, 100)
        painter.setPen(QPen(filter_color, 1.5))
        painter.setBrush(Qt.NoBrush) # type: ignore
        
        cy_filter = rect.center().y() - 7
        sz = 4 # half width
        
        # Funnel shape
        # Top line
        painter.drawLine(QPointF(cx - sz, cy_filter - sz), QPointF(cx + sz, cy_filter - sz))
        # V shape down
        p1 = QPointF(cx - sz, cy_filter - sz)
        p2 = QPointF(cx + sz, cy_filter - sz)
        p3 = QPointF(cx, cy_filter + 2)
        # Tube down
        p4 = QPointF(cx, cy_filter + 5)
        
        painter.drawLine(p1, p3)
        painter.drawLine(p2, p3)
        painter.drawLine(p3, p4)
        
        painter.restore()

# ============================================
# 自定义表格控件 (支持拖拽排序)
# ============================================

class NoSelectionColorDelegate(QStyledItemDelegate):
    """
    Delegate that renders the item background with its specific Color (from UserRole+1),
    ignoring selection state for background, but drawing text normally.
    """
    def paint(self, painter, option, index):
        # 1. Draw Background (Using stored color, ignoring selection)
        color = index.data(Qt.UserRole + 1) # Get QColor stored in model
        if isinstance(color, QColor):
            painter.save()
            painter.fillRect(option.rect, color)
            painter.restore()
        
        # 2. Draw Text (Standard)
        # We need to construct a new option with 'Selected' state removed 
        # so standard paint doesn't draw the blue selection background over our rect
        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.State_Selected
        # Ensure text is center aligned as set in item
        super().paint(painter, opt, index)

class DraggableTableWidget(QTableWidget):
    """ 支持拖拽行进行排序或交换的表格 """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalHeader(CustomHeader(Qt.Horizontal, self)) # type: ignore
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        vp = self.viewport()
        if vp is not None: vp.setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        
        # Apply custom delegate to column 0
        self.setItemDelegateForColumn(0, NoSelectionColorDelegate(self))

        self.drag_start_row = -1
        self.main_app = None 

        # Filter storage
        self.current_filter_list = [] # List of FilterCondition
        self.col_def = [] # [(name, type), ...]


    def set_main_app(self, app):
        self.main_app = app

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        # v0.5.2: Click whitespace to deselect and reset current class
        item = self.itemAt(event.pos())
        if not item:
            self.clearSelection()
            if self.main_app and hasattr(self.main_app, 'current_class_index'):
                self.main_app.current_class_index = -1

    def startDrag(self, supportedActions):
        self.drag_start_row = self.currentRow()
        super().startDrag(supportedActions)

    def dropEvent(self, event):
        if not event or not self.main_app: return
        
        # 1. 权限检查：排序和筛选
        header = self.horizontalHeader()
        is_filtered = len(getattr(self, 'active_filters', [])) > 0
        sort_col = header.sortIndicatorSection() if header else -1
        sort_order = header.sortIndicatorOrder() if header else Qt.AscendingOrder
        
        if is_filtered:
             DarkDialogHelper.show_warning(self, "操作限制", "筛选状态下禁止手动拖拽排序。\n请先清除筛选条件。")
             event.ignore()
             return

        # 必须按ID列排序才能拖拽
        if sort_col != 0:
             DarkDialogHelper.show_warning(self, "操作限制", "请先按类别序号（第一列）排序后再进行拖拽操作。")
             event.ignore()
             return

        # 获取源数据
        source_row = self.drag_start_row
        if source_row == -1: 
            event.ignore()
            return
            
        src_item = self.item(source_row, 0)
        if not src_item: return
        src_id = int(src_item.data(Qt.UserRole))

        # 获取 drop 位置
        target_index = self.indexAt(event.pos())
        target_row = target_index.row()
        drop_pos = self.dropIndicatorPosition()
        
        # 处理空白区域Drop
        if target_row == -1:
            if self.rowCount() > 0:
                target_row = self.rowCount() - 1 
            else:
                target_row = 0

        # --- 交换逻辑 (OnItem) ---
        if drop_pos == QAbstractItemView.OnItem:
             target_item = self.item(target_row, 0)
             if target_item:
                 tgt_id = int(target_item.data(Qt.UserRole))
                 if DarkDialogHelper.ask_yes_no(self, "交换类别序号", f"确定交换 类别序号 {src_id} 和 {tgt_id} 吗？\n这将影响所有相关联的标注。"):
                     self.main_app.swap_class_ids(src_id, tgt_id)
                     event.accept()
             return

        # --- 移动/插入逻辑 ---
        # 1. 计算视觉插入位置 (Before Row Index)
        visual_insert_pos = target_row
        if drop_pos == QAbstractItemView.BelowItem:
            visual_insert_pos += 1
        elif drop_pos == QAbstractItemView.OnViewport:
            visual_insert_pos = self.rowCount()
            
        # 2. 获取上下文 ID (上下邻居)
        id_above_v = -1
        id_below_v = -1
        
        # 上邻：视觉位置 - 1 的行
        if visual_insert_pos > 0 and visual_insert_pos <= self.rowCount():
            item_prev = self.item(visual_insert_pos - 1, 0)
            if item_prev: id_above_v = int(item_prev.data(Qt.UserRole))

        # 下邻：视觉位置 的行
        if visual_insert_pos < self.rowCount():
             item_next = self.item(visual_insert_pos, 0)
             if item_next: id_below_v = int(item_next.data(Qt.UserRole))

        # 3. 构造提示信息
        msg = f"确定移动类别 ID {src_id} 到新位置吗？\n\n"
        msg += f"上邻类别ID: {id_above_v if id_above_v != -1 else '(无/顶端)'}\n"
        msg += f"下邻类别ID: {id_below_v if id_below_v != -1 else '(无/底端)'}"
        
        if not DarkDialogHelper.ask_yes_no(self, "移动确认", msg):
            event.ignore()
            return
            
        # 4. 计算逻辑插入位置 (Logical Index)
        # 如果是升序：Visual Index == Logical Index
        # 如果是降序：List [0, 1, 2]. Visual [2, 1, 0].
        #   Insert Before Visual 0 (Value 2) -> Insert Before Logical 2 -> Logical Index 2?
        #   Insert Before Visual 2 (Value 0) -> Insert Before Logical 0 -> Logical Index 0?
        #   Inverse Relationship: logical_idx = visual_idx ? 
        #   No. Visual Row k corresponds to Logical Row (N-1-k).
        #   We want to insert BEFORE Visual Row k.
        #   Means in visual list: [..., k-1, NEW, k, ...]
        #   In logical list (reversed): [..., k, NEW, k-1, ...] (Order reversed?)
        #   Logic: 
        #   Asc:  0, 1, 2. Insert at 1 -> 0, NEW, 1, 2. (Visual 0, NEW, 1, 2)
        #   Desc: 2, 1, 0. Insert at 1 (Before 1). -> 2, NEW, 1, 0.
        #   Logical Result: 0, 1, NEW, 2.
        #   Wait, if Visual 2, NEW, 1, 0. The list is [2, NEW, 1, 0] ? 
        #   So Logical is [0, 1, NEW, 2].
        #   Original Visual Index of '1' was 1. (Row 1).
        #   Original Logical Index of '1' was 1. (Length 3. 3-1-1 = 1).
        #   So target logical is... N - visual_pos?
        #   Let's verify: Length 3.
        #   Insert at Visual 0 (Top). Before '2' (Logical 2). 
        #   New List should be [NEW, 2, 1, 0] (Visual) -> [0, 1, 2, NEW] (Logical).
        #   Visual Pos 0 -> Logical Pos 3 (End). (Length 3).
        #   Insert at Visual 3 (Bottom). After '0' (Logical 0).
        #   New List [2, 1, 0, NEW] (Visual) -> [NEW, 0, 1, 2] (Logical).
        #   Visual Pos 3 -> Logical Pos 0.
        #   Formula: Logical = N - Visual.
        
        count = self.rowCount()
        logical_to_idx = visual_insert_pos
        
        if sort_order == Qt.DescendingOrder:
            logical_to_idx = count - visual_insert_pos
        
        # 5. 执行移动
        self.main_app.move_class_id(src_id, logical_to_idx)
        event.accept()

# ============================================
# 标注画布控件
# ============================================

class AnnotationCanvas(QWidget):
    # 状态枚举
    STATE_IDLE = 0
    STATE_DRAWING = 1
    STATE_MOVING = 2
    STATE_RESIZING = 3
    STATE_PANNING = 4
    STATE_SELECT_BOX = 5 # 框选模式

    # 手柄常量
    HANDLE_SIZE = 10
    HANDLE_TOP_LEFT = 1
    HANDLE_TOP_RIGHT = 2
    HANDLE_BOTTOM_LEFT = 3
    HANDLE_BOTTOM_RIGHT = 4
    HANDLE_TOP = 5
    HANDLE_BOTTOM = 6
    HANDLE_LEFT = 7
    HANDLE_RIGHT = 8

    def __init__(self, parent):
        super().__init__(parent)
        self.main_tab: 'AnnotationApp' = parent # type: ignore
        self._pixmap = None
        self._shapes = []
        self._current_rect = None
        self._selection_rect = None # 框选矩形
        self._start_pos = None
        self._scale = 1.0
        self._pan_x = 0
        self._pan_y = 0
        self._state = self.STATE_IDLE
        self._last_mouse_pos = None
        
        self.selected_indices = set() # 多选索引集合
        
        self._active_handle = None
        self._drag_start_rects = {} # 多选拖拽初始状态 {index: rect}
        self._pan_start_pos = None # 用于区分右键点击和拖拽
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus) # type: ignore

    @property
    def selected_shape_index(self):
        """兼容旧代码属性，返回最后选中的一个索引，如果没有则返回-1"""
        if not self.selected_indices:
            return -1
        return sorted(list(self.selected_indices))[-1]

    @selected_shape_index.setter
    def selected_shape_index(self, value):
        """兼容旧代码属性设置"""
        self.selected_indices.clear()
        if value != -1:
            self.selected_indices.add(value)

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        self._shapes = []
        self._current_rect = None
        self._selection_rect = None
        self._scale = 1.0
        self._pan_x = 0
        self._pan_y = 0
        self.selected_indices.clear()
        self.update()

    def set_shapes(self, shapes):
        self._shapes = shapes
        self.update()

    def get_shapes(self):
        return self._shapes

    def get_img_dims(self):
        if not self._pixmap: return 0, 0
        return int(self._pixmap.width() * self._scale), int(self._pixmap.height() * self._scale)

    def map_to_screen(self, rect_norm):
        img_w, img_h = self.get_img_dims()
        if img_w == 0 or not self._pixmap: return QRectF()
        
        win_w, win_h = self.width(), self.height()
        base_scale = min(win_w / self._pixmap.width(), win_h / self._pixmap.height()) if self._pixmap.width() > 0 else 1.0
        final_scale = base_scale * self._scale
        
        disp_w = int(self._pixmap.width() * final_scale)
        disp_h = int(self._pixmap.height() * final_scale)
        
        off_x = (win_w - disp_w) // 2 + self._pan_x
        off_y = (win_h - disp_h) // 2 + self._pan_y
        
        x = rect_norm.x() * disp_w + off_x
        y = rect_norm.y() * disp_h + off_y
        w = rect_norm.width() * disp_w
        h = rect_norm.height() * disp_h
        return QRectF(x, y, w, h)

    def map_from_screen(self, point):
        win_w, win_h = self.width(), self.height()
        if not self._pixmap: return 0.0, 0.0
        base_scale = min(win_w / self._pixmap.width(), win_h / self._pixmap.height())
        final_scale = base_scale * self._scale
        disp_w = int(self._pixmap.width() * final_scale)
        disp_h = int(self._pixmap.height() * final_scale)
        off_x = (win_w - disp_w) // 2 + self._pan_x
        off_y = (win_h - disp_h) // 2 + self._pan_y
        
        nx = (point.x() - off_x) / disp_w
        ny = (point.y() - off_y) / disp_h
        return nx, ny
        
    def limit_to_image_bounds(self, nx, ny):
        return max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny))

    def get_handle_at(self, pos, rect_screen):
        hs = self.HANDLE_SIZE
        x, y, w, h = rect_screen.x(), rect_screen.y(), rect_screen.width(), rect_screen.height()
        
        if QRectF(x - hs/2, y - hs/2, hs, hs).contains(pos): return self.HANDLE_TOP_LEFT
        if QRectF(x + w - hs/2, y - hs/2, hs, hs).contains(pos): return self.HANDLE_TOP_RIGHT
        if QRectF(x - hs/2, y + h - hs/2, hs, hs).contains(pos): return self.HANDLE_BOTTOM_LEFT
        if QRectF(x + w - hs/2, y + h - hs/2, hs, hs).contains(pos): return self.HANDLE_BOTTOM_RIGHT
        
        if QRectF(x + hs/2, y - hs/2, w - hs, hs).contains(pos): return self.HANDLE_TOP
        if QRectF(x + hs/2, y + h - hs/2, w - hs, hs).contains(pos): return self.HANDLE_BOTTOM
        if QRectF(x - hs/2, y + hs/2, hs, h - hs).contains(pos): return self.HANDLE_LEFT
        if QRectF(x + w - hs/2, y + hs/2, hs, h - hs).contains(pos): return self.HANDLE_RIGHT
        
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if not self._pixmap:
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(self.rect(), Qt.AlignCenter, "请加载图片文件夹并选择图片进行标注") # type: ignore
            return

        win_w, win_h = self.width(), self.height()
        base_scale = min(win_w / self._pixmap.width(), win_h / self._pixmap.height()) if self._pixmap.width() > 0 else 1.0
        final_scale = base_scale * self._scale
        disp_w = int(self._pixmap.width() * final_scale)
        disp_h = int(self._pixmap.height() * final_scale)
        off_x = (win_w - disp_w) // 2 + self._pan_x
        off_y = (win_h - disp_h) // 2 + self._pan_y
        
        target_rect = QRect(int(off_x), int(off_y), disp_w, disp_h)
        painter.drawPixmap(target_rect, self._pixmap)
        
        # Draw Shapes
        for i, shape in enumerate(self._shapes):
            rect_norm = shape['rect']
            screen_rect = self.map_to_screen(rect_norm)
            
            cls_idx = shape['class_index']
            color_tuple = self.main_tab.get_class_color(cls_idx)
            color = QColor(*color_tuple)
            
            is_selected = (i in self.selected_indices)
            pen_width = 3 if is_selected else 2
            painter.setPen(QPen(color, pen_width))
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 80 if is_selected else 0))
            painter.drawRect(screen_rect)
            
            label_name = self.main_tab.get_class_name(cls_idx)
            fm = painter.fontMetrics()
            txt_w = fm.width(label_name) + 10
            txt_h = fm.height() + 4
            txt_bg_rect = QRectF(screen_rect.left(), screen_rect.top() - txt_h, txt_w, txt_h)
            painter.fillRect(txt_bg_rect, color)
            painter.setPen(QColor(255, 255, 255) if color.lightness() < 128 else QColor(0, 0, 0))
            painter.drawText(txt_bg_rect, Qt.AlignCenter, label_name) # type: ignore
            
            if is_selected:
                painter.setPen(QColor(0, 0, 255))
                painter.setBrush(QColor(255, 255, 255))
                hs = self.HANDLE_SIZE
                sx, sy, sw, sh = screen_rect.x(), screen_rect.y(), screen_rect.width(), screen_rect.height()
                handles = [
                    QPoint(int(sx), int(sy)), QPoint(int(sx+sw), int(sy)), 
                    QPoint(int(sx), int(sy+sh)), QPoint(int(sx+sw), int(sy+sh)),
                    QPoint(int(sx+sw/2), int(sy)), QPoint(int(sx+sw/2), int(sy+sh)),
                    QPoint(int(sx), int(sy+sh/2)), QPoint(int(sx+sw), int(sy+sh/2))
                ]
                for p in handles:
                    painter.drawRect(int(p.x()-hs/2), int(p.y()-hs/2), hs, hs)

        # Draw New Rect
        rect = self._current_rect
        if rect is not None:
            painter.setPen(QPen(QColor(255, 255, 255), 2, Qt.DashLine)) # type: ignore
            painter.setBrush(Qt.NoBrush) # type: ignore
            painter.drawRect(rect)
            
        # Draw Selection Box (Rubber Band)
        if self._selection_rect is not None:
            painter.setPen(QPen(QColor(0, 120, 215), 1, Qt.DashLine))
            painter.setBrush(QColor(0, 120, 215, 50))
            painter.drawRect(self._selection_rect)

    def mousePressEvent(self, event):
        if not self._pixmap: return
        pos = event.localPos() 
        modifiers = QApplication.keyboardModifiers()
        
        # --- Right Click ---
        if event.button() == Qt.RightButton: # type: ignore
            hit_shape = self.get_shape_at(pos)
            
            # 如果点击了已选中的某个框，则不改变当前选择集合，直接弹出菜单
            if hit_shape != -1 and hit_shape in self.selected_indices:
                pass 
            elif hit_shape != -1:
                # 点击了未选中的框 -> 选中它 (单选)
                self.selected_indices.clear()
                self.selected_indices.add(hit_shape)
                self.update()
                self.main_tab.sync_list_selection_from_canvas() 
            
            if self.selected_indices:
                # 弹出菜单 (针对所有选中项)
                self.main_tab.show_annotation_context_menu(self.mapToGlobal(event.pos()), from_canvas=True)
            else:
                self._state = self.STATE_PANNING
                self._last_mouse_pos = pos
                self._pan_start_pos = pos
                self.setCursor(Qt.ClosedHandCursor) # type: ignore
            return

        # --- Left Click ---
        if event.button() == Qt.LeftButton: # type: ignore
            
            # 1. Check Handles (Priority)
            # 只有当选中单个的时候，或者点击的是当前操作的目标时
            # 需求：多选时，点击对应的框进行大小修改 -> 取消其他，只修改这一个
            
            # Find handle on ANY selected shape? 
            # Or usually handle is checked on the 'last' selected?
            # Iterating all selected shapes to find a handle click
            clicked_handle_shape = -1
            handle_code = None
            
            for idx in self.selected_indices:
                rect_norm = self._shapes[idx]['rect']
                screen_rect = self.map_to_screen(rect_norm)
                h = self.get_handle_at(pos, screen_rect)
                if h:
                    clicked_handle_shape = idx
                    handle_code = h
                    break
            
            if clicked_handle_shape != -1:
                # Clicked a handle
                # Logic: Cancel others, select only this one
                self.selected_indices.clear()
                self.selected_indices.add(clicked_handle_shape)
                self.main_tab.sync_list_selection_from_canvas() 
                
                self._state = self.STATE_RESIZING
                self._active_handle = handle_code
                self._drag_start_rects = {clicked_handle_shape: self._shapes[clicked_handle_shape]['rect']} 
                self._last_mouse_pos = pos
                self.update()
                return

            # 2. Check Hit Body
            hit_shape = self.get_shape_at(pos)
            
            if modifiers & Qt.ControlModifier:
                if hit_shape != -1:
                    # Toggle selection
                    if hit_shape in self.selected_indices:
                        self.selected_indices.remove(hit_shape)
                    else:
                        self.selected_indices.add(hit_shape)
                    self.main_tab.sync_list_selection_from_canvas() 
                    self.update()
                    return # Toggle toggles, doesn't start moving immediately usually? Or maybe allows moving?
                    # Windows Explorer Ctrl+Click selects. To move you need to drag. 
                    # If I return here, drag won't start.
                    # But if I don't return, I need state.
                    # Let's enter Moving Candidate state? 
                    # Simpler: If hit, we toggle. If user holds and moves, it's a drag.
                    # But Ctrl+Drag on item is usually Copy in many apps. Here user says "toggle".
                    # Let's assume just selection toggling on click. Movement requires explicit drag state setup.
                    # If I set STATE_MOVING here, it might conflict with toggle if not moved.
                    # Standard logic: MousePress toggles. If simple click, done. If drag...
                    # Let's just select/deselect. If user wants to move multiple, they usually Select All then Drag without Ctrl?
                    # User: "按住ctrl...左键鼠标点击多个标注框也可以进行多选...位置拖动不需要取消其他选中" -> implies dragging works.
                    # So if I Ctrl+Click an UNSELECTED item, it becomes SELECTED. Then if I drag, I move ALL selected.
                    # So I should fall through to Moving logic.
                else:
                    # Ctrl + Click Empty -> Rubber Band
                    self._state = self.STATE_SELECT_BOX
                    self._start_pos = pos
                    self._selection_rect = QRectF(pos, pos)
                    return
            
            # Not Ctrl
            if hit_shape != -1:
                if hit_shape not in self.selected_indices:
                     # Clicked an unselected shape without Ctrl -> Select only this one
                     self.selected_indices.clear()
                     self.selected_indices.add(hit_shape)
                     self.main_tab.sync_list_selection_from_canvas() 
                
                # Setup Moving (for all selected)
                self._state = self.STATE_MOVING
                self._drag_start_rects = {i: self._shapes[i]['rect'] for i in self.selected_indices}
                self._last_mouse_pos = pos
                self.update()
                return

            # 3. Clicked Empty Space (No Hit)
            # "在点击图片区域时自动取消多选并选中最后一个点击的行类别，进行标注"
            self.selected_indices.clear()
            self.main_tab.annotation_table.clearSelection()
            self.main_tab.prepare_drawing_class_selection() # 触发类别列表多选归一逻辑
            
            self._state = self.STATE_DRAWING
            
            nx, ny = self.map_from_screen(pos)
            if 0 <= nx <= 1 and 0 <= ny <= 1:
                self._start_pos = pos
                self._current_rect = QRectF(pos, pos)
                self.update()
            else:
                nx, ny = self.limit_to_image_bounds(nx, ny)
                clamped_rect = self.map_to_screen(QRectF(nx, ny, 0, 0))
                self._start_pos = clamped_rect.topLeft()
                self._current_rect = QRectF(self._start_pos, self._start_pos)
                self.update()

    def mouseMoveEvent(self, event):
        pos = event.localPos()
        
        if self._state == self.STATE_PANNING:
            delta = pos - self._last_mouse_pos
            self._pan_x += delta.x()
            self._pan_y += delta.y()
            self._last_mouse_pos = pos
            self.update()
            
        elif self._state == self.STATE_DRAWING:
            if self._start_pos is not None:
                nx, ny = self.map_from_screen(pos)
                nx, ny = self.limit_to_image_bounds(nx, ny)
                nx_s, ny_s = self.map_from_screen(self._start_pos)
                nx_s, ny_s = self.limit_to_image_bounds(nx_s, ny_s) 
                
                rect_norm = QRectF(QPointF(nx_s, ny_s), QPointF(nx, ny)).normalized()
                self._current_rect = self.map_to_screen(rect_norm)
                self.update()

        elif self._state == self.STATE_SELECT_BOX:
             # Rubber Band
             if self._start_pos is not None:
                 self._selection_rect = QRectF(self._start_pos, pos).normalized()
                 self.update()
                
        elif self._state == self.STATE_MOVING:
            if self.selected_indices and self._drag_start_rects:
                nx1, ny1 = self.map_from_screen(self._last_mouse_pos)
                nx2, ny2 = self.map_from_screen(pos)
                dx = nx2 - nx1
                dy = ny2 - ny1
                
                # Check bounds for ALL shapes to determine valid dx, dy
                # "有两个框移动时左框碰到左边界，则两个都不可再往左移动"
                valid_dx = dx
                valid_dy = dy
                
                for idx in self.selected_indices:
                    orig_r = self._drag_start_rects.get(idx)
                    if not orig_r: continue
                    
                    # Test move
                    test_r = orig_r.translated(dx, dy)
                    
                    # Check X
                    if test_r.left() < 0: valid_dx = max(valid_dx, 0 - orig_r.left())
                    if test_r.right() > 1: valid_dx = min(valid_dx, 1 - orig_r.right())
                    
                    # Check Y
                    if test_r.top() < 0: valid_dy = max(valid_dy, 0 - orig_r.top())
                    if test_r.bottom() > 1: valid_dy = min(valid_dy, 1 - orig_r.bottom())

                # Apply valid delta (accumulated from start or incremental?)
                # We used incremental from last_pos. 
                # Better to use Total Delta from Drag Start to avoid rounding errors?
                # But here we used last_pos. Let's recalculate based on last_pos but clamped.
                
                # With calculated valid_dx/dy, we apply to current rects?
                # No, standard implementation:
                # 1. Update positions.
                # 2. Update last_pos (be careful with clamping, if clamped, we shouldn't advance mouse ref potentially?)
                # Actually, simpler: Calculate proposed new rects. If invalid, clamp delta.
                
                # Implementation:
                # Calculate constrained dx, dy based on current positions
                current_dx = dx
                current_dy = dy
                
                for idx in self.selected_indices:
                    r = self._shapes[idx]['rect']
                    if r.left() + current_dx < 0: current_dx = -r.left()
                    if r.right() + current_dx > 1: current_dx = 1 - r.right()
                    if r.top() + current_dy < 0: current_dy = -r.top()
                    if r.bottom() + current_dy > 1: current_dy = 1 - r.bottom()
                
                # Apply
                if current_dx != 0 or current_dy != 0:
                    for idx in self.selected_indices:
                         r = self._shapes[idx]['rect']
                         self._shapes[idx]['rect'] = r.translated(current_dx, current_dy)
                    
                    # Update mouse pos only if moved?
                    # Mapping back is imperfect. Just update last_pos to current pos is standard,
                    # but if we clamped, the mouse drifted from the object. That's fine.
                    self._last_mouse_pos = pos 
                    self.update()
                
        elif self._state == self.STATE_RESIZING:
            idx = list(self.selected_indices)[0] # Should be only one
            if idx in self._drag_start_rects:
                nx, ny = self.map_from_screen(pos)
                nx, ny = self.limit_to_image_bounds(nx, ny)
                
                r = self._shapes[idx]['rect']
                l, t, r_edge, b = r.left(), r.top(), r.right(), r.bottom()
                
                if self._active_handle == self.HANDLE_TOP_LEFT: l, t = nx, ny
                elif self._active_handle == self.HANDLE_TOP_RIGHT: r_edge, t = nx, ny
                elif self._active_handle == self.HANDLE_BOTTOM_LEFT: l, b = nx, ny
                elif self._active_handle == self.HANDLE_BOTTOM_RIGHT: r_edge, b = nx, ny
                elif self._active_handle == self.HANDLE_TOP: t = ny
                elif self._active_handle == self.HANDLE_BOTTOM: b = ny
                elif self._active_handle == self.HANDLE_LEFT: l = nx
                elif self._active_handle == self.HANDLE_RIGHT: r_edge = nx
                
                if l > r_edge: l, r_edge = r_edge, l
                if t > b: t, b = b, t

                new_rect = QRectF(QPointF(l, t), QPointF(r_edge, b))
                self._shapes[idx]['rect'] = new_rect
                self.update()

        else:
            # Hover cursor
            hit_shape = self.get_shape_at(pos)
            if hit_shape != -1 and hit_shape in self.selected_indices and len(self.selected_indices) == 1:
                # Only show resize cursors if SINGLE selection
                r = self._shapes[hit_shape]['rect']
                sr = self.map_to_screen(r)
                handle = self.get_handle_at(pos, sr)
                if handle in [self.HANDLE_TOP_LEFT, self.HANDLE_BOTTOM_RIGHT]: self.setCursor(Qt.SizeFDiagCursor) # type: ignore
                elif handle in [self.HANDLE_TOP_RIGHT, self.HANDLE_BOTTOM_LEFT]: self.setCursor(Qt.SizeBDiagCursor) # type: ignore
                elif handle in [self.HANDLE_TOP, self.HANDLE_BOTTOM]: self.setCursor(Qt.SizeVerCursor) # type: ignore
                elif handle in [self.HANDLE_LEFT, self.HANDLE_RIGHT]: self.setCursor(Qt.SizeHorCursor) # type: ignore
                elif sr.contains(pos): self.setCursor(Qt.SizeAllCursor) # type: ignore
                else: self.setCursor(Qt.ArrowCursor) # type: ignore
            elif hit_shape != -1:
                 # Hovering over a shape (multi selected or unselected)
                 self.setCursor(Qt.SizeAllCursor) 
            else:
                self.setCursor(Qt.ArrowCursor) # type: ignore

    def mouseReleaseEvent(self, event):
        if self._state == self.STATE_PANNING:
            if self._pan_start_pos is not None:
                dist = (event.localPos() - self._pan_start_pos).manhattanLength()
                if dist < 5:
                     self.main_tab.show_annotation_context_menu(self.mapToGlobal(event.pos()), from_canvas=True)
            self._pan_start_pos = None

        elif self._state == self.STATE_DRAWING:
            rect = self._current_rect
            if rect is not None and (rect.width() > 5 or rect.height() > 5):
                nx_tl, ny_tl = self.map_from_screen(rect.topLeft())
                nx_br, ny_br = self.map_from_screen(rect.bottomRight())
                nx_tl, ny_tl = self.limit_to_image_bounds(nx_tl, ny_tl)
                nx_br, ny_br = self.limit_to_image_bounds(nx_br, ny_br)
                w = nx_br - nx_tl
                h = ny_br - ny_tl
                if w > 0 and h > 0:
                    norm_rect = QRectF(nx_tl, ny_tl, w, h).normalized()
                    self.main_tab.add_new_shape(norm_rect)
            self._current_rect = None
        
        elif self._state == self.STATE_SELECT_BOX:
            # Apply Rubber Band Selection
            if self._selection_rect:
                # Find all intersecting shapes
                s_rect = self._selection_rect.normalized()
                toggle_indices = []
                for i, shape in enumerate(self._shapes):
                    screen_rect = self.map_to_screen(shape['rect'])
                    # Strict contained or intersect? "在内的标注框...选中已选中的框则取消选中"
                    # Usually "intersects" is easier, but "在内" means contained. 
                    # "rectangular box (unrestricted)... frames WITHIN" -> Contained.
                    # But standard behavior is often Intersects. 
                    # Let's use Intersects for easier selection, or Contains if user was strict.
                    # "在内的" -> Inside.
                    if s_rect.contains(screen_rect) or s_rect.intersects(screen_rect):
                        toggle_indices.append(i)
                
                for i in toggle_indices:
                    if i in self.selected_indices:
                        self.selected_indices.remove(i)
                    else:
                        self.selected_indices.add(i)
                
                self.main_tab.sync_list_selection_from_canvas()
                self.update()
            self._selection_rect = None

        elif self._state in [self.STATE_MOVING, self.STATE_RESIZING]:
            # Update timestamps for all modified
            ts = get_timestamp()
            if self._drag_start_rects:
                changes = {}
                for idx in self.selected_indices:
                    if idx in self._drag_start_rects:
                        old_r = self._drag_start_rects[idx]
                        r = self._shapes[idx]['rect'] if isinstance(self._shapes[idx], dict) else self._shapes[idx][0]
                        x, y, w, h = r.x(), r.y(), r.width(), r.height()
                        new_r = QRectF(max(0.0, min(1.0-w, x)), max(0.0, min(1.0-h, y)), w, h)
                        
                        if old_r != new_r:
                            # 本地先还原到 old，并加入 changes 提供给 Action 初始化执行
                            if isinstance(self._shapes[idx], dict): self._shapes[idx]['rect'] = old_r
                            else: self._shapes[idx][0] = old_r
                            changes[idx] = (old_r, new_r)

                if changes:
                    # BulkModifyShapeRectAction 与之前的 ModifyShapeRectAction 架构类似
                    # 把这批 changes 的 dict 传进去，do() 里赋新尺寸，undo() 里赋旧尺寸
                    action = BulkModifyShapeRectAction(self.main_tab, changes)
                    self.main_tab.action_pool.execute(action)

            self._drag_start_rects.clear()
        
        self._state = self.STATE_IDLE
        self.setCursor(Qt.ArrowCursor) # type: ignore
        self.update()

    def get_shape_at(self, pos):
        for i in range(len(self._shapes)-1, -1, -1):
            rect_norm = self._shapes[i]['rect']
            screen_rect = self.map_to_screen(rect_norm)
            if screen_rect.contains(pos):
                return i
        return -1

    def wheelEvent(self, event):
        if not self._pixmap: return
        zoom_in = event.angleDelta().y() > 0
        factor = 1.1 if zoom_in else 0.9
        self._scale *= factor
        self.update()

# ============================================
# 标注主界面
# ============================================

class AnnotationApp(QWidget):
    FORMAT_YOLO_TXT = "YOLO (.txt)"
    FORMAT_VOC_XML = "PASCAL VOC (.xml)"
    FORMAT_COCO_JSON = "MS COCO (.json)"

    def __init__(self):
        super().__init__()
        self.current_image_path = None
        self.class_data = [] 
        self.current_class_index = -1 
        self.current_format = self.FORMAT_YOLO_TXT 
        
        # COCO Support Data
        self.coco_data = {}
        self.coco_file_name = "annotations.json" 
        
        self.action_pool = ActionPool(self)
        
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        splitter = QSplitter(Qt.Horizontal) # type: ignore

        # --- Left Panel ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)
        
        # Format Selection Row
        fmt_layout = QHBoxLayout()
        fmt_layout.addWidget(QLabel("工作格式:"))
        self.format_combo = ComboBoxWithArrow()
        self.format_combo.addItems([self.FORMAT_YOLO_TXT, self.FORMAT_VOC_XML, self.FORMAT_COCO_JSON])
        self.format_combo.currentTextChanged.connect(self.on_format_changed)
        fmt_layout.addWidget(self.format_combo)
        
        btn_export = QPushButton("导出")
        btn_export.clicked.connect(self.export_annotations_dialog)
        fmt_layout.addWidget(btn_export)
        
        if SHOW_ACTION_POOL_DEBUG:
            btn_action_log = QPushButton("操作池日志")
            btn_action_log.clicked.connect(self.show_action_pool_log)
            fmt_layout.addWidget(btn_action_log)

        left_layout.addLayout(fmt_layout)
        left_layout.addSpacing(10)

        # Image Dir
        self.btn_open_dir = QPushButton(" 打开图片目录")
        self.btn_open_dir.setIcon(QIcon(resource_path("assets/icon_browse.png")))
        self.btn_open_dir.clicked.connect(self.open_directory)
        left_layout.addWidget(self.btn_open_dir)
        
        self.img_dir_edit = QLineEdit()
        self.img_dir_edit.setPlaceholderText("未选择图片目录")
        self.img_dir_edit.setReadOnly(True)
        left_layout.addWidget(self.img_dir_edit)

        # Label Dir
        left_layout.addSpacing(5)
        btn_out_browse = QPushButton(" 选择标签目录")
        btn_out_browse.setIcon(QIcon(resource_path("assets/icon_browse.png")))
        btn_out_browse.clicked.connect(self.select_output_dir)
        left_layout.addWidget(btn_out_browse)
        
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("保存位置 (默认与图片目录同级labels)")
        self.output_dir_edit.setReadOnly(True)
        left_layout.addWidget(self.output_dir_edit)

        # --- Resizable List Area (Splitter) ---
        left_layout.addSpacing(10)
        
        list_splitter = QSplitter(Qt.Vertical)
        list_splitter.setHandleWidth(4) # Easier to grab
        # Handle style (optional visual cue)
        list_splitter.setStyleSheet("QSplitter::handle { background-color: #3e3e42; }")

        # Group 1: Classes
        class_widget = QWidget()
        class_layout_g = QVBoxLayout(class_widget)
        class_layout_g.setContentsMargins(0, 0, 0, 0)
        class_layout_g.setSpacing(5)
        class_layout_g.addWidget(QLabel("类别列表 (支持右键/拖拽):"))

        self.class_table = DraggableTableWidget()
        self.class_table.main_app = self # type: ignore
        self.class_table.setColumnCount(3)
        self.class_table.setHorizontalHeaderLabels(["类别序号", "名称", "修改时间"])
        # 自定义行高/间距以方便拖拽，增加 padding 模拟间隔
        self.class_table.setStyleSheet("""
            QTableWidget::item { 
                padding-top: 8px; 
                padding-bottom: 8px; 
            }
        """) 
        
        self.class_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.class_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.class_table.setEditTriggers(QAbstractItemView.NoEditTriggers) # v0.5.2: Disable double click edit

        self.setup_table_interface(self.class_table, [
            ("类别序号", FilterCondition.TYPE_NUMBER),
            ("名称", FilterCondition.TYPE_TEXT),
            ("修改时间", FilterCondition.TYPE_DATETIME)
        ])
        
        # Remove setFixedHeight to allow resizing
        # self.class_table.setFixedHeight(150) 
        
        self.class_table.customContextMenuRequested.connect(self.show_class_context_menu)
        self.class_table.itemClicked.connect(self.on_category_clicked)
        # 类别列表多选支持
        self.class_table.itemSelectionChanged.connect(self.on_class_selection_changed)
        self.class_table.set_main_app(self)
        
        class_layout_g.addWidget(self.class_table)
        list_splitter.addWidget(class_widget)

        # Group 2: Annotations
        anno_widget = QWidget()
        anno_layout_g = QVBoxLayout(anno_widget)
        anno_layout_g.setContentsMargins(0, 0, 0, 0)
        anno_layout_g.setSpacing(5)
        anno_layout_g.addWidget(QLabel("当前图片标注列表:"))
        
        self.annotation_table = QTableWidget()
        self.annotation_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.annotation_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.annotation_table.setColumnCount(4)
        self.annotation_table.setHorizontalHeaderLabels(["序号", "类别序号", "名称", "修改时间"])
        
        self.annotation_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.annotation_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        
        # 标注列表右键菜单与多选同步
        self.annotation_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.annotation_table.customContextMenuRequested.connect(lambda pos: self.show_annotation_context_menu(self.annotation_table.mapToGlobal(pos), from_canvas=False))
        self.annotation_table.itemSelectionChanged.connect(self.sync_canvas_selection_from_list)

        self.setup_table_interface(self.annotation_table, [
            ("序号", FilterCondition.TYPE_NUMBER),
            ("类别序号", FilterCondition.TYPE_NUMBER),
            ("名称", FilterCondition.TYPE_TEXT),
            ("修改时间", FilterCondition.TYPE_DATETIME)
        ])

        # Remove setFixedHeight
        # self.annotation_table.setFixedHeight(120)
        
        self.annotation_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # self.annotation_table.setSelectionMode(QAbstractItemView.SingleSelection) # Removed in v0.5.2 to allow Ctrl+A
        self.annotation_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # customContextMenuRequested already connected above
        self.annotation_table.itemClicked.connect(self.on_annotation_item_clicked)
        
        anno_layout_g.addWidget(self.annotation_table)
        list_splitter.addWidget(anno_widget)

        # Group 3: Files
        file_widget = QWidget()
        file_layout_g = QVBoxLayout(file_widget)
        file_layout_g.setContentsMargins(0, 0, 0, 0)
        file_layout_g.setSpacing(5)
        file_layout_g.addWidget(QLabel("图片文件列表:"))

        self.file_table = QTableWidget()
        self.file_table.setColumnCount(2)
        self.file_table.setHorizontalHeaderLabels(["文件名", "修改时间"])
        
        self.file_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.file_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

        self.setup_table_interface(self.file_table, [
            ("文件名", FilterCondition.TYPE_TEXT),
            ("修改时间", FilterCondition.TYPE_DATETIME)
        ])

        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.itemClicked.connect(self.on_file_clicked)
        
        file_layout_g.addWidget(self.file_table)
        list_splitter.addWidget(file_widget)

        # Set stretch factors (Classes:Annot:Files = 2:2:4)
        list_splitter.setStretchFactor(0, 2)
        list_splitter.setStretchFactor(1, 2)
        list_splitter.setStretchFactor(2, 4)

        left_layout.addWidget(list_splitter) 
        
        # --- Right Panel ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        
        nav_layout = QHBoxLayout()
        self.lbl_current_file = QLabel("未选择文件")
        self.lbl_current_file.setStyleSheet("font-weight: bold; color: #00aaff;")
        
        # 撤销与重做设为分离式工具按钮 (Split Button)
        from PyQt5.QtWidgets import QToolButton
        
        btn_style = """
        QToolButton { 
            border: 1px solid #3e3e42; 
            border-radius: 4px; 
            background-color: #333333; 
            padding: 6px 12px; 
            padding-right: 25px; /* leave space for the menu button */
            min-height: 24px;
            color: #f0f0f0;
        }
        QToolButton:hover { 
            background-color: #3e3e42; 
            border-color: #007acc; 
        }
        QToolButton:pressed { 
            background-color: #007acc;
            color: #ffffff;
            border-color: #007acc;
        }
        QToolButton:disabled { 
            background-color: #252526; 
            color: #6d6d6d; 
            border-color: #2d2d30; 
        }
        QToolButton::menu-button {
            border-left: 1px solid #555;
            border-top-right-radius: 4px;
            border-bottom-right-radius: 4px;
            width: 25px;
        }
        QToolButton::menu-arrow {
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid #00ff00; /* Green Down Triangle */
            margin-right: 5px;
        }
        QToolButton::menu-arrow:open {
            border-top: none;
            border-bottom: 5px solid #00ff00; /* Green Up Triangle */
        }
        """

        self.btn_undo = QToolButton()
        self.btn_undo.setText(" 撤销")
        self.btn_undo.setToolTip("撤销 (Ctrl+Z)")
        self.btn_undo.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_undo.clicked.connect(self.action_pool.undo)
        self.btn_undo.setStyleSheet(btn_style)
        self.menu_undo = QMenu(self.btn_undo)
        self.btn_undo.setMenu(self.menu_undo)
        
        self.btn_redo = QToolButton()
        self.btn_redo.setText(" 重做")
        self.btn_redo.setToolTip("重做 (Ctrl+Y)")
        self.btn_redo.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_redo.clicked.connect(self.action_pool.redo)
        self.btn_redo.setStyleSheet(btn_style)
        self.menu_redo = QMenu(self.btn_redo)
        self.btn_redo.setMenu(self.menu_redo)
        
        btn_prev = QPushButton(" 上一张")
        btn_prev.setToolTip("上一张 (←)")
        btn_prev.clicked.connect(lambda: self.change_image(-1))
        btn_next = QPushButton(" 下一张")
        btn_next.setToolTip("下一张 (→)")
        btn_next.clicked.connect(lambda: self.change_image(1))
        
        nav_layout.addWidget(QLabel("当前:"))
        nav_layout.addWidget(self.lbl_current_file, 1)
        nav_layout.addWidget(self.btn_undo)
        nav_layout.addWidget(self.btn_redo)
        nav_layout.addWidget(btn_prev)
        nav_layout.addWidget(btn_next)

        if getattr(self, "SHOW_ACTION_POOL_DEBUG", False):
            btn_debug = QPushButton(" ⚙️ 操作池看板")
            btn_debug.setStyleSheet("background-color: #552222; color: #ffcccc;")
            btn_debug.clicked.connect(self.show_action_pool_log)
            nav_layout.addWidget(btn_debug)

        right_layout.addLayout(nav_layout)

        self.canvas = AnnotationCanvas(self) 
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        canvas_container = QFrame()
        canvas_container.setStyleSheet("background-color: transparent; border: 1px solid #444;")
        
        c_layout = QVBoxLayout(canvas_container)
        c_layout.setContentsMargins(0,0,0,0)
        c_layout.addWidget(self.canvas)
        right_layout.addWidget(canvas_container)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter)
        self.setLayout(layout)
        
        self.class_table.installEventFilter(self)
        self.annotation_table.installEventFilter(self)
        self.file_table.installEventFilter(self)
        
        # 快捷键配置
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence

        def safe_trigger(action_func):
            def wrapper():
                focus_widget = QApplication.focusWidget()
                if isinstance(focus_widget, (QLineEdit, QTextEdit)):
                    return
                action_func()
            return wrapper

        def safe_change_image(direction):
            def wrapper():
                focus_widget = QApplication.focusWidget()
                if isinstance(focus_widget, (QLineEdit, QTextEdit)):
                    return
                self.change_image(direction)
            return wrapper

        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(safe_trigger(self.action_pool.undo))
        QShortcut(QKeySequence("Ctrl+Y"), self).activated.connect(safe_trigger(self.action_pool.redo))
        QShortcut(QKeySequence(Qt.Key_Left), self).activated.connect(safe_change_image(-1))
        QShortcut(QKeySequence(Qt.Key_Right), self).activated.connect(safe_change_image(1))
        
        self.update_undo_redo_ui()

    def _jump_undo(self, steps):
        for _ in range(steps):
            if not self.action_pool.undo_stack:
                break
            self.action_pool.undo()

    def _jump_redo(self, steps):
        for _ in range(steps):
            if not self.action_pool.redo_stack:
                break
            self.action_pool.redo()

    def update_undo_redo_ui(self):
        """Update Undo and Redo buttons and their dropdown menus."""
        self.menu_undo.clear()
        self.menu_redo.clear()
        
        # 设置菜单字体和样式（可选）
        if not self.action_pool.undo_stack:
            self.btn_undo.setEnabled(False)
            act = self.menu_undo.addAction("没有可撤销的操作")
            act.setEnabled(False)
        else:
            self.btn_undo.setEnabled(True)
            for i, action in enumerate(reversed(self.action_pool.undo_stack)):
                # i+1 is the number of steps to jump back!
                act = self.menu_undo.addAction(f"{i+1}步前: {action.description}")
                act.triggered.connect(lambda checked, steps=i+1: self._jump_undo(steps))
                
        if not self.action_pool.redo_stack:
            self.btn_redo.setEnabled(False)
            act = self.menu_redo.addAction("没有可重做的操作")
            act.setEnabled(False)
        else:
            self.btn_redo.setEnabled(True)
            for i, action in enumerate(reversed(self.action_pool.redo_stack)):
                act = self.menu_redo.addAction(f"{i+1}步后: {action.description}")
                act.triggered.connect(lambda checked, steps=i+1: self._jump_redo(steps))

    def setup_table_interface(self, table, col_definitions):
        # 1. 设置自定义 header
        header = CustomHeader(Qt.Horizontal, table) # type: ignore
        table.setHorizontalHeader(header)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        table.setSortingEnabled(True)
        table.setContextMenuPolicy(Qt.CustomContextMenu) # type: ignore
        
        # 2. 绑定 header 右键菜单
        header.setContextMenuPolicy(Qt.CustomContextMenu) # type: ignore
        header.customContextMenuRequested.connect(lambda pos: self.show_header_menu(pos, table, col_definitions))

        # 3. 存储元数据到 Table 对象上
        table.col_definitions = col_definitions # type: ignore
        table.active_filters = [] # type: ignore

    def show_header_menu(self, pos, table, col_definitions):
        header = table.horizontalHeader()
        menu = QMenu(header)
        
        action_filter = QAction("筛选设置", header)
        action_filter.triggered.connect(lambda: self.open_filter_dialog(table, col_definitions))
        menu.addAction(action_filter)
        
        # 如果有筛选，提供清除
        if getattr(table, 'active_filters', []):
            action_clear = QAction("取消筛选", header)
            action_clear.triggered.connect(lambda: self.clear_table_filters(table))
            menu.addAction(action_clear)
            
        menu.exec_(header.mapToGlobal(pos))

    def open_filter_dialog(self, table, col_definitions):
        current_fs = getattr(table, 'active_filters', [])
        dlg = AdvancedFilterDialog(self, col_definitions, current_fs)
        if dlg.exec_() == QDialog.Accepted:
            new_filters = dlg.get_filters()
            table.active_filters = new_filters # type: ignore
            self.apply_table_filters(table)

    def clear_table_filters(self, table):
        table.active_filters = [] # type: ignore
        self.apply_table_filters(table)

    def apply_table_filters(self, table):
        filters = getattr(table, 'active_filters', [])
        
        # 1. Update Header Visuals
        header = table.horizontalHeader()
        if isinstance(header, CustomHeader):
            active_cols = set(f.col_idx for f in filters)
            # Clear all
            header.active_filters = active_cols
            vp = header.viewport()
            if vp: vp.update()

        # 2. Iterate Rows and Hide/Show
        row_count = table.rowCount()
        for r in range(row_count):
            should_show = True
            
            # Logic: All filters must pass (AND)
            for f in filters:
                item = table.item(r, f.col_idx)
                if not item: 
                    should_show = False
                    break
                
                text = item.text()
                
                # Check based on type
                if f.col_type == FilterCondition.TYPE_NUMBER:
                    try:
                        val_float = float(text)
                        target_float = float(f.value)
                        
                        passed = True
                        if f.operator == FilterCondition.OP_EQ: passed = abs(val_float - target_float) < 1e-6
                        elif f.operator == FilterCondition.OP_NEQ: passed = abs(val_float - target_float) > 1e-6
                        elif f.operator == FilterCondition.OP_GT: passed = val_float > target_float
                        elif f.operator == FilterCondition.OP_LT: passed = val_float < target_float
                        elif f.operator == FilterCondition.OP_GTE: passed = val_float >= target_float
                        elif f.operator == FilterCondition.OP_LTE: passed = val_float <= target_float
                        elif f.operator == FilterCondition.OP_CONTAINS: passed = f.value in text # String fallback
                        elif f.operator == FilterCondition.OP_NOT_CONTAINS: passed = f.value not in text
                        
                        if not passed: should_show = False
                    except:
                        # Parse fail -> Hide? Or only hide if strict? 
                        # Let's say if filter is number but data isn't, hide.
                        should_show = False

                elif f.col_type == FilterCondition.TYPE_DATETIME:
                    # Try Parse
                    # Default fmt: %Y-%m-%d %H:%M or %Y-%m-%d %H:%M:%S
                    dt = None
                    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
                        try:
                            dt = datetime.strptime(text, fmt)
                            break
                        except: pass
                    
                    if not dt:
                        # Fallback to string match for Contains/Eq
                        if f.operator == FilterCondition.OP_CONTAINS: should_show = f.value in text
                        elif f.operator == FilterCondition.OP_NOT_CONTAINS: should_show = f.value not in text
                        elif f.operator == FilterCondition.OP_EQ: should_show = text == f.value
                        elif f.operator == FilterCondition.OP_NEQ: should_show = text != f.value
                        else: should_show = False # > < need parsing
                    else:
                        # Dimensions
                        check_val = dt
                        target_val = None
                        
                        # Prepare comparison values based on Dimension
                        try:
                            if f.dt_dim == FilterCondition.DT_YEAR: 
                                check_val = dt.year; target_val = int(f.value)
                            elif f.dt_dim == FilterCondition.DT_MONTH: 
                                check_val = dt.month; target_val = int(f.value)
                            elif f.dt_dim == FilterCondition.DT_DAY: 
                                check_val = dt.day; target_val = int(f.value)
                            elif f.dt_dim == FilterCondition.DT_HOUR: 
                                check_val = dt.hour; target_val = int(f.value)
                            elif f.dt_dim == FilterCondition.DT_MINUTE: 
                                check_val = dt.minute; target_val = int(f.value)
                            elif f.dt_dim == FilterCondition.DT_SECOND: 
                                check_val = dt.second; target_val = int(f.value)
                            else:
                                # Full datetime comparison? Or just string match if dim not selected
                                # Logic: If no DIM selected, try to parse target as DT and compare
                                pass
                        except:
                            should_show = False # Parse target value failed
                        
                        if target_val is not None:
                            # Compare numbers
                            if f.operator == FilterCondition.OP_EQ: should_show = check_val == target_val
                            elif f.operator == FilterCondition.OP_NEQ: should_show = check_val != target_val
                            elif f.operator == FilterCondition.OP_GT: should_show = check_val > target_val # type: ignore
                            elif f.operator == FilterCondition.OP_LT: should_show = check_val < target_val # type: ignore
                            elif f.operator == FilterCondition.OP_GTE: should_show = check_val >= target_val # type: ignore
                            elif f.operator == FilterCondition.OP_LTE: should_show = check_val <= target_val # type: ignore
                            # Contains not relevant for numbers
                        elif f.dt_dim is None:
                             # No dim specific, try string fallback or full parse
                             pass

                else: # Text
                    if f.operator == FilterCondition.OP_EQ: should_show = text == f.value
                    elif f.operator == FilterCondition.OP_NEQ: should_show = text != f.value
                    elif f.operator == FilterCondition.OP_CONTAINS: should_show = f.value in text
                    elif f.operator == FilterCondition.OP_NOT_CONTAINS: should_show = f.value not in text
                
                if not should_show: break
            
            table.setRowHidden(r, not should_show)


    # ==========================
    # Logic: Format & Export
    # ==========================
    
    def on_format_changed(self, text):
        prev_format = self.current_format
        if prev_format == text: return
        
        self.current_format = text
        # DarkDialogHelper.show_info(self, "格式变更", f"工作格式已切换为 {text}。\n注意：原有标注保留在原文件格式中，如需转换请使用【导出】功能。")
        
        # v0.5.2: Auto-refresh annotations for current image after changing format
        if self.current_image_path:
             filename = os.path.basename(self.current_image_path)
             # Reload using new format logic
             self.load_current_annotations(filename)
             self.refresh_annotation_table()
             self.canvas.update()

    def show_action_pool_log(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("操作池日志 (Debug)")
        dialog.resize(600, 400)
        layout = QVBoxLayout(dialog)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        logs = "\n".join(self.action_pool.action_log)
        text_edit.setPlainText(logs)
        layout.addWidget(text_edit)
        
        dialog.exec_()

    def export_annotations_dialog(self):
        items = [self.FORMAT_YOLO_TXT, self.FORMAT_VOC_XML, self.FORMAT_COCO_JSON]
        target_fmt, ok = QInputDialog.getItem(self, "导出标注", "选择目标导出格式:", items, 0, False)
        if not ok or not target_fmt: return
        
        default_export_path = os.path.join(self.output_dir_edit.text() or "", "export")
        export_dir = QFileDialog.getExistingDirectory(self, "选择导出目录", default_export_path)
        if not export_dir: return
        
        # 收集文件
        files = []
        total = self.file_table.rowCount()
        for row in range(total):
            item = self.file_table.item(row, 0)
            if item:
                files.append(item.text())
                
        if not files:
            DarkDialogHelper.show_warning(self, "提示", "没有可导出的文件。")
            return

        # 锁定当前状态用于线程读取
        current_fmt_locked = self.current_format
        src_dir_locked = self.output_dir_edit.text()
        
        # 如果当前是COCO格式，预加载数据以确保线程安全读取
        if current_fmt_locked == self.FORMAT_COCO_JSON:
             self._ensure_coco_loaded()
        
        # 封装加载函数，注入当前环境参数
        def load_func_wrapper(filename, fmt_ignored):
            return self._load_shapes_headless(filename, current_fmt_locked, root_dir_override=src_dir_locked)

        # 启动导出线程和进度对话框
        worker = ExportWorker(files, target_fmt, export_dir, load_func_wrapper, self._save_shapes_headless)
        dlg = ExportProgressDialog(self, worker)
        dlg.exec_()

    def _load_shapes_headless(self, filename, fmt, root_dir_override=None):
        shapes = []
        dir_path = root_dir_override if root_dir_override else self.output_dir_edit.text()
        
        if fmt == self.FORMAT_YOLO_TXT:
             txt_name = os.path.splitext(filename)[0] + ".txt"
             path = os.path.join(dir_path, txt_name)
             if os.path.exists(path):
                 with open(path, 'r', encoding='utf-8') as f:
                     for line in f:
                         parts = line.strip().split()
                         if len(parts) >= 5:
                             try:
                                 cls_idx = int(parts[0])
                                 cx, cy, w, h = map(float, parts[1:5])
                                 x, y = cx - w/2, cy - h/2
                                 shapes.append({'class_index': cls_idx, 'rect': QRectF(x, y, w, h)})
                             except: pass
        elif fmt == self.FORMAT_VOC_XML:
             xml_name = os.path.splitext(filename)[0] + ".xml"
             path = os.path.join(dir_path, xml_name)
             if os.path.exists(path):
                 try:
                     tree = ET.parse(path)
                     xml_root = tree.getroot()
                     size = xml_root.find('size')
                     width, height = 0.0, 0.0
                     if size is not None:
                         w_e = size.find('width')
                         h_e = size.find('height')
                         if w_e is not None and w_e.text is not None: width = float(w_e.text)
                         if h_e is not None and h_e.text is not None: height = float(h_e.text)
                     
                     for obj in xml_root.findall('object'):
                         name_e = obj.find('name')
                         name = name_e.text if (name_e is not None and name_e.text) else ""
                         bndbox = obj.find('bndbox')
                         if bndbox is not None:
                             xmin_e = bndbox.find('xmin')
                             ymin_e = bndbox.find('ymin')
                             xmax_e = bndbox.find('xmax')
                             ymax_e = bndbox.find('ymax')
                             if (xmin_e is not None and xmin_e.text is not None and 
                                 ymin_e is not None and ymin_e.text is not None and 
                                 xmax_e is not None and xmax_e.text is not None and 
                                 ymax_e is not None and ymax_e.text is not None):
                                 xmin = float(xmin_e.text)
                                 ymin = float(ymin_e.text)
                                 xmax = float(xmax_e.text)
                                 ymax = float(ymax_e.text)
                                 cls_idx = -1
                                 for i, c in enumerate(self.class_data):
                                     if c['name'] == name: cls_idx = i; break
                                 if cls_idx != -1 and width > 0:
                                     x, y, w, h = xmin/width, ymin/height, (xmax-xmin)/width, (ymax-ymin)/height
                                     shapes.append({'class_index': cls_idx, 'rect': QRectF(x, y, w, h)})
                 except: pass
        elif fmt == self.FORMAT_COCO_JSON:
             if not self.coco_data: self._ensure_coco_loaded()
             
             # v0.5.2: Use optimized maps if available
             img_entry = None
             if hasattr(self, 'coco_images_map') and self.coco_images_map:
                 img_entry = self.coco_images_map.get(filename)
             else:
                 img_entry = next((i for i in self.coco_data.get('images', []) if i['file_name'] == filename), None)

             if img_entry:
                 img_id = img_entry['id']
                 img_w, img_h = img_entry.get('width', 0), img_entry.get('height', 0)
                 
                 anns = []
                 if hasattr(self, 'coco_anns_map') and self.coco_anns_map:
                     anns = self.coco_anns_map.get(img_id, [])
                 else:
                     anns = [a for a in self.coco_data.get('annotations', []) if a['image_id'] == img_id]
                     
                 cat_id_to_idx = {} 
                 for i, c in enumerate(self.class_data):
                     for coco_cat in self.coco_data.get('categories', []):
                         if coco_cat['name'] == c['name']: cat_id_to_idx[coco_cat['id']] = i; break
                 
                 if img_w > 0 and img_h > 0:
                    for a in anns:
                        if a.get('category_id') in cat_id_to_idx:
                            box = a.get('bbox', [0,0,0,0])
                            shapes.append({'class_index': cat_id_to_idx[a['category_id']], 
                                            'rect': QRectF(box[0]/img_w, box[1]/img_h, box[2]/img_w, box[3]/img_h)})
        return shapes

    def _save_shapes_headless(self, shapes, filename, fmt, out_dir):
        if not os.path.exists(out_dir): os.makedirs(out_dir)
        img_path = os.path.join(self.current_dir, filename)
        img_w, img_h = 1000, 1000 
        if os.path.exists(img_path):
            from PyQt5.QtGui import QImage
            # Use QImage instead of QPixmap for thread safety
            img = QImage(img_path)
            if not img.isNull(): img_w, img_h = img.width(), img.height()
            
        if fmt == self.FORMAT_YOLO_TXT:
            txt_path = os.path.join(out_dir, os.path.splitext(filename)[0] + ".txt")
            with open(txt_path, 'w', encoding='utf-8') as f:
                for s in shapes:
                    r = s['rect']
                    cx, cy = r.x() + r.width()/2, r.y() + r.height()/2
                    f.write(f"{s['class_index']} {cx:.6f} {cy:.6f} {r.width():.6f} {r.height():.6f}\n")
                    
        elif fmt == self.FORMAT_VOC_XML:
            xml_path = os.path.join(out_dir, os.path.splitext(filename)[0] + ".xml")
            root = ET.Element('annotation')
            ET.SubElement(root, 'filename').text = filename
            size = ET.SubElement(root, 'size')
            ET.SubElement(size, 'width').text = str(img_w)
            ET.SubElement(size, 'height').text = str(img_h)
            for s in shapes:
                r = s['rect']
                obj = ET.SubElement(root, 'object')
                ET.SubElement(obj, 'name').text = self.get_class_name(s['class_index'])
                bndbox = ET.SubElement(obj, 'bndbox')
                ET.SubElement(bndbox, 'xmin').text = str(int(r.x()*img_w))
                ET.SubElement(bndbox, 'ymin').text = str(int(r.y()*img_h))
                ET.SubElement(bndbox, 'xmax').text = str(int((r.x()+r.width())*img_w))
                ET.SubElement(bndbox, 'ymax').text = str(int((r.y()+r.height())*img_h))
            xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
            with open(xml_path, "w", encoding='utf-8') as f: f.write(xmlstr)

        elif fmt == self.FORMAT_COCO_JSON:
            json_path = os.path.join(out_dir, "export_coco.json")
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f: data = json.load(f)
            else:
                data = {"images": [], "annotations": [], "categories": []}
                for i, c in enumerate(self.class_data):
                    data['categories'].append({"id": i+1, "name": c['name']})
            img_id = len(data['images']) + 1 
            data['images'].append({"id": img_id, "file_name": filename, "width": img_w, "height": img_h})
            ann_id_start = len(data['annotations']) + 1
            for i, s in enumerate(shapes):
                name = self.get_class_name(s['class_index'])
                cat_id = next((c['id'] for c in data['categories'] if c['name'] == name), 1)
                r = s['rect']
                x, y, w, h = r.x()*img_w, r.y()*img_h, r.width()*img_w, r.height()*img_h
                data['annotations'].append({
                    "id": ann_id_start + i,
                    "image_id": img_id,
                    "category_id": cat_id,
                    "bbox": [x, y, w, h],
                    "area": w*h,
                    "iscrowd": 0
                })
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f)


    # ==========================
    # Logic: Core
    # ==========================

    def open_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择图片目录")
        if dir_path:
            self.current_dir = dir_path
            self.img_dir_edit.setText(dir_path) 
            parent_dir = os.path.dirname(dir_path)
            default_label_dir = os.path.join(parent_dir, "labels")
            self.output_dir_edit.setText(default_label_dir)
            if not os.path.exists(default_label_dir):
                try: os.makedirs(default_label_dir)
                except: pass
            self.refresh_file_table()
            self.load_classes()

    def select_output_dir(self):
        old_dir = self.output_dir_edit.text()
        d = QFileDialog.getExistingDirectory(self, "选择标签目录", old_dir)
        if d and d != old_dir: 
            # v0.5.2: Auto-migrate class definitions
            import shutil
            try:
                if old_dir and os.path.exists(old_dir):
                    src_json = os.path.join(old_dir, "classes.json")
                    src_txt = os.path.join(old_dir, "classes.txt")
                    dst_json = os.path.join(d, "classes.json")
                    dst_txt = os.path.join(d, "classes.txt")
                    
                    if os.path.exists(src_json) and not os.path.exists(dst_json):
                        shutil.copy2(src_json, dst_json)
                    if os.path.exists(src_txt) and not os.path.exists(dst_txt):
                        shutil.copy2(src_txt, dst_txt)
            except Exception as e:
                print(f"Auto-migrate classes failed: {e}")

            self.output_dir_edit.setText(d)
            self.load_classes()
            
            # v0.5.2: Auto-refresh annotations for current image after changing label dir
            if self.current_image_path:
                filename = os.path.basename(self.current_image_path)
                # clear coco cache if directory changed (as it might be a different dataset context)
                self.coco_data = None 
                self.load_current_annotations(filename)
                self.refresh_annotation_table()

    def refresh_file_table(self):
        self.file_table.setSortingEnabled(False)
        self.file_table.setRowCount(0)
        exts = ('.jpg', '.jpeg', '.png', '.bmp')
        if hasattr(self, 'current_dir'):
            files = sorted([f for f in os.listdir(self.current_dir) if f.lower().endswith(exts)])
            self.file_table.setRowCount(len(files))
            for i, f in enumerate(files):
                item_name = QTableWidgetItem(f)
                self.file_table.setItem(i, 0, item_name)
                
                full_path = os.path.join(self.current_dir, f)
                ts = datetime.fromtimestamp(os.path.getmtime(full_path)).strftime("%Y-%m-%d %H:%M")
                item_time = QTableWidgetItem(ts)
                self.file_table.setItem(i, 1, item_time)
        
        self.apply_table_filters(self.file_table) # Re-apply filters
        self.file_table.setSortingEnabled(True)

    def load_classes(self):
        self.class_data = []
        self.class_table.setRowCount(0)
        out_dir = self.output_dir_edit.text()
        json_path = os.path.join(out_dir, "classes.json")
        txt_path = os.path.join(out_dir, "classes.txt")
        
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f: 
                    data = json.load(f)
                    # Support New Structure (Dict) vs Old Structure (List)
                    if isinstance(data, dict):
                        self.class_data = data.get('categories', [])
                        # We can load info if needed, but for now ignoring
                    elif isinstance(data, list):
                        self.class_data = data
            except: pass
            
        elif os.path.exists(txt_path):
            with open(txt_path, 'r', encoding='utf-8') as f:
                names = [l.strip() for l in f.readlines() if l.strip()]
                for n in names:
                    self.class_data.append({
                        "id": len(self.class_data),
                        "name": n, 
                        "color": [random.randint(50,255) for _ in range(3)], 
                        "updated_at": get_timestamp()
                    })
            self.save_classes_json()
        
        # Enforce ID consistency and missing attributes
        for i, c in enumerate(self.class_data):
            # ID sync with list index
            c['id'] = i 
            
            # Ensure name exists
            if 'name' not in c:
                c['name'] = f"Class_{i}"

            # Ensure color exists
            if 'color' not in c or not isinstance(c['color'], list) or len(c['color']) != 3:
                c['color'] = [random.randint(50, 255) for _ in range(3)]
                
            # Ensure timestamp
            if 'updated_at' not in c: 
                c['updated_at'] = get_timestamp()
            
        self.refresh_class_table()

    def save_classes_json(self):
        out_dir = self.output_dir_edit.text()
        if not out_dir: return
        if not os.path.exists(out_dir): os.makedirs(out_dir)
        
        # Enforce IDs before saving
        for i, c in enumerate(self.class_data):
            c['id'] = i
            
        # New Structure
        output_data = {
            "info": {
                "year": datetime.now().year,
                "version": APP_VERSION,
                "contributor": APP_NAME
            },
            "categories": self.class_data
        }
        
        with open(os.path.join(out_dir, "classes.json"), 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
            
        with open(os.path.join(out_dir, "classes.txt"), 'w', encoding='utf-8') as f:
            for cls in self.class_data:
                f.write(f"{cls['name']}\n")

    def refresh_class_table(self):
        # Disable sorting to populate table in strict List Order (0..N)
        self.class_table.setSortingEnabled(False)
        self.class_table.model().layoutAboutToBeChanged.emit() # Notify model about changes
        
        self.class_table.clearContents()
        # Explicitly reset row count to 0 to ensure all row states (hidden, height) are reset
        self.class_table.setRowCount(0)
        self.class_table.setRowCount(len(self.class_data))
        
        for i, cls in enumerate(self.class_data):
            # Column 0: ID (Color is in Delegate, not background role)
            item_id = QTableWidgetItem(str(i))
            item_id.setTextAlignment(Qt.AlignCenter) # type: ignore
            # Crucial: Store Real Index in UserRole for accurate lookups
            item_id.setData(Qt.UserRole, i) 
            
            # Text color logic for ID
            c = cls['color']
            # We use a delegate for rendering the ID cell background, 
            # but we set the text foreground here for contrast
            # Calculate luminance
            lum = c[0]*0.299 + c[1]*0.587 + c[2]*0.114
            if lum < 128: item_id.setForeground(QColor(255, 255, 255))
            else: item_id.setForeground(QColor(0, 0, 0))
            
            # Store Color in UserRole for the Delegate to access!
            # Using UserRole+1 for Color
            item_id.setData(Qt.UserRole + 1, QColor(*c))

            # Column 1: Name
            item_name = QTableWidgetItem(cls['name'])
            # Name column use default style (clear explicit colors)
            item_name.setBackground(QBrush()) # Clear background
            item_name.setForeground(QBrush()) # Clear foreground (use QSS default)

            self.class_table.setItem(i, 0, item_id)
            self.class_table.setItem(i, 1, item_name)
            self.class_table.setItem(i, 2, QTableWidgetItem(cls.get('updated_at', '')))
            
            # Ensure row is shown
            self.class_table.setRowHidden(i, False)

        if self.current_class_index != -1 and self.current_class_index < self.class_table.rowCount():
            # Select the row corresponding to current_class_index
            # Warning: If sorted, Row != Index. 
            # We need to find the row with UserRole == current_index.
            # But here sorting is Disabled, so Row == Index.
            self.class_table.selectRow(self.current_class_index)
        
        self.apply_table_filters(self.class_table)
        self.class_table.model().layoutChanged.emit() # Notify model layout changed
        self.class_table.setSortingEnabled(True)

    def show_class_context_menu(self, pos):
        menu = QMenu()
        
        # Check selection
        selected_rows = self.class_table.selectionModel().selectedRows()
        count = len(selected_rows)

        # v0.5.2: Add Select All
        sel_all_action = QAction("全选", self)
        sel_all_action.triggered.connect(self.class_table.selectAll)
        menu.addAction(sel_all_action)
        menu.addSeparator()
        
        item = self.class_table.itemAt(pos)
        idx = -1
        if item:
            item_id_cell = self.class_table.item(item.row(), 0)
            idx = item_id_cell.data(Qt.UserRole) if item_id_cell else -1 
        
        add_action = QAction("新建类别", self)
        add_action.triggered.connect(self.add_new_class_dialog) 
        menu.addAction(add_action)
        
        if count > 1:
             menu.addSeparator()
             del_all_action = QAction(f"删除选中 ({count})", self)
             del_all_action.triggered.connect(self.delete_selected_classes_logic)
             menu.addAction(del_all_action)
        elif idx != -1:
            menu.addSeparator()
            edit_action = QAction("修改名称", self)
            edit_action.triggered.connect(lambda: self.edit_class_name(idx))
            menu.addAction(edit_action)
            
            color_action = QAction("修改颜色", self)
            color_action.triggered.connect(lambda: self.edit_class_color(idx))
            menu.addAction(color_action)
            
            id_action = QAction("修改类别序号", self)
            id_action.triggered.connect(lambda: self.edit_class_id(idx))
            menu.addAction(id_action)
            
            del_action = QAction("删除类别", self)
            del_action.triggered.connect(lambda: self.delete_class_by_id(idx))
            menu.addAction(del_action)
            
        menu.exec_(self.class_table.mapToGlobal(pos))
        
    def delete_class_by_id(self, target_id):
        if not DarkDialogHelper.ask_yes_no(self, "确认删除", "删除此类别可能影响现有标注，确定吗？"):
            return
        self.class_data = [c for c in self.class_data if c['id'] != target_id]
        self.save_classes_json()
        self.refresh_class_table()
        self.current_class_index = -1


    # ==========================
    # Logic: Class ID Management
    # ==========================
    
    def edit_class_id(self, old_idx):
        new_id, ok = DarkDialogHelper.get_int(self, "修改类别序号", "输入新序号:", old_idx, 0, 999)
        if ok and new_id != old_idx:
            # 限制范围
            if new_id >= len(self.class_data): new_id = len(self.class_data) - 1
            if new_id < 0: new_id = 0
            
            # 如果目标ID已存在（且不是追加到末尾），询问策略
            if new_id < len(self.class_data):
                reply = DarkDialogHelper.ask_yes_no_cancel(self, "类别序号冲突", 
                    f"类别序号 {new_id} 已存在 ({self.class_data[new_id]['name']})。\n"
                    "选择【是】替换(交换)位置，选择【否】插入到该位置，【取消】放弃。")
                
                if reply == QMessageBox.Yes:
                    self.swap_class_ids(old_idx, new_id)
                elif reply == QMessageBox.No:
                    self.move_class_id(old_idx, new_id)
            else:
                self.move_class_id(old_idx, new_id)

    def _recursive_shift(self, current_idx, target_match_id, n_limit):
        """ 使用有限递归逻辑进行属性移动 """
        # 递归终止条件
        if current_idx >= n_limit:
            return n_limit
            
        current_id = -1
        if current_idx < len(self.class_data):
            current_id = self.class_data[current_idx].get('id', -1)
            
        # 找到目标 ID 或到达边界停止
        if current_id == target_match_id or current_idx == n_limit - 1:
            return current_idx

        # 向下递归
        stop_idx = self._recursive_shift(current_idx + 1, target_match_id, n_limit)
        
        # 回溯阶段：将属性从 Current 复制到 Current+1 (Shift Right)
        if current_idx + 1 < len(self.class_data):
            self.class_data[current_idx + 1] = self.class_data[current_idx]
            
        return stop_idx

    def swap_class_ids(self, idx1, idx2):
        if idx1 == idx2: return
        remap = {idx1: idx2, idx2: idx1}
        
        # 在 classes.json 中交换名称、颜色等所有非ID属性
        item1 = self.class_data[idx1]
        item2 = self.class_data[idx2]
        
        attrs1 = {k: v for k, v in item1.items() if k != 'id'}
        attrs2 = {k: v for k, v in item2.items() if k != 'id'}
        
        item1.update(attrs2)
        item2.update(attrs1)
        
        # ID 保持与索引一致
        item1['id'] = idx1
        item2['id'] = idx2
        item1['updated_at'] = get_timestamp()
        item2['updated_at'] = get_timestamp()
        
        self._apply_id_remapping(remap)
        self.save_classes_json()
        self.load_classes() 
        self.refresh_annotation_table()
        self.canvas.update()

    def move_class_id(self, from_idx, to_idx):
        """ 
        移动类别序号 (使用列表标准操作修复 v0.5.0 的递归bug)
        """
        if from_idx == to_idx: return
        n = len(self.class_data)
        if not (0 <= from_idx < n): return
        
        # 调整目标索引（因为移除元素后，后续元素索引会前移）
        target_idx = to_idx
        if target_idx > from_idx:
            target_idx -= 1
            
        if target_idx < 0: target_idx = 0
        if target_idx > n - 1: target_idx = n - 1

        # 移动元素
        item = self.class_data.pop(from_idx)
        self.class_data.insert(target_idx, item)

        # 3. 检查连贯性并重新进行ID复制 (从0开始)
        # 生成 ID 映射表用于更新文件
        new_map = {}
        for i, item in enumerate(self.class_data):
            old_id = item.get('id', -1)
            # 如果 ID 发生变化（位置改变必然导致ID重新分配）
            if old_id != -1 and old_id != i:
                new_map[old_id] = i
            item['id'] = i
            item['updated_at'] = get_timestamp()

        # 更新 classes.txt 和 classes.json 由 save_classes_json 处理
        # 更新标注文件中的 ID
        self._apply_id_remapping(new_map)

        # 4. 刷新列表显示
        self.save_classes_json() 
        self.load_classes() 
        self.refresh_annotation_table()
        self.canvas.update()

    def _apply_id_remapping(self, remap_dict):
        """ 辅助函数：将 remap_dict 应用于当前画布上的所有形状 """
        if not remap_dict: return
        shapes = self.canvas.get_shapes()
        changed = False
        for s in shapes:
            old_c = s['class_index']
            if old_c in remap_dict:
                s['class_index'] = remap_dict[old_c]
                changed = True
        
        # 如果有变化，保存当前图片的标注文件
        if changed:
            self.save_current_annotations()
    # ==========================
    # Logic: Class CRUD
    # ==========================

    def add_new_class_dialog(self):
        existing_names = [c['name'] for c in self.class_data]
        name, ok = DarkDialogHelper.get_item(self, "选择/新建类别", "类别名称:", existing_names, 0, editable=True)
        if ok and name:
            name = name.strip()
            if not name: return -1
            for i, cls in enumerate(self.class_data):
                if cls['name'] == name:
                    return i
            color = DarkDialogHelper.get_color(self)
            if color.isValid():
                self.class_data.append({"id": len(self.class_data),
                                        "name": name, 
                                        "color": [color.red(), color.green(), color.blue()],
                                        "updated_at": get_timestamp()})
                self.save_classes_json()
                self.refresh_class_table()
                return len(self.class_data) - 1 
        return -1

    def edit_class_name(self, idx):
        old_name = self.class_data[idx]['name']
        name, ok = DarkDialogHelper.get_text(self, "修改名称", "新名称:", text=old_name)
        if ok and name:
            self.class_data[idx]['name'] = name
            self.class_data[idx]['updated_at'] = get_timestamp()
            self.save_classes_json()
            self.refresh_class_table()
            self.canvas.update()
            self.refresh_annotation_table()

    def edit_class_color(self, idx):
        old_c = self.class_data[idx]['color']
        color = DarkDialogHelper.get_color(self, initial=QColor(*old_c))
        if color.isValid():
            self.class_data[idx]['color'] = [color.red(), color.green(), color.blue()]
            self.class_data[idx]['updated_at'] = get_timestamp()
            self.save_classes_json()
            self.refresh_class_table()
            self.canvas.update()

    def delete_class(self, idx):
        if DarkDialogHelper.ask_yes_no(self, "确认删除", "删除此类别可能影响现有标注，确定吗？"):
            self.class_data.pop(idx)
            self.save_classes_json()
            self.refresh_class_table()
            self.current_class_index = -1

    def save_classes_json(self):
        out_dir = self.output_dir_edit.text()
        if not out_dir: return
        if not os.path.exists(out_dir): os.makedirs(out_dir)
        with open(os.path.join(out_dir, "classes.json"), 'w', encoding='utf-8') as f:
            json.dump(self.class_data, f, indent=2, ensure_ascii=False)
        with open(os.path.join(out_dir, "classes.txt"), 'w', encoding='utf-8') as f:
            for cls in self.class_data:
                f.write(f"{cls['name']}\n")

    def on_category_clicked(self, item):
        # 获取该行对应的真实 Class Index (Data Index)
        row = item.row()
        item_id_cell = self.class_table.item(row, 0)
        idx = item_id_cell.data(Qt.UserRole) if item_id_cell else -1 
        
        if idx == -1: return

        # 检查选中状态来更新 current_index
        # 多选模式下，QTableWidget 已经处理了选中状态的变化
        # 我们只需要同步 current_class_index
        if item.isSelected():
            self.current_class_index = idx
        else:
            # 如果这是当前选中的类，且被取消选中了
            if self.current_class_index == idx:
                self.current_class_index = -1
                # 尝试找其他选中的行作为 current?
                selected = self.class_table.selectedItems()
                if selected:
                     other_item = self.class_table.item(selected[0].row(), 0)
                     if other_item:
                         self.current_class_index = int(other_item.data(Qt.UserRole))

    # ==========================
    # Logic: Annotation & Files
    # ==========================

    def on_file_clicked(self, item):
        if not item: return
        row = item.row()
        name_item = self.file_table.item(row, 0)
        if name_item:
            filename = name_item.text()
            self.load_image(filename)

    def change_image(self, delta):
        # 注意: 过滤后行数减少，逻辑需要支持
        count = self.file_table.rowCount()
        # count 只包含筛选后显示的行吗? 不是，rowCount是所有行，只是部分隐藏
        # 所以我们需要找到 visible rows
        
        visible_rows = [r for r in range(count) if not self.file_table.isRowHidden(r)]
        if not visible_rows: return
        
        curr_items = self.file_table.selectedItems()
        curr_row = curr_items[0].row() if curr_items else -1
        
        # Find index in visible list
        try:
            current_vis_idx = visible_rows.index(curr_row)
        except ValueError:
            current_vis_idx = -1
            
        if current_vis_idx == -1 and visible_rows:
            next_vis_idx = 0
        else:
            next_vis_idx = current_vis_idx + delta
            
        if 0 <= next_vis_idx < len(visible_rows):
            next_row = visible_rows[next_vis_idx]
            self.file_table.selectRow(next_row)
            name_item = self.file_table.item(next_row, 0)
            if name_item:
                filename = name_item.text()
                self.load_image(filename)
        else:
            DarkDialogHelper.show_info(self, "提示", "已经是第一张或最后一张了。")

    def load_image(self, filename):
        if not self.current_dir: return
        
        # 1. 记录 VIEW 并在操作池中隔离文件环境
        log_action = BaseAction(f"切换并载入图像: {filename}", level=ActionLevel.VIEW)
        self.action_pool.switch_context(filename)
        self.action_pool.execute(log_action)

        self.current_image_path = os.path.join(self.current_dir, filename)
        self.lbl_current_file.setText(filename)
        pixmap = QPixmap(self.current_image_path)
        self.canvas.set_pixmap(pixmap)
        self.load_current_annotations(filename)
        self.refresh_annotation_table()

    def load_current_annotations(self, filename):
        if not filename: 
            self.canvas.set_shapes([])
            return
        # v0.5.2: Ensure we load based on the current label directory's context
        shapes = self._load_shapes_headless(filename, self.current_format, root_dir_override=self.output_dir_edit.text())
        self.canvas.set_shapes(shapes)

    def add_new_shape(self, rect_normalized):
        cls_idx = self.current_class_index
        if cls_idx == -1:
            new_idx = self.add_new_class_dialog()
            if new_idx != -1:
                cls_idx = new_idx
                self.current_class_index = new_idx
                self.class_table.selectRow(new_idx)
            else:
                return 

        shape_data = {'class_index': cls_idx, 'rect': rect_normalized, 'updated_at': get_timestamp()}
        action = AddShapeAction(self, shape_data)
        self.action_pool.execute(action)

    def remove_shape(self, index):
        if 0 <= index < len(self.canvas._shapes):
            self.canvas._shapes.pop(index)
            self.save_current_annotations()
            self.refresh_annotation_table()
            self.canvas.selected_shape_index = -1
            self.canvas.update()

    def save_current_annotations(self, format_override=None):
        if not self.current_image_path: return
        fmt = format_override or self.current_format
        
        # v0.5.2: COCO Runtime Memory Optimization
        if fmt == self.FORMAT_COCO_JSON and hasattr(self, 'coco_data') and self.coco_data:
             self._update_coco_memory_and_save(self.canvas.get_shapes(), os.path.basename(self.current_image_path))
             return

        self._save_shapes_headless(self.canvas.get_shapes(), os.path.basename(self.current_image_path), fmt, self.output_dir_edit.text())

    def _update_coco_memory_and_save(self, shapes, filename):
        # 1. Ensure categories exist in COCO data
        cat_name_to_id = {}
        processed_coco_cats = self.coco_data.get('categories', [])
        
        # Sync categories if needed
        existing_coco_names = {c['name']: c['id'] for c in processed_coco_cats}
        next_cat_id = max(existing_coco_names.values()) + 1 if existing_coco_names else 1
        
        for app_cat in self.class_data:
            cname = app_cat['name']
            if cname in existing_coco_names:
                cat_name_to_id[cname] = existing_coco_names[cname]
            else:
                new_entry = {"id": next_cat_id, "name": cname, "supercategory": "none"}
                self.coco_data.setdefault('categories', []).append(new_entry)
                cat_name_to_id[cname] = next_cat_id
                next_cat_id += 1

        # 2. Find or Create Image Entry
        img_entry = None
        if hasattr(self, 'coco_images_map'):
            img_entry = self.coco_images_map.get(filename)
        
        if not img_entry:
            # Create new
            img_id = 1
            images = self.coco_data.get('images', [])
            if images: img_id = max(i['id'] for i in images) + 1
            
            w, h = self.canvas.get_img_dims()
            img_entry = {"id": img_id, "file_name": filename, "width": w, "height": h}
            self.coco_data.setdefault('images', []).append(img_entry)
            
            if hasattr(self, 'coco_images_map'):
                self.coco_images_map[filename] = img_entry
        
        img_id = img_entry['id']
        w, h = img_entry['width'], img_entry['height']
        if w == 0 or h == 0:
             w, h = self.canvas.get_img_dims()
             img_entry['width'] = w
             img_entry['height'] = h

        # 3. Remove old annotations for this image
        # Using a reconstruction list approach is safer than removing from list while iterating
        if hasattr(self, 'coco_anns_map'):
            old_anns = self.coco_anns_map.get(img_id, [])
            # Only need to remove these specific objects from the main list. 
            # Since main list is large, this is the bottleneck.
            # Optimization: If we trust our map, we can filter.
            # But filtering the whole 100k list is slow.
            # Lazy approach: Allow 'zombie' annotations? No, file size grows.
            # Best approach: list comprehension is fast in C.
            # Rebuild main list excluding current image_id
            self.coco_data['annotations'] = [a for a in self.coco_data.get('annotations', []) if a['image_id'] != img_id]
            self.coco_anns_map[img_id] = []
        else:
             self.coco_data['annotations'] = [a for a in self.coco_data.get('annotations', []) if a['image_id'] != img_id]

        # 4. Add new annotations
        next_ann_id = 1
        anns = self.coco_data.get('annotations', [])
        if anns:
             # This max() over large list is also slow. 
             # Optimization: Cached max_id?
             # For safety, let's max. If too slow, we can optimize later.
             next_ann_id = max(a['id'] for a in anns) + 1
        
        new_anns = []
        for i, s in enumerate(shapes):
            cname = self.get_class_name(s['class_index'])
            cid = cat_name_to_id.get(cname, 1)
            r = s['rect']
            
            # Format: [x, y, w, h] (Absolute)
            bx, by, bw, bh = r.x()*w, r.y()*h, r.width()*w, r.height()*h
            
            ann = {
                "id": next_ann_id + i,
                "image_id": img_id,
                "category_id": cid,
                "bbox": [bx, by, bw, bh],
                "area": bw * bh,
                "iscrowd": 0,
                "segmentation": [] # Bbox only support
            }
            new_anns.append(ann)
        
        self.coco_data['annotations'].extend(new_anns)
        
        # update index
        if hasattr(self, 'coco_anns_map'):
            self.coco_anns_map[img_id] = new_anns

        # 5. Save to disk (Dump)
        out_dir = self.output_dir_edit.text()
        if out_dir:
            path = os.path.join(out_dir, "export_coco.json")
            # This write might be slow for 100MB+ files.
            # User warning? No, just do it.
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.coco_data, f, ensure_ascii=False)

    def refresh_annotation_table(self):
        self.annotation_table.setSortingEnabled(False)
        self.annotation_table.setRowCount(len(self.canvas.get_shapes()))
        
        for i, shape in enumerate(self.canvas.get_shapes()):
            cls_idx = shape['class_index']
            self.annotation_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.annotation_table.setItem(i, 1, QTableWidgetItem(str(cls_idx)))
            name = self.get_class_name(cls_idx)
            self.annotation_table.setItem(i, 2, QTableWidgetItem(name))
            time_str = shape.get('updated_at', 'None')
            self.annotation_table.setItem(i, 3, QTableWidgetItem(time_str))

        self.apply_table_filters(self.annotation_table)
        self.annotation_table.setSortingEnabled(True)

    def on_annotation_item_clicked(self, item):
        idx = item.row()
        id_item = self.annotation_table.item(idx, 0)
        if id_item:
             real_idx = int(id_item.text()) - 1
             self.canvas.selected_shape_index = real_idx
             self.canvas.update()

    # v0.5.2: Removed legacy show_annotation_context_menu (shadowed by new version below)


    def modify_selected_annotations_class(self, indices=None):
        if not indices: return
        
        # Get existing class names
        existing_names = [c['name'] for c in self.class_data]
        
        # Determine initial selection
        current_name = ""
        if len(indices) == 1:
            idx = indices[0]
            current_shapes = self.canvas.get_shapes()
            if 0 <= idx < len(current_shapes):
                cls_idx = current_shapes[idx]['class_index']
                current_name = self.get_class_name(cls_idx)
        
        # Determine dropdown default index
        default_idx = 0
        if current_name and current_name in existing_names:
            default_idx = existing_names.index(current_name)
            
        name, ok = DarkDialogHelper.get_item(self, "修改类别", "选择或输入新类别:", existing_names, default_idx, editable=True)
        
        if ok and name:
            name = name.strip()
            if not name: return

            new_cls_idx = -1
            for i, cls in enumerate(self.class_data):
                if cls['name'] == name:
                    new_cls_idx = i
                    break
            
            if new_cls_idx == -1:
                color = DarkDialogHelper.get_color(self)
                if color.isValid():
                    self.class_data.append({"id": len(self.class_data),
                                            "name": name, 
                                            "color": [color.red(), color.green(), color.blue()],
                                            "updated_at": get_timestamp()})
                    self.save_classes_json()
                    self.refresh_class_table()
                    new_cls_idx = len(self.class_data) - 1
                else: return 

            if new_cls_idx != -1:
                current_shapes = self.canvas.get_shapes()
                changed = False
                ts = get_timestamp()
                
                for idx in indices:
                    if 0 <= idx < len(current_shapes):
                        current_shapes[idx]['class_index'] = new_cls_idx
                        current_shapes[idx]['updated_at'] = ts
                        changed = True
                
                if changed:
                    self.save_current_annotations()
                    self.refresh_annotation_table()
                    self.canvas.update()
                    # Restore selection
                    self.canvas.selected_indices = set(indices)
                    self.sync_list_selection_from_canvas()
    
    def highlight_annotation_in_list(self, idx):
        # Iterate rows (checking visible logic?)
        # Just select if found
        for r in range(self.annotation_table.rowCount()):
             item = self.annotation_table.item(r, 0)
             if item and int(item.text()) == idx:
                 self.annotation_table.selectRow(r)
                 break

    def get_class_color(self, idx):
        if 0 <= idx < len(self.class_data):
            return self.class_data[idx]['color']
        return [255, 255, 255] 

    def get_class_name(self, idx):
        if 0 <= idx < len(self.class_data):
            return self.class_data[idx]['name']
        return str(idx)

    def _ensure_coco_loaded(self):
         out_dir = self.output_dir_edit.text()
         if not out_dir: return
         
         # 优先查找 export_coco.json，其次 annotations.json
         # v0.5.2: Support export_coco.json and build optimized indices
         candidates = ["export_coco.json", "annotations.json"]
         found_path = None
         for c in candidates:
             p = os.path.join(out_dir, c)
             if os.path.exists(p):
                 found_path = p
                 break

         if not self.coco_data and found_path:
             try:
                 with open(found_path, 'r', encoding='utf-8') as f: 
                    self.coco_data = json.load(f)
                 # 建立加速索引
                 self.coco_images_map = {img['file_name']: img for img in self.coco_data.get('images', [])}
                 self.coco_anns_map = {}
                 for ann in self.coco_data.get('annotations', []):
                     img_id = ann['image_id']
                     if img_id not in self.coco_anns_map: self.coco_anns_map[img_id] = []
                     self.coco_anns_map[img_id].append(ann)
             except Exception as e:
                 print(f"Error loading COCO: {e}") 

    def eventFilter(self, source, event):
        if event.type() == QEvent.KeyPress: # type: ignore
            if event.key() == Qt.Key_Delete: # type: ignore
                if source == self.class_table:
                    self.delete_selected_classes_logic()
                    return True
                elif source == self.annotation_table:
                    # Explicitly isolate: Delete in list only deletes in list (and syncs to canvas)
                    self.delete_selected_annotations()
                    return True
        return super().eventFilter(source, event)

    def delete_selected_classes_logic(self):
        selection = self.class_table.selectionModel().selectedRows()
        ids_to_delete = []
        for index in selection:
            item = self.class_table.item(index.row(), 0)
            if item:
                ids_to_delete.append(int(item.data(Qt.UserRole)))
        
        if not ids_to_delete: return
        
        if not DarkDialogHelper.ask_yes_no(self, "删除确认", f"确定删除选中的 {len(ids_to_delete)} 个类别吗？\n注意：这将永久删除文件夹中所有相关标注，并重排剩余类别ID！该操作不可逆。"):
             return

        # 1. Calculate ID Mapping (Old -> New)
        old_class_data = self.class_data[:]
        new_class_data = []
        id_map = {} 
        
        deleted_set = set(ids_to_delete)
        new_idx_counter = 0
        for old_c in old_class_data:
            old_id = old_c['id']
            if old_id in deleted_set:
                id_map[old_id] = -1 # Delete
            else:
                id_map[old_id] = new_idx_counter
                # Update internal ID
                c_copy = old_c.copy()
                c_copy['id'] = new_idx_counter
                new_class_data.append(c_copy)
                new_idx_counter += 1

        # 2. Process Files (Batch)
        current_fmt = self.current_format
        root_dir = self.output_dir_edit.text()
        
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if current_fmt == self.FORMAT_COCO_JSON:
                 self._delete_classes_coco(deleted_set)
            else:
                 self._delete_classes_per_file(id_map, old_class_data, new_class_data, root_dir)

            # 3. Finalize
            self.class_data = new_class_data
            self.save_classes_json()
            self.refresh_class_table()
            self.current_class_index = -1
            
            # Refresh current canvas
            if self.current_image_path:
                filename = os.path.basename(self.current_image_path)
                self.load_current_annotations(filename)
                self.refresh_annotation_table()
                self.canvas.update()
                
        except Exception as e:
            QApplication.restoreOverrideCursor()
            DarkDialogHelper.show_critical(self, "错误", f"删除过程出错: {str(e)}")
            return
            
        QApplication.restoreOverrideCursor()
        DarkDialogHelper.show_info(self, "完成", "类别及对应标注删除完成。")

    def _delete_classes_per_file(self, id_map, old_data, new_data, root_dir):
        # Scan all files
        total_rows = self.file_table.rowCount()
        files = []
        for r in range(total_rows):
            item = self.file_table.item(r, 0)
            if item: files.append(item.text())
            
        for f in files:
            # Load with OLD context (implicitly uses self.class_data which is still old_data)
            shapes = self._load_shapes_headless(f, self.current_format, root_dir_override=root_dir)
            
            new_shapes = []
            changed = False
            for s in shapes:
                old_id = s['class_index']
                target_id = id_map.get(old_id, old_id)
                
                if target_id == -1:
                    changed = True # Delete this shape
                    continue
                
                if target_id != old_id:
                    s['class_index'] = target_id
                    changed = True
                new_shapes.append(s)
            
            if changed:
                # Context Switch for Save (VOC needs New Names)
                self.class_data = new_data
                try:
                    self._save_shapes_headless(new_shapes, f, self.current_format, root_dir)
                finally:
                    self.class_data = old_data # Restore

    def _delete_classes_coco(self, deleted_ids):
        if not self.coco_data: self._ensure_coco_loaded()
        if not self.coco_data: return
        
        # 1. Identify Names to delete
        names_to_delete = set()
        for c in self.class_data:
            if c['id'] in deleted_ids:
                names_to_delete.add(c['name'])
        
        # 2. Filter COCO Categories
        cats = self.coco_data.get('categories', [])
        valid_cats = []
        chk_del_cat_ids = set()
        
        for c in cats:
            if c['name'] in names_to_delete:
                chk_del_cat_ids.add(c['id'])
            else:
                valid_cats.append(c)
        self.coco_data['categories'] = valid_cats
        
        # 3. Filter Annotations
        old_anns = self.coco_data.get('annotations', [])
        new_anns = [a for a in old_anns if a['category_id'] not in chk_del_cat_ids]
        self.coco_data['annotations'] = new_anns
        
        # 4. Rebuild Map
        if hasattr(self, 'coco_anns_map'):
             self.coco_anns_map = {}
             for ann in new_anns:
                 iid = ann['image_id']
                 if iid not in self.coco_anns_map: self.coco_anns_map[iid] = []
                 self.coco_anns_map[iid].append(ann)
                 
        # 5. Save
        out_dir = self.output_dir_edit.text()
        if out_dir:
            path = os.path.join(out_dir, "export_coco.json")
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.coco_data, f, ensure_ascii=False)

    def on_class_selection_changed(self):
        pass

    def prepare_drawing_class_selection(self):
        """如果在多选类别状态下开始画框，自动切换为只选中最后点击的那个"""
        selected_rows = [i.row() for i in self.class_table.selectionModel().selectedRows()]
        if len(selected_rows) > 1:
            current = self.class_table.currentRow()
            if current != -1:
                # 只保留当前行选中
                self.class_table.setSelectionMode(QAbstractItemView.SingleSelection)
                self.class_table.selectRow(current)
                self.class_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
                
                item = self.class_table.item(current, 0)
                if item:
                    # Update current class index context
                    idx = int(item.data(Qt.UserRole))
                    self.current_class_index = idx

    def sync_canvas_selection_from_list(self):
        """标注列表 -> 画布"""
        selected_rows = [i.row() for i in self.annotation_table.selectionModel().selectedRows()]
        indices = set()
        for r in selected_rows:
            item = self.annotation_table.item(r, 0)
            if item:
                try:
                    val = int(item.text()) - 1
                    indices.add(val)
                except:
                    pass
        
        self.canvas.selected_indices = indices
        self.canvas.update()

    def sync_list_selection_from_canvas(self):
        """画布 -> 标注列表"""
        indices = self.canvas.selected_indices
        self.annotation_table.blockSignals(True)
        self.annotation_table.clearSelection()
        
        for i in indices:
            target_text = str(i + 1)
            items = self.annotation_table.findItems(target_text, Qt.MatchExactly)
            for item in items:
                if item.column() == 0:
                    self.annotation_table.selectRow(item.row())
                    
        self.annotation_table.blockSignals(False)

    def show_annotation_context_menu(self, pos, from_canvas=False):
        if from_canvas:
            indices = list(self.canvas.selected_indices)
        else:
            rows = [i.row() for i in self.annotation_table.selectionModel().selectedRows()]
            indices = []
            for r in rows:
                item = self.annotation_table.item(r, 0)
                if item and item.text().isdigit(): 
                    indices.append(int(item.text()) - 1)
        
        menu = QMenu(self)
        
        # v0.5.2: Modify Class
        if indices:
            act_modify = menu.addAction("修改类别...")
            act_modify.triggered.connect(lambda: self.modify_selected_annotations_class(indices))
            menu.addSeparator()
        
        # Copy/Cut
        if indices:
            act_copy = menu.addAction("复制 (Ctrl+C)")
            act_copy.triggered.connect(self.copy_annotations)
            act_cut = menu.addAction("剪切 (Ctrl+X)")
            act_cut.triggered.connect(self.cut_annotations)
        
        # Paste
        clipboard = QApplication.clipboard()
        if clipboard.mimeData().hasText():
            act_paste = menu.addAction("粘贴 (Ctrl+V)")
            act_paste.triggered.connect(self.paste_annotations)
            
        menu.addSeparator()

        # v0.5.2: Select All
        act_all = menu.addAction("全选 (Ctrl+A)")
        act_all.triggered.connect(self.annotation_table.selectAll)

        if indices:
            act_del = menu.addAction("删除选中")
            act_del.setShortcut("Delete")
            act_del.triggered.connect(self.delete_selected_annotations)
        
        menu.exec_(pos)

    def copy_annotations(self):
        self._copy_cut_logic(is_cut=False)

    def cut_annotations(self):
        self._copy_cut_logic(is_cut=True)

    def _copy_cut_logic(self, is_cut):
        indices = sorted(list(self.canvas.selected_indices))
        if not indices: return
        
        shapes = self.canvas.get_shapes()
        export_data = []
        
        for i in indices:
            if i < 0 or i >= len(shapes): continue
            s = shapes[i]
            rect = s['rect']
            cls = s['class_index']
            cx = rect.x() + rect.width()/2
            cy = rect.y() + rect.height()/2
            line = f"{cls} {cx:.6f} {cy:.6f} {rect.width():.6f} {rect.height():.6f}"
            export_data.append(line)
        
        text_data = "\n".join(export_data)
        QApplication.clipboard().setText(text_data)
        
        if is_cut:
            self.delete_selected_annotations()

    def paste_annotations(self):
        clipboard = QApplication.clipboard()
        if not clipboard.mimeData().hasText(): return
        
        text = clipboard.text()
        lines = text.strip().split('\n')
        new_shapes = []
        current_ts = get_timestamp()
        
        for line in lines:
            parts = line.split()
            if len(parts) >= 5:
                try:
                    cls_id = int(parts[0])
                    cx = float(parts[1])
                    cy = float(parts[2])
                    w = float(parts[3])
                    h = float(parts[4])
                    x = cx - w/2
                    y = cy - h/2
                    rect = QRectF(x, y, w, h)
                    
                    if 0 <= cls_id < len(self.class_data):
                        new_shapes.append({
                            "class_index": cls_id,
                            "rect": rect,
                            "created_at": current_ts,
                            "updated_at": current_ts
                        })
                except:
                    pass
        
        if new_shapes:
            current_shapes = self.canvas.get_shapes()
            current_shapes.extend(new_shapes)
            self.canvas.set_shapes(current_shapes)
            self.save_current_annotations(format_override=None)
            self.refresh_annotation_table()
            
            total = len(current_shapes)
            added = len(new_shapes)
            self.canvas.selected_indices = set(range(total - added, total))
            self.sync_list_selection_from_canvas()

    def delete_selected_annotations(self):
        indices = sorted(list(self.canvas.selected_indices), reverse=True)
        if not indices: return
        
        action = DeleteShapesAction(self, list(self.canvas.selected_indices))
        self.action_pool.execute(action)

    def keyPressEvent(self, event):
        modifiers = event.modifiers()
        key = event.key()
        
        # Check if a text input widget is focused to avoid conflicts
        in_text_input = isinstance(self.focusWidget(), (QLineEdit, QTextEdit))

        # v0.5.2: Global Delete Shortcut (Context Isolated)
        if key == Qt.Key_Delete and not in_text_input:
            self.delete_selected_annotations()

        elif modifiers & Qt.ControlModifier:
            if key == Qt.Key_C and not in_text_input:
                self.copy_annotations()
            elif key == Qt.Key_X and not in_text_input:
                self.cut_annotations()
            elif key == Qt.Key_V and not in_text_input:
                self.paste_annotations()
            elif key == Qt.Key_A and not in_text_input:
                count = len(self.canvas.get_shapes())
                self.canvas.selected_indices = set(range(count))
                self.sync_list_selection_from_canvas()
                self.canvas.update()
            elif key == Qt.Key_Z and not in_text_input:
                self.action_pool.undo()
            elif key == Qt.Key_Y and not in_text_input:
                self.action_pool.redo()
                
        elif key == Qt.Key_Left and not in_text_input:
            self.change_image(-1)
        elif key == Qt.Key_Right and not in_text_input:
            self.change_image(1)
# QSS
# ============================================
QSS_STYLE = """
/* 全局样式 */
QWidget { 
    color: #e0e0e0; 
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif; 
    font-size: 14px; 
}
QMainWindow { 
    background-color: #1e1e1e; 
}

/* 分组框 */
QGroupBox { 
    border: 1px solid #3e3e42; 
    border-radius: 6px; 
    margin-top: 24px; 
    font-weight: bold; 
    background-color: #252526; 
}
QGroupBox::title { 
    subcontrol-origin: margin; 
    subcontrol-position: top left; 
    left: 12px; 
    padding: 0 4px; 
    color: #007acc; 
}

/* 按钮通用 */
QPushButton { 
    border: 1px solid #3e3e42; 
    border-radius: 4px; 
    background-color: #333333; 
    padding: 6px 12px; 
    min-height: 24px;
    color: #f0f0f0;
}
QPushButton:hover { 
    background-color: #3e3e42; 
    border-color: #007acc; 
}
QPushButton:pressed { 
    background-color: #007acc;
    color: #ffffff;
    border-color: #007acc;
}
QPushButton:disabled { 
    background-color: #252526; 
    color: #6d6d6d; 
    border-color: #2d2d30; 
}

/* 删除按钮特定样式 */
QPushButton#removeButton {
    background-color: #c0392b; 
    border: none; 
    border-radius: 4px; 
}
QPushButton#removeButton:hover {
    background-color: #e74c3c;
}

/* 输入控件 */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateTimeEdit { 
    border: 1px solid #3e3e42; 
    border-radius: 2px; 
    padding: 4px; 
    background-color: #252526; 
    color: #cccccc; 
    selection-background-color: #264f78; 
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QDateTimeEdit:focus { 
    border: 1px solid #007acc; 
}

/* 下拉框 */
QComboBox::drop-down { 
    subcontrol-origin: padding; 
    subcontrol-position: top right; 
    width: 20px; 
    border-left-width: 0px;
    background-color: transparent; 
}
QComboBox QAbstractItemView { 
    background-color: #1f1f1f; 
    color: #cccccc; 
    selection-background-color: #3e3e42; 
    border: 1px solid #3e3e42; 
}

/* 列表与表格 */
QListWidget, QTableWidget { 
    background-color: #1e1e1e; 
    border: 1px solid #3e3e42; 
    border-radius: 4px; 
    alternate-background-color: #252526; 
    gridline-color: #333333; 
    selection-background-color: #094771; 
    selection-color: #ffffff;
}
QListWidget::item:selected, QTableWidget::item:selected { 
    background-color: #094771; 
    color: white; 
}
QListWidget::item:hover, QTableWidget::item:hover {
    background-color: #2a2d2e;
}

/* 表头 */
QHeaderView { 
    background-color: #252526; 
    border: none;
}
QHeaderView::section { 
    background-color: #252526; 
    color: #cccccc; 
    padding: 6px 4px; 
    border: none; 
    border-right: 1px solid #3e3e42; 
    border-bottom: 1px solid #3e3e42;
}
QTableCornerButton::section { 
    background-color: #252526; 
    border: 1px solid #3e3e42; 
}

/* 自定义标签 */
QLabel[class="sectionTitle"] { 
    font-size: 16px; 
    font-weight: bold; 
    color: #ffffff; 
    padding-bottom: 6px; 
    border-bottom: 2px solid #007acc; 
    margin-bottom: 12px; 
}

/* 分割线 */
QSplitter::handle { 
    background-color: #3e3e42; 
    width: 1px; 
}

/* 工具提示 */
QToolTip { 
    border: 1px solid #454545; 
    background-color: #252526; 
    color: #cccccc; 
    padding: 4px; 
}

/* 菜单 */
QMenu { 
    background-color: #1f1f1f; 
    border: 1px solid #454545; 
    padding: 4px;
}
QMenu::item { 
    padding: 6px 28px 6px 28px; 
    color: #cccccc; 
    background-color: transparent; 
}
QMenu::item:selected { 
    background-color: #094771; 
    color: #ffffff; 
}
QMenu::separator { 
    height: 1px; 
    background: #454545; 
    margin: 4px 10px; 
}

/* 消息框与对话框 */
QMessageBox, QDialog { 
    background-color: #1e1e1e; 
    color: #cccccc; 
}
QMessageBox QLabel { 
    color: #cccccc; 
}

/* 滚动条 */
QScrollBar:vertical { 
    border: none; 
    background: #1e1e1e; 
    width: 12px; 
    margin: 0px; 
}
QScrollBar::handle:vertical { 
    background: #424242; 
    min-height: 20px; 
    border-radius: 6px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover { 
    background: #4f4f4f; 
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { 
    height: 0px; 
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { 
    background: none; 
}

QScrollBar:horizontal { 
    border: none; 
    background: #1e1e1e; 
    height: 12px; 
    margin: 0px; 
}
QScrollBar::handle:horizontal { 
    background: #424242; 
    min-width: 20px; 
    border-radius: 6px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover { 
    background: #4f4f4f; 
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { 
    width: 0px; 
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { 
    background: none; 
}

/* 颜色选择器 */
QColorDialog { 
    background-color: #1e1e1e; 
    color: #cccccc; 
}

QScrollArea { 
    border: none; 
    background: transparent; 
}
QScrollArea > QWidget > QWidget { 
    background: transparent; 
}
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f" {APP_NAME_FULL} - v{APP_VERSION} ") 
        self.setMinimumSize(1100, 750)
        icon_names = ["app_icon.png", "app_icon.ico"]
        for name in icon_names:
            icon_path = resource_path(os.path.join("assets", name))
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
                break
        self.central_widget = AnnotationApp() 
        self.setCentralWidget(self.central_widget)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS_STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
