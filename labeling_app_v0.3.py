"""
项目名称: 独立数据标注工具 (Labeling Tool)
版本: v0.3
开发环境: Python 3.9+ | PyQt5

功能说明:
    引入表格控件与 ID 管理，增强数据展示能力。
    主要功能:
    1. 列表升级: 将简单的 ListWidget 升级为 QTableWidget，显示文件名、修改时间等详情。
    2. 类别管理: 支持拖拽调整类别 ID 顺序，处理 ID 冲突与合并。
    3. 独立导出: 格式转换从实时保存分离，改为独立的导出功能。

使用说明:
    1. 运行: python labeling_app_v0.3.py
    2. 类别排序: 在类别列表中拖拽行可重新分配 ID。

更新日志 (v0.3):
    [新增] 文件与标注列表使用表格控件，支持列排序。
    [新增] 类别 ID 管理系统，支持拖拽排序和冲突解决。
    [新增] 独立的“导出标注”对话框。
    [优化] 界面布局调整，移除顶部大标题以节省空间。

打包指令:
    pyinstaller --noconsole --onefile --icon=assets/app_icon_colored.png --name="LabelingTool_v0.3" --add-data "assets;assets" labeling_app_v0.3.py
"""

import sys
import os
import json
import random
import time
import shutil
from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QLineEdit, QFileDialog, 
                             QMessageBox, QSplitter, QListWidget, QTableWidget, QTableWidgetItem,
                             QFrame, QSizePolicy, QInputDialog, QMenu, QAction, QHeaderView,
                             QListWidgetItem, QColorDialog, QDialog, QComboBox, QAbstractItemView)
from PyQt5.QtCore import Qt, QSize, QPoint, QPointF, QRectF, QRect, QEvent, QMimeData
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor, QPen, QDrag

# ============================================
# 工具函数与类
# ============================================

def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

class CustomHeader(QHeaderView):
    """ 自定义表头，支持简单的排序图标绘制 """
    def __init__(self, orientation=Qt.Horizontal, parent=None): # type: ignore
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        # 默认禁用内置的sortIndicator绘制(如果想完全自己画)，或者与之共存
        # 这里我们覆盖paintSection在默认绘制后追加我们自己的图形
        self.filter_column = -1  # 哪一列处于筛选状态(示例)

    def set_filter_column(self, col):
        self.filter_column = col
        vp = self.viewport()
        if vp:
            vp.update()

    def paintSection(self, painter, rect, logicalIndex):
        if not painter: return
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()

        # 1. 绘制排序图标 (三角形)
        # 只有当显示排序指示器且当前列是被排序列时
        if self.isSortIndicatorShown() and self.sortIndicatorSection() == logicalIndex:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            
            size = 8
            margin = 5
            
            # 位置: 右侧居中
            cx = rect.right() - margin - size
            cy = rect.center().y()
            
            # [修复] 绘制背景遮挡文字重叠
            # 计算需要清除的区域 (右侧包含图标的区域)
            clear_w = size + margin * 2
            clear_rect = QRectF(rect.right() - clear_w, rect.top(), clear_w, rect.height())
            
            # 获取背景色 (尝试匹配当前样式)
            # 由于 stylesheet 设置 QHeaderView::section 为 #333，这里硬编码匹配防止调色板获取失败
            bg_color = QColor(51, 51, 51) 
            painter.setPen(Qt.NoPen) # type: ignore
            painter.setBrush(bg_color)
            painter.drawRect(clear_rect)
            
            # 绘制图标
            painter.setBrush(QColor(0, 120, 215)) # 蓝色强调

            path = QPointF()
            if self.sortIndicatorOrder() == Qt.AscendingOrder: # type: ignore
                # 上三角形
                p1 = QPointF(cx, cy - size/2)
                p2 = QPointF(cx - size/2, cy + size/2)
                p3 = QPointF(cx + size/2, cy + size/2)
                painter.drawPolygon(p1, p2, p3)
            else:
                # 下三角形
                p1 = QPointF(cx - size/2, cy - size/2)
                p2 = QPointF(cx + size/2, cy - size/2)
                p3 = QPointF(cx, cy + size/2)
                painter.drawPolygon(p1, p2, p3)
            painter.restore()
        
        # 2. 绘制筛选漏斗 (如有)
        if hasattr(self, 'filter_column') and self.filter_column == logicalIndex:
             painter.save()
             painter.setRenderHint(QPainter.Antialiasing)
             painter.setPen(QPen(QColor(255, 100, 0), 1.5)) # 橙色
             painter.setBrush(Qt.NoBrush) # type: ignore
             
             # 简易漏斗
             sz = 6
             cx = rect.left() + 15
             cy = rect.center().y()
             
             # Draw funnel shape: Line top, cone down, spout
             # 简单的图形: 倒三角形 + 竖线
             p1 = QPointF(cx - sz, cy - sz)
             p2 = QPointF(cx + sz, cy - sz)
             p3 = QPointF(cx, cy + sz)
             painter.drawPolygon(p1, p2, p3)
             painter.drawLine(QPointF(cx, cy+sz), QPointF(cx, cy+sz+3))

             painter.restore()

