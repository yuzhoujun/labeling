"""
项目名称: 独立数据标注工具 (Labeling Tool)
版本: v0.1
开发环境: Python 3.9+ | PyQt5

功能说明:
    这是一个轻量级的 YOLO 数据集标注工具，独立于其他大型系统。
    主要功能包括:
    1. 基础标注: 支持加载图片文件夹，绘制矩形框，生成 YOLO 格式 (.txt) 标注文件。
    2. 类别管理: 简单的类别添加与删除功能。
    3. 自动保存: 实时保存标注结果。
    4. 界面风格: 基础深色主题支持。

使用说明:
    1. 运行: python labeling_app_v0.1.py
    2. 确保 assets 目录下有 app_icon.png 和 app_icon_colored.png。

打包指令:
    pyinstaller --noconsole --onefile --icon=assets/app_icon_colored.png --name="LabelingTool_v0.1" --add-data "assets;assets" labeling_app_v0.1.py
"""

import sys
import os
import json
import random
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QLineEdit, QFileDialog, 
                             QMessageBox, QSplitter, QListWidget, 
                             QFrame, QSizePolicy, QInputDialog, QMenu, QAction, QListWidgetItem, QColorDialog, QDialog)
from PyQt5.QtCore import Qt, QSize, QPoint, QPointF, QRectF, QRect, QEvent
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor, QPen

# ============================================
# 工具函数与类
# ============================================

def resource_path(relative_path):
    """ 获取资源的绝对路径，兼容 PyInstaller 打包 """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

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
        dialog = QInputDialog(parent)
        dialog.setWindowTitle(title)
        dialog.setLabelText(label)
        dialog.setComboBoxItems(items)
        dialog.setTextValue(items[current] if items else "")
        dialog.setComboBoxEditable(editable)
        dialog.setOkButtonText("确定")
        dialog.setCancelButtonText("取消")
        dialog.setStyleSheet(parent.styleSheet())
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
        self._start_pos = None
        self._scale = 1.0
        self._pan_x = 0
        self._pan_y = 0
        self._state = self.STATE_IDLE
        self._last_mouse_pos = None
        self.selected_shape_index = -1
        self._active_handle = None
        self._drag_start_rect = None # Normalized rect when drag started
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus) # type: ignore

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        self._shapes = []
        self._current_rect = None
        self._scale = 1.0
        self._pan_x = 0
        self._pan_y = 0
        self.selected_shape_index = -1
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
        
        # Calculate offset
        win_w, win_h = self.width(), self.height()
        base_scale = min(win_w / self._pixmap.width(), win_h / self._pixmap.height()) if self._pixmap.width() > 0 else 1.0
        final_scale = base_scale * self._scale
        
        # Recalculate true image dimensions on screen
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
        # Inverse of map_to_screen
        win_w, win_h = self.width(), self.height()
        if not self._pixmap: return 0.0, 0.0
        base_scale = min(win_w / self._pixmap.width(), win_h / self._pixmap.height())
        final_scale = base_scale * self._scale
        disp_w = int(self._pixmap.width() * final_scale)
        disp_h = int(self._pixmap.height() * final_scale)
        off_x = (win_w - disp_w) // 2 + self._pan_x
        off_y = (win_h - disp_h) // 2 + self._pan_y
        
        # 使用 QPointF 防止整数除法精度丢失
        nx = (point.x() - off_x) / disp_w
        ny = (point.y() - off_y) / disp_h
        return nx, ny

    def get_handle_at(self, pos, rect_screen):
        hs = self.HANDLE_SIZE
        x, y, w, h = rect_screen.x(), rect_screen.y(), rect_screen.width(), rect_screen.height()
        
        # Corners (use QPointF for precise float hit testing)
        if QRectF(x - hs/2, y - hs/2, hs, hs).contains(pos): return self.HANDLE_TOP_LEFT
        if QRectF(x + w - hs/2, y - hs/2, hs, hs).contains(pos): return self.HANDLE_TOP_RIGHT
        if QRectF(x - hs/2, y + h - hs/2, hs, hs).contains(pos): return self.HANDLE_BOTTOM_LEFT
        if QRectF(x + w - hs/2, y + h - hs/2, hs, hs).contains(pos): return self.HANDLE_BOTTOM_RIGHT
        
        # Edges
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

        # Common calc for offset
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
            
            is_selected = (i == self.selected_shape_index)
            pen_width = 3 if is_selected else 2
            painter.setPen(QPen(color, pen_width))
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 80 if is_selected else 0))
            painter.drawRect(screen_rect)
            
            # Label Text
            label_name = self.main_tab.get_class_name(cls_idx)
            fm = painter.fontMetrics()
            txt_w = fm.width(label_name) + 10
            txt_h = fm.height() + 4
            txt_bg_rect = QRectF(screen_rect.left(), screen_rect.top() - txt_h, txt_w, txt_h)
            painter.fillRect(txt_bg_rect, color)
            painter.setPen(QColor(255, 255, 255) if color.lightness() < 128 else QColor(0, 0, 0))
            painter.drawText(txt_bg_rect, Qt.AlignCenter, label_name) # type: ignore
            
            # Draw Handles if selected
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

        # Draw current drawing rect
        rect = self._current_rect
        if rect is not None:
            painter.setPen(QPen(QColor(255, 255, 255), 2, Qt.DashLine)) # type: ignore
            painter.setBrush(Qt.NoBrush) # type: ignore
            painter.drawRect(rect)

    def mousePressEvent(self, event):
        if not self._pixmap: return
        pos = event.localPos() # Use floating point localPos
        
        if event.button() == Qt.RightButton: # type: ignore
            # Right click logic
            # Check if clicked on a box first
            hit_shape = self.get_shape_at(pos)
            if hit_shape != -1:
                self.selected_shape_index = hit_shape
                self.update()
                # Show menu
                self.main_tab.show_annotation_context_menu(self.mapToGlobal(event.pos()), from_canvas=True)
            else:
                # Pan
                self._state = self.STATE_PANNING
                self._last_mouse_pos = pos
                self.setCursor(Qt.ClosedHandCursor) # type: ignore
            return

        if event.button() == Qt.LeftButton: # type: ignore
            # 1. Check handles of selected shape
            if self.selected_shape_index != -1:
                rect_norm = self._shapes[self.selected_shape_index]['rect']
                screen_rect = self.map_to_screen(rect_norm)
                handle = self.get_handle_at(pos, screen_rect)
                if handle:
                    self._state = self.STATE_RESIZING
                    self._active_handle = handle
                    self._drag_start_rect = rect_norm # Store normalized start rect
                    self._last_mouse_pos = pos
                    return
                
                # 2. Check interior of selected shape (Move)
                if screen_rect.contains(pos):
                    self._state = self.STATE_MOVING
                    self._drag_start_rect = rect_norm # Store normalized start rect
                    self._last_mouse_pos = pos
                    return

            # 3. Check other shapes to select
            hit_shape = self.get_shape_at(pos)
            if hit_shape != -1:
                self.selected_shape_index = hit_shape
                self.main_tab.highlight_annotation_in_list(hit_shape)
                self.update()
                self._state = self.STATE_MOVING
                self._drag_start_rect = self._shapes[hit_shape]['rect']
                self._last_mouse_pos = pos
            else:
                # 4. Start Drawing
                self.selected_shape_index = -1
                self.main_tab.annotation_list_widget.clearSelection()
                self._state = self.STATE_DRAWING
                self._start_pos = pos
                self._current_rect = QRectF(pos, pos)
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
            if self._start_pos:
                self._current_rect = QRectF(self._start_pos, pos).normalized()
                self.update()
                
        elif self._state == self.STATE_MOVING:
            if self.selected_shape_index != -1 and self._drag_start_rect:
                # Calculate delta in normalized coords
                nx1, ny1 = self.map_from_screen(self._last_mouse_pos)
                nx2, ny2 = self.map_from_screen(pos)
                dx = nx2 - nx1
                dy = ny2 - ny1
                
                r = self._shapes[self.selected_shape_index]['rect']
                # Use QRectF.translated
                new_r = r.translated(dx, dy)
                self._shapes[self.selected_shape_index]['rect'] = new_r
                self._last_mouse_pos = pos
                self.update()
                
        elif self._state == self.STATE_RESIZING:
            if self.selected_shape_index != -1 and self._drag_start_rect:
                # Complex resize logic in normalized coords
                nx, ny = self.map_from_screen(pos)
                r = self._shapes[self.selected_shape_index]['rect']
                # Get current bounds
                l, t, r_edge, b = r.left(), r.top(), r.right(), r.bottom()
                
                # IMPORTANT FIX: Use correct coordinate updates
                if self._active_handle == self.HANDLE_TOP_LEFT:
                    l, t = nx, ny
                elif self._active_handle == self.HANDLE_TOP_RIGHT:
                    r_edge, t = nx, ny
                elif self._active_handle == self.HANDLE_BOTTOM_LEFT:
                    l, b = nx, ny
                elif self._active_handle == self.HANDLE_BOTTOM_RIGHT:
                    r_edge, b = nx, ny
                elif self._active_handle == self.HANDLE_TOP:
                    t = ny
                elif self._active_handle == self.HANDLE_BOTTOM:
                    b = ny
                elif self._active_handle == self.HANDLE_LEFT:
                    l = nx
                elif self._active_handle == self.HANDLE_RIGHT:
                    r_edge = nx
                
                # Correct flip issues
                if l > r_edge: l, r_edge = r_edge, l
                if t > b: t, b = b, t

                # Fix: Use QPointF explicitly to avoid integer truncation issues
                new_rect = QRectF(QPointF(l, t), QPointF(r_edge, b))
                self._shapes[self.selected_shape_index]['rect'] = new_rect
                self.update()

        else:
            # Hover effects (Cursor change)
            if self.selected_shape_index != -1:
                r = self._shapes[self.selected_shape_index]['rect']
                sr = self.map_to_screen(r)
                handle = self.get_handle_at(pos, sr)
                if handle in [self.HANDLE_TOP_LEFT, self.HANDLE_BOTTOM_RIGHT]:
                    self.setCursor(Qt.SizeFDiagCursor) # type: ignore
                elif handle in [self.HANDLE_TOP_RIGHT, self.HANDLE_BOTTOM_LEFT]:
                    self.setCursor(Qt.SizeBDiagCursor) # type: ignore
                elif handle in [self.HANDLE_TOP, self.HANDLE_BOTTOM]:
                    self.setCursor(Qt.SizeVerCursor) # type: ignore
                elif handle in [self.HANDLE_LEFT, self.HANDLE_RIGHT]:
                    self.setCursor(Qt.SizeHorCursor) # type: ignore
                elif sr.contains(pos):
                    self.setCursor(Qt.SizeAllCursor) # type: ignore
                else:
                    self.setCursor(Qt.ArrowCursor) # type: ignore
            else:
                self.setCursor(Qt.ArrowCursor) # type: ignore

    def mouseReleaseEvent(self, event):
        if self._state == self.STATE_DRAWING:
            rect = self._current_rect
            if rect is not None and (rect.width() > 5 or rect.height() > 5):
                # Convert to normalized
                nx_tl, ny_tl = self.map_from_screen(rect.topLeft())
                nx_br, ny_br = self.map_from_screen(rect.bottomRight())
                w = nx_br - nx_tl
                h = ny_br - ny_tl
                
                if w > 0 and h > 0:
                    norm_rect = QRectF(nx_tl, ny_tl, w, h).normalized()
                    self.main_tab.add_new_shape(norm_rect)
            self._current_rect = None
            
        elif self._state in [self.STATE_MOVING, self.STATE_RESIZING]:
            # Finish move/resize, save changes
            # Ensure coords are within [0,1]
            if self.selected_shape_index != -1:
                r = self._shapes[self.selected_shape_index]['rect']
                x, y, w, h = r.x(), r.y(), r.width(), r.height()
                x = max(0.0, min(1.0-w, x))
                y = max(0.0, min(1.0-h, y))
                self._shapes[self.selected_shape_index]['rect'] = QRectF(x, y, w, h)

            self.main_tab.save_yolo_txt()
            self.main_tab.refresh_annotation_list()
        
        self._state = self.STATE_IDLE
        self.setCursor(Qt.ArrowCursor) # type: ignore
        self.update()

    def get_shape_at(self, pos):
        # Reverse check
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
    def __init__(self):
        super().__init__()
        self.current_image_path = None
        self.class_data = [] 
        self.current_class_index = -1 
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        splitter = QSplitter(Qt.Horizontal) # type: ignore

        # --- Left Panel ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)
        
        title_label = QLabel("数据集标注工具")
        title_label.setProperty("class", "sectionTitle")
        left_layout.addWidget(title_label)

        self.btn_open_dir = QPushButton(" 打开图片目录")
        self.btn_open_dir.setIcon(QIcon(resource_path("assets/icon_browse.png"))) # 这里可能需要注意图标路径
        self.btn_open_dir.clicked.connect(self.open_directory)
        left_layout.addWidget(self.btn_open_dir)
        
        # Path LineEdit (ReadOnly)
        self.img_dir_edit = QLineEdit()
        self.img_dir_edit.setPlaceholderText("未选择图片目录")
        self.img_dir_edit.setReadOnly(True)
        left_layout.addWidget(self.img_dir_edit)

        # Labels Path - Button ABOVE LineEdit
        left_layout.addSpacing(10)
        btn_out_browse = QPushButton(" 选择标签目录")
        btn_out_browse.setIcon(QIcon(resource_path("assets/icon_browse.png")))
        btn_out_browse.clicked.connect(self.select_output_dir)
        left_layout.addWidget(btn_out_browse)
        
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("保存位置 (默认与图片目录同级labels)")
        self.output_dir_edit.setReadOnly(True)
        left_layout.addWidget(self.output_dir_edit)

        left_layout.addWidget(QLabel("类别列表 (右键管理):"))
        self.class_list_widget = QListWidget()
        self.class_list_widget.setFixedHeight(120)
        self.class_list_widget.setContextMenuPolicy(Qt.CustomContextMenu) # type: ignore
        self.class_list_widget.customContextMenuRequested.connect(self.show_class_context_menu)
        self.class_list_widget.itemClicked.connect(self.on_category_clicked)
        left_layout.addWidget(self.class_list_widget)

        left_layout.addWidget(QLabel("当前图片标注:"))
        self.annotation_list_widget = QListWidget()
        self.annotation_list_widget.setFixedHeight(100)
        self.annotation_list_widget.setContextMenuPolicy(Qt.CustomContextMenu) # type: ignore
        self.annotation_list_widget.customContextMenuRequested.connect(lambda pos: self.show_annotation_context_menu(self.annotation_list_widget.mapToGlobal(pos), from_canvas=False))
        self.annotation_list_widget.itemClicked.connect(self.on_annotation_item_clicked)
        left_layout.addWidget(self.annotation_list_widget)

        # File List at bottom
        lbl_file_list = QLabel("文件列表:")
        self.file_list_widget = QListWidget()
        self.file_list_widget.itemClicked.connect(self.on_file_clicked)
        
        left_layout.addWidget(lbl_file_list)
        left_layout.addWidget(self.file_list_widget, 1) # Give stretch
        
        # --- Right Panel ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        
        nav_layout = QHBoxLayout()
        self.lbl_current_file = QLabel("未选择文件")
        self.lbl_current_file.setStyleSheet("font-weight: bold; color: #00aaff;")
        btn_prev = QPushButton(" 上一张")
        btn_prev.clicked.connect(lambda: self.change_image(-1))
        btn_next = QPushButton(" 下一张")
        btn_next.clicked.connect(lambda: self.change_image(1))
        nav_layout.addWidget(QLabel("当前:"))
        nav_layout.addWidget(self.lbl_current_file, 1)
        nav_layout.addWidget(btn_prev)
        nav_layout.addWidget(btn_next)
        right_layout.addLayout(nav_layout)

        self.canvas = AnnotationCanvas(self) 
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # 修改点：将画布容器背景设为 transparent (透明)，保留边框
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
        
        # 安装事件过滤器以处理键盘事件
        self.class_list_widget.installEventFilter(self)
        self.annotation_list_widget.installEventFilter(self)

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
            self.refresh_file_list()
            self.load_classes()

    def select_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择标签目录", self.output_dir_edit.text())
        if d: 
            self.output_dir_edit.setText(d)
            self.load_classes()

    def refresh_file_list(self):
        self.file_list_widget.clear()
        exts = ('.jpg', '.jpeg', '.png', '.bmp')
        if hasattr(self, 'current_dir'):
            for f in sorted(os.listdir(self.current_dir)):
                if f.lower().endswith(exts):
                    self.file_list_widget.addItem(f)

    def load_classes(self):
        self.class_data = []
        self.class_list_widget.clear()
        out_dir = self.output_dir_edit.text()
        json_path = os.path.join(out_dir, "classes.json")
        txt_path = os.path.join(out_dir, "classes.txt")
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f: self.class_data = json.load(f)
            except: pass
        if not self.class_data and os.path.exists(txt_path):
            with open(txt_path, 'r', encoding='utf-8') as f:
                names = [l.strip() for l in f.readlines() if l.strip()]
                for n in names:
                    self.class_data.append({"name": n, "color": [random.randint(50,255) for _ in range(3)]})
            self.save_classes_json()
        self.refresh_class_list_widget()

    def refresh_class_list_widget(self):
        self.class_list_widget.clear()
        for i, cls in enumerate(self.class_data):
            c = cls['color']
            icon = QPixmap(16, 16)
            icon.fill(QColor(*c))
            item = QListWidgetItem(QIcon(icon), f"{i}: {cls['name']}")
            self.class_list_widget.addItem(item)
        if self.current_class_index != -1 and self.current_class_index < self.class_list_widget.count():
            self.class_list_widget.setCurrentRow(self.current_class_index)
        else:
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

    def show_class_context_menu(self, pos):
        menu = QMenu()
        item = self.class_list_widget.itemAt(pos)
        idx = self.class_list_widget.row(item) if item else -1
        # Pylance Fix: Use wrapper or lambda for slots
        add_action = QAction("新建类别", self)
        add_action.triggered.connect(self.safe_add_new_class)
        menu.addAction(add_action)
        if idx != -1:
            edit_action = QAction("修改名称", self)
            edit_action.triggered.connect(lambda: self.edit_class_name(idx))
            menu.addAction(edit_action)
            color_action = QAction("修改颜色", self)
            color_action.triggered.connect(lambda: self.edit_class_color(idx))
            menu.addAction(color_action)
            del_action = QAction("删除类别", self)
            del_action.triggered.connect(lambda: self.delete_class(idx))
            menu.addAction(del_action)
        menu.exec_(self.class_list_widget.mapToGlobal(pos))

    def safe_add_new_class(self):
        self.add_new_class_dialog()

    def add_new_class_dialog(self):
        # 获取现有类别名称列表用于下拉提示
        existing_names = [c['name'] for c in self.class_data]
        
        name, ok = DarkDialogHelper.get_item(self, "选择/新建类别", "类别名称:", existing_names, 0, editable=True)
        
        if ok and name:
            name = name.strip()
            if not name: return -1

            # 修改点：检查是否已存在
            for i, cls in enumerate(self.class_data):
                if cls['name'] == name:
                    return i
            
            # 如果不存在，则进入新建流程
            color = DarkDialogHelper.get_color(self)
            if color.isValid():
                self.class_data.append({"name": name, "color": [color.red(), color.green(), color.blue()]})
                self.save_classes_json()
                self.refresh_class_list_widget()
                return len(self.class_data) - 1 
        
        return -1

    def edit_class_name(self, idx):
        old_name = self.class_data[idx]['name']
        name, ok = DarkDialogHelper.get_text(self, "修改名称", "新名称:", text=old_name)
        if ok and name:
            self.class_data[idx]['name'] = name
            self.save_classes_json()
            self.refresh_class_list_widget()
            self.canvas.update()
            self.refresh_annotation_list()

    def edit_class_color(self, idx):
        old_c = self.class_data[idx]['color']
        color = DarkDialogHelper.get_color(self, initial=QColor(*old_c))
        if color.isValid():
            self.class_data[idx]['color'] = [color.red(), color.green(), color.blue()]
            self.save_classes_json()
            self.refresh_class_list_widget()
            self.canvas.update()

    def delete_class(self, idx):
        reply = QMessageBox.question(self, "确认删除", "删除此类别可能影响现有标注，确定吗？")
        if reply == QMessageBox.Yes:
            self.class_data.pop(idx)
            self.save_classes_json()
            self.refresh_class_list_widget()
            self.current_class_index = -1

    def on_category_clicked(self, item):
        idx = self.class_list_widget.row(item)
        if idx == self.current_class_index:
            self.current_class_index = -1
            self.class_list_widget.clearSelection()
        else:
            self.current_class_index = idx

    def on_file_clicked(self, item):
        if item is None: return
        self.load_image(item.text())

    def on_annotation_item_clicked(self, item):
        idx = self.annotation_list_widget.row(item)
        self.canvas.selected_shape_index = idx
        self.canvas.update()

    def change_image(self, delta):
        count = self.file_list_widget.count()
        if count == 0: return
        curr_row = self.file_list_widget.currentRow()
        next_row = curr_row + delta
        if 0 <= next_row < count:
            self.file_list_widget.setCurrentRow(next_row)
            item = self.file_list_widget.item(next_row)
            if item:
                self.load_image(item.text())
        else:
            QMessageBox.information(self, "提示", "已经是第一张或最后一张了。")

    def load_image(self, filename):
        if not self.current_dir:
            self.img_dir_edit.setText("未选择图片目录")
            self.lbl_current_file.setText("未选择文件")
            self.canvas.set_pixmap(None)
            self.load_yolo_labels("")
            self.refresh_annotation_list()
            return

        self.current_image_path = os.path.join(self.current_dir, filename)
        self.lbl_current_file.setText(filename)
        pixmap = QPixmap(self.current_image_path)
        self.canvas.set_pixmap(pixmap)
        self.load_yolo_labels(filename)
        self.refresh_annotation_list()

    def load_yolo_labels(self, filename):
        if not filename: return
        txt_name = os.path.splitext(filename)[0] + ".txt"
        out_dir = self.output_dir_edit.text()
        txt_path = os.path.join(out_dir, txt_name) if out_dir else ""
        shapes = []
        if os.path.exists(txt_path):
            with open(txt_path, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        cls_idx = int(parts[0])
                        cx, cy, w, h = map(float, parts[1:5])
                        x = cx - w/2
                        y = cy - h/2
                        shapes.append({'class_index': cls_idx, 'rect': QRectF(x, y, w, h)})
        self.canvas.set_shapes(shapes)

    def add_new_shape(self, rect_normalized):
        cls_idx = self.current_class_index
        if cls_idx == -1:
            new_idx = self.add_new_class_dialog()
            if new_idx != -1:
                cls_idx = new_idx
                self.current_class_index = new_idx
                self.class_list_widget.setCurrentRow(new_idx)
            else:
                return 

        self.canvas._shapes.append({'class_index': cls_idx, 'rect': rect_normalized})
        self.save_yolo_txt()
        self.refresh_annotation_list()
        self.canvas.update()

    def remove_shape(self, index):
        if 0 <= index < len(self.canvas._shapes):
            self.canvas._shapes.pop(index)
            self.save_yolo_txt()
            self.refresh_annotation_list()
            self.canvas.selected_shape_index = -1
            self.canvas.update()

    def save_yolo_txt(self):
        if not self.current_image_path: return
        out_dir = self.output_dir_edit.text()
        if not out_dir: return
        if not os.path.exists(out_dir): os.makedirs(out_dir)
        txt_name = os.path.splitext(os.path.basename(self.current_image_path))[0] + ".txt"
        txt_path = os.path.join(out_dir, txt_name)
        with open(txt_path, 'w', encoding='utf-8') as f:
            for shape in self.canvas.get_shapes():
                cls_idx = shape['class_index']
                rect = shape['rect']
                cx = rect.x() + rect.width()/2
                cy = rect.y() + rect.height()/2
                f.write(f"{cls_idx} {cx:.6f} {cy:.6f} {rect.width():.6f} {rect.height():.6f}\n")

    def refresh_annotation_list(self):
        self.annotation_list_widget.clear()
        for i, shape in enumerate(self.canvas.get_shapes()):
            cls_idx = shape['class_index']
            name = self.get_class_name(cls_idx)
            item = QListWidgetItem(f"ID {i}: {name}")
            self.annotation_list_widget.addItem(item)

    def show_annotation_context_menu(self, pos, from_canvas=False):
        menu = QMenu()
        idx = -1
        if from_canvas:
            idx = self.canvas.selected_shape_index
        else:
            item = self.annotation_list_widget.itemAt(self.annotation_list_widget.mapFromGlobal(pos))
            idx = self.annotation_list_widget.row(item) if item else -1
        
        if idx != -1:
            del_action = QAction("删除标注", self)
            del_action.triggered.connect(lambda: self.remove_shape(idx))
            menu.addAction(del_action)
            change_action = QAction("修改类别", self)
            change_action.triggered.connect(lambda: self.change_shape_class(idx))
            menu.addAction(change_action)
            menu.exec_(pos)

    def change_shape_class(self, idx):
        existing_names = [c['name'] for c in self.class_data]
        # 同样开启 editable=True，允许用户在修改时直接创建新类
        name, ok = DarkDialogHelper.get_item(self, "修改类别", "选择或输入新类别:", existing_names, 0, editable=True)
        
        if ok and name:
            name = name.strip()
            if not name: return

            new_cls_idx = -1
            # 1. 检查是否存在
            for i, cls in enumerate(self.class_data):
                if cls['name'] == name:
                    new_cls_idx = i
                    break
            
            # 2. 不存在则创建新类
            if new_cls_idx == -1:
                color = DarkDialogHelper.get_color(self)
                if color.isValid():
                    self.class_data.append({"name": name, "color": [color.red(), color.green(), color.blue()]})
                    self.save_classes_json()
                    self.refresh_class_list_widget()
                    new_cls_idx = len(self.class_data) - 1
                else:
                    return # 用户取消了颜色选择，终止修改

            # 3. 应用更改
            if new_cls_idx != -1:
                self.canvas._shapes[idx]['class_index'] = new_cls_idx
                self.save_yolo_txt()
                self.refresh_annotation_list()
                self.canvas.update()

    def highlight_annotation_in_list(self, idx):
        self.annotation_list_widget.setCurrentRow(idx)

    def get_class_color(self, idx):
        if 0 <= idx < len(self.class_data):
            return self.class_data[idx]['color']
        return [255, 255, 255] 

    def get_class_name(self, idx):
        if 0 <= idx < len(self.class_data):
            return self.class_data[idx]['name']
        return str(idx)
    
    def eventFilter(self, source, event):
        # 监听键盘按键事件
        if event.type() == QEvent.KeyPress: # type: ignore
            # 处理 Delete 键删除列表项
            if event.key() == Qt.Key_Delete: # type: ignore
                if source == self.class_list_widget:
                    row = self.class_list_widget.currentRow()
                    if row != -1:
                        self.delete_class(row)
                    return True
                elif source == self.annotation_list_widget:
                    row = self.annotation_list_widget.currentRow()
                    if row != -1:
                        self.remove_shape(row)
                    return True
        return super().eventFilter(source, event)

# ============================================
# 主窗口 (Main App)
# ============================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("数据标注工具")
        self.setMinimumSize(1000, 700)
        
        # 设置窗口图标
        # 优先查找 app_icon.png (白色主题图标) 适配深色界面
        icon_names = ["app_icon.png", "app_icon.ico"]
        for name in icon_names:
            icon_path = resource_path(os.path.join("assets", name))
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
                break
            
        self.central_widget = AnnotationApp() # 使用标注界面作为中心组件
        self.setCentralWidget(self.central_widget)

# ============================================
# QSS 样式表
# ============================================
QSS_STYLE = """
QWidget { color: #e0e0e0; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 14px; }
QMainWindow { background-color: #121212; }
QGroupBox { border: 1px solid #444444; border-radius: 8px; margin-top: 25px; font-weight: bold; background-color: rgba(45, 45, 50, 0.5); }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 15px; padding: 0 5px; color: #00aaff; }
QPushButton { border: 1px solid #555; border-radius: 6px; background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #3c3c3c, stop: 1 #303030); padding: 6px 12px; min-height: 24px; }
QPushButton:hover { background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #4d4d4d, stop: 1 #404040); border-color: #007acc; }
QPushButton:pressed { background-color: #252525; }
QPushButton:disabled { background-color: #2a2a2a; color: #666666; border-color: #333; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { border: 1px solid #555; border-radius: 4px; padding: 4px; background-color: #252526; color: #e0e0e0; selection-background-color: #007acc; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid #007acc; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border-left-width: 1px; border-left-color: #555; border-top-right-radius: 4px; border-bottom-right-radius: 4px; background-color: #333; }
QListWidget { background-color: #252526; border: 1px solid #444; border-radius: 6px; padding: 5px; }
QListWidget::item:selected { background-color: #007acc; color: white; border-radius: 4px; }
QLabel[class="sectionTitle"] { font-size: 18px; font-weight: bold; color: #ffffff; padding-bottom: 8px; border-bottom: 2px solid #007acc; margin-bottom: 15px; }
QSplitter::handle { background-color: #3a3a3a; width: 2px; }
QToolTip { border: 1px solid #555; background-color: #2b2b2b; color: #e0e0e0; padding: 5px; }
QMenu { background-color: #2b2b2b; border: 1px solid #444; }
QMenu::item { padding: 5px 25px 5px 25px; color: #e0e0e0; background-color: transparent; }
QMenu::item:selected { background-color: #007acc; color: #ffffff; }
QMenu::separator { height: 1px; background: #444; margin: 5px 10px; }
QMessageBox { background-color: #2b2b2b; color: #e0e0e0; }
QMessageBox QLabel { color: #e0e0e0; }
QDialog { background-color: #2b2b2b; color: #e0e0e0; }
QDialog QLabel { color: #e0e0e0; }
QInputDialog QComboBox { background-color: #252526; color: #e0e0e0; border: 1px solid #555; }
QInputDialog QComboBox QAbstractItemView { background-color: #252526; color: #e0e0e0; selection-background-color: #007acc; }
QColorDialog { background-color: #2b2b2b; color: #e0e0e0; }
"""

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 应用全局样式
    app.setStyleSheet(QSS_STYLE)
    
    # 启动主窗口
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