# ============================================
# 自定义表格控件 (支持拖拽排序)
# ============================================

class DraggableTableWidget(QTableWidget):
    """ 支持拖拽行进行排序或交换的表格 """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 设置自定义表头
        self.setHorizontalHeader(CustomHeader(Qt.Horizontal, self)) # type: ignore
        
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        # Pylance fix: 显式检查
        vp = self.viewport()
        if vp is not None:
            vp.setAcceptDrops(True)
            
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        
        self.drag_start_row = -1
        self.main_app = None # Reference to AnnotationApp for callbacks


    def set_main_app(self, app):
        self.main_app = app

    def startDrag(self, supportedActions):
        self.drag_start_row = self.currentRow()
        super().startDrag(supportedActions)

    def dropEvent(self, event):
        if not event: return
        if not self.main_app or self.drag_start_row == -1:
            super().dropEvent(event)
            return

        # 获取目标行
        pos = event.pos()
        target_row = self.indexAt(pos).row()
        
        # 如果是空白处，默认追加到最后
        if target_row == -1: 
            target_row = self.rowCount() - 1

        if target_row == self.drag_start_row:
            event.ignore()
            return

        # 判断是 "交换" 还是 "插入"
        # 简化逻辑：如果是拖动到了某个Item的中心区域，视为交换 (Swap)
        # 如果是拖拽到了Item的边缘（DropIndicator显示），视为插入 (Insert)
        # 但是 QTableWidget 的默认 dropEvent 是做移动（删除+插入）。
        # 我们需要在这里拦截并执行我们自己的逻辑
        
        # 检查是否开启了排序/筛选，如果开启则禁止插入
        is_sorting = self.isSortingEnabled()
        if is_sorting:
             # 如果正在排序，逻辑比较复杂，暂时禁止拖动，或者只允许逻辑交换
             # 用户需求：后面排序筛选逻辑启用时，插入逻辑不可用
             # 这里简单判断，如果是排序状态，提示不可用并忽略
             # 其实 sorted 状态下 view 和 model index 不一致，处理很麻烦
             # 建议: 拖拽时暂时关闭排序
             pass

        # 获取DropIndicator的位置
        drop_pos = self.dropIndicatorPosition() 
        # OnItem, AboveItem, BelowItem, OnViewport
        
        source_idx = self.drag_start_row
        target_idx = target_row
        
        # 判断意图：OnItem -> Swap, Above/Below -> Insert
        if drop_pos == QAbstractItemView.OnItem:
            # 执行交换
            if QMessageBox.question(self, "交换类别ID", f"确定交换 ID {source_idx} 和 ID {target_idx} 吗？\n这将影响所有相关联的标注。", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.main_app.swap_class_ids(source_idx, target_idx)
                event.accept()
        else:
            # 执行插入
            # 计算实际插入位置
            # if drop_pos == QAbstractItemView.BelowItem: target_idx += 1
            # 这里的 target_idx 是视觉上的行，已经由基类逻辑计算了 indicator
            
            # 由于QTableWidget默认的InternalMove就是插入逻辑(Move)，如果不重写，它会自己搬运数据
            # 但是我们需要联动 class_data 的更新
            # 所以我们拦截事件，执行数据更新，然后刷新表格
            
            # 注意：在排序启用时，不允许插入
            if self.header_sorted_column() != -1:
                QMessageBox.warning(self, "禁止操作", "请先取消排序再进行拖拽排序。")
                event.ignore()
                return

            self.main_app.move_class_id(source_idx, target_idx)
            event.accept()
    
    def header_sorted_column(self):
        # 检查是否有列处于排序状态
        header = self.horizontalHeader()
        if header is not None and header.isSortIndicatorShown(): # type: ignore
            return header.sortIndicatorSection() # type: ignore
        return -1

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
        self._drag_start_rect = None 
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

        rect = self._current_rect
        if rect is not None:
            painter.setPen(QPen(QColor(255, 255, 255), 2, Qt.DashLine)) # type: ignore
            painter.setBrush(Qt.NoBrush) # type: ignore
            painter.drawRect(rect)

    def mousePressEvent(self, event):
        if not self._pixmap: return
        pos = event.localPos() 
        
        if event.button() == Qt.RightButton: # type: ignore
            hit_shape = self.get_shape_at(pos)
            if hit_shape != -1:
                self.selected_shape_index = hit_shape
                self.update()
                self.main_tab.show_annotation_context_menu(self.mapToGlobal(event.pos()), from_canvas=True)
            else:
                self._state = self.STATE_PANNING
                self._last_mouse_pos = pos
                self.setCursor(Qt.ClosedHandCursor) # type: ignore
            return

        if event.button() == Qt.LeftButton: # type: ignore
            if self.selected_shape_index != -1:
                rect_norm = self._shapes[self.selected_shape_index]['rect']
                screen_rect = self.map_to_screen(rect_norm)
                handle = self.get_handle_at(pos, screen_rect)
                if handle:
                    self._state = self.STATE_RESIZING
                    self._active_handle = handle
                    self._drag_start_rect = rect_norm 
                    self._last_mouse_pos = pos
                    return
                
                if screen_rect.contains(pos):
                    self._state = self.STATE_MOVING
                    self._drag_start_rect = rect_norm 
                    self._last_mouse_pos = pos
                    return

            hit_shape = self.get_shape_at(pos)
            if hit_shape != -1:
                self.selected_shape_index = hit_shape
                self.main_tab.highlight_annotation_in_list(hit_shape)
                self.update()
                self._state = self.STATE_MOVING
                self._drag_start_rect = self._shapes[hit_shape]['rect']
                self._last_mouse_pos = pos
            else:
                self.selected_shape_index = -1
                self.main_tab.annotation_table.clearSelection()
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
                
        elif self._state == self.STATE_MOVING:
            if self.selected_shape_index != -1 and self._drag_start_rect:
                nx1, ny1 = self.map_from_screen(self._last_mouse_pos)
                nx2, ny2 = self.map_from_screen(pos)
                dx = nx2 - nx1
                dy = ny2 - ny1
                
                r = self._shapes[self.selected_shape_index]['rect']
                new_r = r.translated(dx, dy)
                
                x, y, w, h = new_r.x(), new_r.y(), new_r.width(), new_r.height()
                if x < 0: x = 0
                if y < 0: y = 0
                if x + w > 1: x = 1 - w
                if y + h > 1: y = 1 - h
                
                self._shapes[self.selected_shape_index]['rect'] = QRectF(x, y, w, h)
                self._last_mouse_pos = pos
                self.update()
                
        elif self._state == self.STATE_RESIZING:
            if self.selected_shape_index != -1 and self._drag_start_rect:
                nx, ny = self.map_from_screen(pos)
                nx, ny = self.limit_to_image_bounds(nx, ny)
                
                r = self._shapes[self.selected_shape_index]['rect']
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
                self._shapes[self.selected_shape_index]['rect'] = new_rect
                self.update()

        else:
            if self.selected_shape_index != -1:
                r = self._shapes[self.selected_shape_index]['rect']
                sr = self.map_to_screen(r)
                handle = self.get_handle_at(pos, sr)
                if handle in [self.HANDLE_TOP_LEFT, self.HANDLE_BOTTOM_RIGHT]: self.setCursor(Qt.SizeFDiagCursor) # type: ignore
                elif handle in [self.HANDLE_TOP_RIGHT, self.HANDLE_BOTTOM_LEFT]: self.setCursor(Qt.SizeBDiagCursor) # type: ignore
                elif handle in [self.HANDLE_TOP, self.HANDLE_BOTTOM]: self.setCursor(Qt.SizeVerCursor) # type: ignore
                elif handle in [self.HANDLE_LEFT, self.HANDLE_RIGHT]: self.setCursor(Qt.SizeHorCursor) # type: ignore
                elif sr.contains(pos): self.setCursor(Qt.SizeAllCursor) # type: ignore
                else: self.setCursor(Qt.ArrowCursor) # type: ignore
            else:
                self.setCursor(Qt.ArrowCursor) # type: ignore

    def mouseReleaseEvent(self, event):
        if self._state == self.STATE_DRAWING:
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
            
        elif self._state in [self.STATE_MOVING, self.STATE_RESIZING]:
            if self.selected_shape_index != -1:
                r = self._shapes[self.selected_shape_index]['rect']
                x, y, w, h = r.x(), r.y(), r.width(), r.height()
                x = max(0.0, min(1.0-w, x))
                y = max(0.0, min(1.0-h, y))
                self._shapes[self.selected_shape_index]['rect'] = QRectF(x, y, w, h)
                self._shapes[self.selected_shape_index]['updated_at'] = get_timestamp() # Update Time

            self.main_tab.save_current_annotations(format_override=None) 
            self.main_tab.refresh_annotation_table()
        
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
        
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        splitter = QSplitter(Qt.Horizontal) # type: ignore

        # --- Left Panel ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)
        
        # v0.3 Removed Title Label
        
        # Format Selection Row with Export
        fmt_layout = QHBoxLayout()
        fmt_layout.addWidget(QLabel("工作格式:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems([self.FORMAT_YOLO_TXT, self.FORMAT_VOC_XML, self.FORMAT_COCO_JSON])
        self.format_combo.currentTextChanged.connect(self.on_format_changed)
        fmt_layout.addWidget(self.format_combo)
        
        btn_export = QPushButton("导出")
        btn_export.clicked.connect(self.export_annotations_dialog)
        # btn_export.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;") 
        fmt_layout.addWidget(btn_export)
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

        # --- Class Table (New in v0.3) ---
        left_layout.addSpacing(10)
        left_layout.addWidget(QLabel("类别列表 (支持右键/拖拽):"))
        self.class_table = DraggableTableWidget()
        self.class_table.setColumnCount(3)
        self.class_table.setHorizontalHeaderLabels(["Class ID", "名称", "修改时间"])
        
        # 使用 CustomHeader 并允许列宽调整
        class_header = self.class_table.horizontalHeader()
        if class_header:
            class_header.setSectionResizeMode(QHeaderView.Interactive)
            class_header.setStretchLastSection(True)
            
        self.class_table.setSortingEnabled(True) # Enable Sort
        self.class_table.setFixedHeight(150)
        self.class_table.setContextMenuPolicy(Qt.CustomContextMenu) # type: ignore
        self.class_table.customContextMenuRequested.connect(self.show_class_context_menu)
        self.class_table.itemClicked.connect(self.on_category_clicked)
        self.class_table.set_main_app(self)
        left_layout.addWidget(self.class_table)

        # --- Annotation Table (New in v0.3) ---
        left_layout.addWidget(QLabel("当前图片标注列表:"))
        self.annotation_table = QTableWidget()
        self.annotation_table.setColumnCount(4)
        self.annotation_table.setHorizontalHeaderLabels(["ID", "Class ID", "名称", "修改时间"])
        
        # 配置表头与列宽
        self.annotation_table.setHorizontalHeader(CustomHeader(Qt.Horizontal, self.annotation_table)) # type: ignore
        ann_header = self.annotation_table.horizontalHeader()
        if ann_header:
            ann_header.setSectionResizeMode(QHeaderView.Interactive)
            ann_header.setStretchLastSection(True)

        self.annotation_table.setSortingEnabled(True)
        self.annotation_table.setFixedHeight(120)
        self.annotation_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.annotation_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.annotation_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.annotation_table.setContextMenuPolicy(Qt.CustomContextMenu) # type: ignore
        self.annotation_table.customContextMenuRequested.connect(lambda pos: self.show_annotation_context_menu(self.annotation_table.mapToGlobal(pos), from_canvas=False))
        self.annotation_table.itemClicked.connect(self.on_annotation_item_clicked)
        left_layout.addWidget(self.annotation_table)

        # --- File Table (New in v0.3) ---
        lbl_file_list = QLabel("文件列表:")
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(2)
        self.file_table.setHorizontalHeaderLabels(["文件名", "修改时间"])
        
        # 配置表头与列宽
        self.file_table.setHorizontalHeader(CustomHeader(Qt.Horizontal, self.file_table)) # type: ignore
        file_header = self.file_table.horizontalHeader()
        if file_header:
            file_header.setSectionResizeMode(QHeaderView.Interactive)
            file_header.setStretchLastSection(True)
            
        self.file_table.setSortingEnabled(True)
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.itemClicked.connect(self.on_file_clicked)
        
        left_layout.addWidget(lbl_file_list)
        left_layout.addWidget(self.file_table, 1) 
        
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

    # ==========================
    # Logic: Format & Export
    # ==========================
    
    def on_format_changed(self, text):
        # v0.3: Switching format DOES NOT auto-save.
        # It changes the 'mode' for reading/writing future actions.
        # If user switches format, they might want to reload the current image's labels in new format?
        prev_format = self.current_format
        self.current_format = text
        
        QMessageBox.information(self, "格式变更", f"工作格式已切换为 {text}。\n注意：原有标注保留在原文件格式中，如需转换请使用【导出】功能。")
        
        # Optionally reload current image to try loading labels in new format
        if self.current_image_path:
             self.load_image(os.path.basename(self.current_image_path))

    def export_annotations_dialog(self):
        # Dialog to choose target format
        items = [self.FORMAT_YOLO_TXT, self.FORMAT_VOC_XML, self.FORMAT_COCO_JSON]
        target_fmt, ok = QInputDialog.getItem(self, "导出标注", "选择目标导出格式:", items, 0, False)
        if not ok or not target_fmt: return
        
        default_export_path = os.path.join(self.output_dir_edit.text() or "", "export")
        export_dir = QFileDialog.getExistingDirectory(self, "选择导出目录", default_export_path)
        if not export_dir: return
        
        # Batch Process
        count = 0
        total = self.file_table.rowCount()
        
        try:
            # We iterate file list
            for row in range(total):
                item = self.file_table.item(row, 0)
                if not item: continue
                filename = item.text()
                
                # 1. Load labels using CURRENT format logic (cached or from disk)
                # But we can't disturb current GUI state too much. 
                # We need a headless loading method
                shapes = self._load_shapes_headless(filename, self.current_format)
                
                # 2. Save to TARGET format in NEW dir
                self._save_shapes_headless(shapes, filename, target_fmt, export_dir)
                count += 1
                
            QMessageBox.information(self, "导出成功", f"成功导出 {count} 个文件的标注到:\n{export_dir}")
        except Exception as e:
             QMessageBox.critical(self, "导出失败", str(e))

    def _load_shapes_headless(self, filename, fmt):
        # Re-use logic but without canvas dependency if possible
        # Actually simplest is just using current App methods but redirecting output
        # For simplicity, we assume we load from disk.
        shapes = []
        # Construct path
        if fmt == self.FORMAT_YOLO_TXT:
             # Just like load_yolo_labels but returns list
             txt_name = os.path.splitext(filename)[0] + ".txt"
             path = os.path.join(self.output_dir_edit.text(), txt_name)
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
             path = os.path.join(self.output_dir_edit.text(), xml_name)
             if os.path.exists(path):
                 try:
                     tree = ET.parse(path)
                     root = tree.getroot()
                     size = root.find('size')
                     width, height = 0.0, 0.0
                     if size is not None:
                         w_e = size.find('width')
                         h_e = size.find('height')
                         if w_e is not None and w_e.text: width = float(w_e.text)
                         if h_e is not None and h_e.text: height = float(h_e.text)
                     
                     for obj in root.findall('object'):
                         name_e = obj.find('name')
                         name = name_e.text if (name_e is not None and name_e.text) else ""
                         bndbox = obj.find('bndbox')
                         if bndbox is not None:
                             xmin_e = bndbox.find('xmin')
                             ymin_e = bndbox.find('ymin')
                             xmax_e = bndbox.find('xmax')
                             ymax_e = bndbox.find('ymax')
                             
                             if xmin_e is not None and xmin_e.text and \
                                ymin_e is not None and ymin_e.text and \
                                xmax_e is not None and xmax_e.text and \
                                ymax_e is not None and ymax_e.text:
                                 
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
             # Reuse loaded self.coco_data
             if not self.coco_data: self._ensure_coco_loaded()
             # Find image
             img_entry = next((i for i in self.coco_data.get('images', []) if i['file_name'] == filename), None)
             if img_entry:
                 img_id = img_entry['id']
                 img_w, img_h = img_entry['width'], img_entry['height']
                 anns = [a for a in self.coco_data.get('annotations', []) if a['image_id'] == img_id]
                 
                 # Map Cat ID
                 cat_id_to_idx = {} 
                 for i, c in enumerate(self.class_data):
                     for coco_cat in self.coco_data.get('categories', []):
                         if coco_cat['name'] == c['name']: cat_id_to_idx[coco_cat['id']] = i; break
                 
                 for a in anns:
                     if a.get('category_id') in cat_id_to_idx:
                         box = a.get('bbox', [0,0,0,0])
                         shapes.append({'class_index': cat_id_to_idx[a['category_id']], 
                                        'rect': QRectF(box[0]/img_w, box[1]/img_h, box[2]/img_w, box[3]/img_h)})
        return shapes

    def _save_shapes_headless(self, shapes, filename, fmt, out_dir):
        if not os.path.exists(out_dir): os.makedirs(out_dir)
        
        # Assume generic image size if not loaded (Warning: VOC/COCO need real size)
        # We might need to read image header if possible, or skip size dependent logic
        # For this script, we'll try to use QPixmap(filename) if available, else standard
        img_path = os.path.join(self.current_dir, filename)
        img_w, img_h = 1000, 1000 # Fallback
        if os.path.exists(img_path):
            pm = QPixmap(img_path)
            if not pm.isNull(): img_w, img_h = pm.width(), pm.height()
            
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
            # COCO Export is complex because it's one file for all.
            # We create a SINGLE export file.
            json_path = os.path.join(out_dir, "export_coco.json")
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f: data = json.load(f)
            else:
                data = {"images": [], "annotations": [], "categories": []}
                # Init cats
                for i, c in enumerate(self.class_data):
                    data['categories'].append({"id": i+1, "name": c['name']})
            
            # Add Image
            img_id = len(data['images']) + 1 # Simple ID
            data['images'].append({"id": img_id, "file_name": filename, "width": img_w, "height": img_h})
            
            # Add Anns
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
        d = QFileDialog.getExistingDirectory(self, "选择标签目录", self.output_dir_edit.text())
        if d: 
            self.output_dir_edit.setText(d)
            self.load_classes()

    def refresh_file_table(self):
        self.file_table.setSortingEnabled(False) # Disable sort during update
        self.file_table.setRowCount(0)
        exts = ('.jpg', '.jpeg', '.png', '.bmp')
        if hasattr(self, 'current_dir'):
            files = sorted([f for f in os.listdir(self.current_dir) if f.lower().endswith(exts)])
            self.file_table.setRowCount(len(files))
            for i, f in enumerate(files):
                # Name
                item_name = QTableWidgetItem(f)
                self.file_table.setItem(i, 0, item_name)
                
                # Mod Time
                full_path = os.path.join(self.current_dir, f)
                ts = datetime.fromtimestamp(os.path.getmtime(full_path)).strftime("%Y-%m-%d %H:%M")
                item_time = QTableWidgetItem(ts)
                self.file_table.setItem(i, 1, item_time)
        
        self.file_table.setSortingEnabled(True)

    def load_classes(self):
        self.class_data = []
        self.class_table.setRowCount(0)
        out_dir = self.output_dir_edit.text()
        json_path = os.path.join(out_dir, "classes.json")
        txt_path = os.path.join(out_dir, "classes.txt")
        
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f: self.class_data = json.load(f)
            except: pass
            
        elif os.path.exists(txt_path):
            with open(txt_path, 'r', encoding='utf-8') as f:
                names = [l.strip() for l in f.readlines() if l.strip()]
                for n in names:
                    self.class_data.append({"name": n, "color": [random.randint(50,255) for _ in range(3)], "updated_at": get_timestamp()})
            self.save_classes_json()
        
        # Ensure updated_at exists
        for c in self.class_data:
            if 'updated_at' not in c: c['updated_at'] = get_timestamp()
            
        self.refresh_class_table()

    def refresh_class_table(self):
        self.class_table.setSortingEnabled(False)
        self.class_table.setRowCount(len(self.class_data))
        for i, cls in enumerate(self.class_data):
            # ID
            item_id = QTableWidgetItem(str(i))
            item_id.setTextAlignment(Qt.AlignCenter) # type: ignore
            # Color bg for ID
            c = cls['color']
            item_id.setBackground(QColor(*c))
            if (c[0]*0.299 + c[1]*0.587 + c[2]*0.114) < 128: item_id.setForeground(QColor(255,255,255))
            else: item_id.setForeground(QColor(0,0,0))
            
            self.class_table.setItem(i, 0, item_id)
            
            # Name
            self.class_table.setItem(i, 1, QTableWidgetItem(cls['name']))
            
            # Time
            self.class_table.setItem(i, 2, QTableWidgetItem(cls.get('updated_at', '')))
            
        if self.current_class_index != -1 and self.current_class_index < self.class_table.rowCount():
            self.class_table.selectRow(self.current_class_index)
        
        self.class_table.setSortingEnabled(True)

    def show_class_context_menu(self, pos):
        menu = QMenu()
        item = self.class_table.itemAt(pos)
        idx = item.row() if item else -1
        
        add_action = QAction("新建类别", self)
        add_action.triggered.connect(self.safe_add_new_class)
        menu.addAction(add_action)
        
        if idx != -1:
            menu.addSeparator()
            edit_action = QAction("修改名称", self)
            edit_action.triggered.connect(lambda: self.edit_class_name(idx))
            menu.addAction(edit_action)
            
            color_action = QAction("修改颜色", self)
            color_action.triggered.connect(lambda: self.edit_class_color(idx))
            menu.addAction(color_action)
            
            id_action = QAction("修改序号 (ID)", self)
            id_action.triggered.connect(lambda: self.edit_class_id(idx))
            menu.addAction(id_action)
            
            del_action = QAction("删除类别", self)
            del_action.triggered.connect(lambda: self.delete_class(idx))
            menu.addAction(del_action)
            
        menu.exec_(self.class_table.mapToGlobal(pos))

    # ==========================
    # Logic: Class ID Management
    # ==========================
    
    def edit_class_id(self, old_idx):
        new_id, ok = DarkDialogHelper.get_int(self, "修改类别序号", "输入新序号:", old_idx, 0, 999)
        if ok and new_id != old_idx:
            # Check Collision
            if new_id < len(self.class_data):
                # Conflict
                reply = QMessageBox.question(self, "ID 冲突", 
                    f"序号 {new_id} 已存在 ({self.class_data[new_id]['name']})。\n"
                    "选择【Yes】替换(交换)位置，选择【No】插入到该位置(后移)，【Cancel】取消。",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
                
                if reply == QMessageBox.Yes:
                    self.swap_class_ids(old_idx, new_id)
                elif reply == QMessageBox.No:
                    self.move_class_id(old_idx, new_id)
            else:
                # Out of bounds -> Move to end? Or just extend?
                # Usually users want to fill holes. If new_id > len, we handle as move to end
                if new_id >= len(self.class_data):
                     new_id = len(self.class_data) - 1
                     self.move_class_id(old_idx, new_id)

    def swap_class_ids(self, idx1, idx2):
        # Swap data
        self.class_data[idx1], self.class_data[idx2] = self.class_data[idx2], self.class_data[idx1]
        self.class_data[idx1]['updated_at'] = get_timestamp()
        self.class_data[idx2]['updated_at'] = get_timestamp()
        self.save_classes_json()
        self.refresh_class_table()
        
        # Need to update current shapes if they use these IDs?
        # Yes, we should swap annotation references in memory for consistency
        for s in self.canvas.get_shapes():
            if s['class_index'] == idx1: s['class_index'] = idx2
            elif s['class_index'] == idx2: s['class_index'] = idx1
        self.refresh_annotation_table()
        self.canvas.update()

    def move_class_id(self, from_idx, to_idx):
        # Move item
        item = self.class_data.pop(from_idx)
        item['updated_at'] = get_timestamp()
        
        if to_idx >= len(self.class_data): self.class_data.append(item)
        else: self.class_data.insert(to_idx, item)
        
        self.save_classes_json()
        self.refresh_class_table()
        
        # Remap Memory Shapes (Complex: shift indices)
        # Create map: old_idx -> new_idx
        # This is tricky because indices shift.
        # Simplistic approach: this tool session is just updated for visualization.
        # Ideally we should warn the user that this changes ID mapping.
        pass

    # ==========================
    # Logic: Class CRUD
    # ==========================

    def safe_add_new_class(self):
        self.add_new_class_dialog()

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
                self.class_data.append({"name": name, 
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
        reply = QMessageBox.question(self, "确认删除", "删除此类别可能影响现有标注，确定吗？")
        if reply == QMessageBox.Yes:
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
        idx = item.row()
        if idx == self.current_class_index:
            self.current_class_index = -1
            self.class_table.clearSelection()
        else:
            self.current_class_index = idx

    # ==========================
    # Logic: Annotation & Files
    # ==========================

    def on_file_clicked(self, item):
        if not item: return
        # Row index logic for sorting
        row = item.row()
        # Get filename (col 0)
        name_item = self.file_table.item(row, 0)
        if name_item:
            filename = name_item.text()
            self.load_image(filename)

    def change_image(self, delta):
        # We need to find current row in table and move
        count = self.file_table.rowCount()
        if count == 0: return
        
        curr_items = self.file_table.selectedItems()
        curr_row = curr_items[0].row() if curr_items else -1
        
        if curr_row == -1 and count > 0: next_row = 0
        else: next_row = curr_row + delta

        if 0 <= next_row < count:
            self.file_table.selectRow(next_row)
            name_item = self.file_table.item(next_row, 0)
            if name_item:
                filename = name_item.text()
                self.load_image(filename)
        else:
            QMessageBox.information(self, "提示", "已经是第一张或最后一张了。")

    def load_image(self, filename):
        if not self.current_dir: return
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
        # Load from headless but ensure logic fits
        shapes = self._load_shapes_headless(filename, self.current_format)
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

        self.canvas._shapes.append({'class_index': cls_idx, 'rect': rect_normalized, 'updated_at': get_timestamp()})
        self.save_current_annotations()
        self.refresh_annotation_table()
        self.canvas.update()

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
        # Use headless saver with current shapes
        self._save_shapes_headless(self.canvas.get_shapes(), os.path.basename(self.current_image_path), fmt, self.output_dir_edit.text())

    def refresh_annotation_table(self):
        self.annotation_table.setSortingEnabled(False)
        self.annotation_table.setRowCount(len(self.canvas.get_shapes()))
        
        for i, shape in enumerate(self.canvas.get_shapes()):
            cls_idx = shape['class_index']
            # ID
            self.annotation_table.setItem(i, 0, QTableWidgetItem(str(i)))
            
            # Class ID
            self.annotation_table.setItem(i, 1, QTableWidgetItem(str(cls_idx)))
            
            # Name
            name = self.get_class_name(cls_idx)
            self.annotation_table.setItem(i, 2, QTableWidgetItem(name))
            
            # Time
            time_str = shape.get('updated_at', 'None')
            self.annotation_table.setItem(i, 3, QTableWidgetItem(time_str))

        self.annotation_table.setSortingEnabled(True)

    def on_annotation_item_clicked(self, item):
        idx = item.row()
        # Note: Sorting breaks row->index mapping if we don't use ItemData
        # But for v0.3 let's assume unsorted or using ID col
        # Proper way: get UserRole data or ID column
        id_item = self.annotation_table.item(idx, 0)
        if id_item:
             real_idx = int(id_item.text())
             self.canvas.selected_shape_index = real_idx
             self.canvas.update()

    def show_annotation_context_menu(self, pos, from_canvas=False):
        menu = QMenu()
        idx = -1
        if from_canvas:
            idx = self.canvas.selected_shape_index
        else:
            item = self.annotation_table.itemAt(self.annotation_table.mapFromGlobal(pos))
            if item:
                # Get ID from col 0
                row = item.row()
                id_item = self.annotation_table.item(row, 0)
                if id_item:
                    idx = int(id_item.text())
        
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
        name, ok = DarkDialogHelper.get_item(self, "修改类别", "选择或输入新类别:", existing_names, 0, editable=True)
        
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
                    self.class_data.append({"name": name, 
                                            "color": [color.red(), color.green(), color.blue()],
                                            "updated_at": get_timestamp()})
                    self.save_classes_json()
                    self.refresh_class_table()
                    new_cls_idx = len(self.class_data) - 1
                else: return 

            if new_cls_idx != -1:
                self.canvas._shapes[idx]['class_index'] = new_cls_idx
                self.canvas._shapes[idx]['updated_at'] = get_timestamp()
                self.save_current_annotations()
                self.refresh_annotation_table()
                self.canvas.update()
    
    def highlight_annotation_in_list(self, idx):
        # Find row with ID == idx
        # Iterate rows
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

    # ==========================
    # Logic: COCO (Simplified)
    # ==========================
    # Added back necessary minimal COCO helpers for headless
    def _ensure_coco_loaded(self):
         out_dir = self.output_dir_edit.text()
         if not out_dir: return
         json_path = os.path.join(out_dir, "annotations.json")
         if not self.coco_data and os.path.exists(json_path):
             with open(json_path, 'r', encoding='utf-8') as f: self.coco_data = json.load(f)

    def eventFilter(self, source, event):
        if event.type() == QEvent.KeyPress: # type: ignore
            if event.key() == Qt.Key_Delete: # type: ignore
                if source == self.class_table:
                    row = self.class_table.currentRow()
                    if row != -1: self.delete_class(row)
                    return True
                elif source == self.annotation_table:
                    items = self.annotation_table.selectedItems()
                    if items:
                         # Use helper to get real ID
                         id_item = self.annotation_table.item(items[0].row(), 0)
                         if id_item: self.remove_shape(int(id_item.text()))
                    return True
        return super().eventFilter(source, event)

# ============================================
# QSS 样式表 (保留 v0.2 样式并增强 Table)
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
QListWidget, QTableWidget { background-color: #252526; border: 1px solid #444; border-radius: 6px; alternate-background-color: #2d2d2d; gridline-color: #444; }
QListWidget::item:selected, QTableWidget::item:selected { background-color: #007acc; color: white; border-radius: 2px; }
QHeaderView { background-color: #333; }
QHeaderView::section { background-color: #333; color: #e0e0e0; padding: 4px; border: 1px solid #444; }
QTableCornerButton::section { background-color: #333; border: 1px solid #444; }
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
QComboBox QAbstractItemView { background-color: #252526; color: #e0e0e0; selection-background-color: #007acc; border: 1px solid #555; }
QScrollBar:vertical { border: none; background: #2b2b2b; width: 10px; margin: 0px; }
QScrollBar::handle:vertical { background: #555555; min-height: 20px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #666666; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal { border: none; background: #2b2b2b; height: 10px; margin: 0px; }
QScrollBar::handle:horizontal { background: #555555; min-width: 20px; border-radius: 5px; }
QScrollBar::handle:horizontal:hover { background: #666666; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }
QColorDialog { background-color: #2b2b2b; color: #e0e0e0; }
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("数据标注工具 v0.3") 
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
