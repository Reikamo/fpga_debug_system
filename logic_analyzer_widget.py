# logic_analyzer_widget.py

import sys
import numpy as np
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout,
                             QHBoxLayout, QLabel, QCheckBox, QDialog, QFormLayout,
                             QLineEdit, QDialogButtonBox, QFileDialog, QInputDialog, QComboBox,
                             QScrollArea, QSplitter, QGroupBox, QDoubleSpinBox, QSpinBox, QTextEdit,
                             QGridLayout, QListWidget, QListWidgetItem, QMessageBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView) # 导入 QAbstractItemView
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import struct
from protocol import PacketType # 引入协议定义
from communication_manager import CommunicationManager # 导入通信管理器基类
import sys

# --- [新导入] ---
# 导入我们新创建的、包含解析器逻辑和波形叠加窗口的文件
try:
    from software_parser_window import SoftwareParserWindow 
except ImportError as e: # <--- 修改点 1：捕获异常为 e
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print(f"!!! 捕获到导入错误: {e}") # <--- 修改点 2：打印详细错误
    print("!!! Python 路径:", sys.path) # <--- 修改点 3：打印 Python 路径
    print("!!! 警告：无法导入 software_parser_window.py。协议解析功能将不可用。")
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    SoftwareParserWindow = None # 定义一个占位符

# --- 辅助函数：format_time_ns (保持不变) ---
def format_time_ns(cycles: int, clock_freq: int = 50_000_000) -> str:
    """将时钟周期数格式化为带单位的时间字符串 (ns, us, ms, s)"""
    if clock_freq <= 0 or cycles < 0:
        return "N/A"
    if cycles == 0:
        return "0 ns"

    time_sec = cycles / clock_freq
    if time_sec < 1e-6:
        return f"{time_sec * 1e9:.2f} ns"
    elif time_sec < 1e-3:
        return f"{time_sec * 1e6:.2f} us"
    elif time_sec < 1:
        return f"{time_sec * 1e3:.2f} ms"
    else:
        return f"{time_sec:.2f} s"

# --- 类: ChannelSelectionDialog (保持不变) ---
class ChannelSelectionDialog(QDialog):
    """
    通道选择对话框。
    用于从可用信号列表中选择最多16个通道，并生成对应的掩码。
    """
    def __init__(self, available_signals, initial_mask=0, parent=None):
        """
        初始化对话框。

        Args:
            available_signals (list): 所有可选信号名称的列表。
            initial_mask (int): 初始选中的通道掩码。
            parent (QWidget, optional): 父控件。
        """
        super().__init__(parent)
        self.setWindowTitle("选择逻辑分析仪输入通道") 
        self.resize(300, 500) 
        self.available_signals = available_signals 
        self.selected_count = 0 
        self.max_selection = 16 
        self.checkboxes = [] 

        layout = QVBoxLayout(self) 

        selected_initially = bin(initial_mask).count('1')
        self.count_label = QLabel(f"已选: {selected_initially} / {self.max_selection}")
        layout.addWidget(self.count_label)

        list_widget = QListWidget()
        layout.addWidget(list_widget)

        num_signals = len(self.available_signals)
        for i, signal_name in enumerate(self.available_signals):
            item = QListWidgetItem(list_widget)
            checkbox = QCheckBox(signal_name)
            # 根据初始掩码设置复选框状态 (注意位序与列表索引关系)
            # 高位对应列表第一个信号, 所以掩码位索引是 num_signals - 1 - i
            if (initial_mask >> (num_signals - 1 - i)) & 1:
                checkbox.setChecked(True)
            checkbox.stateChanged.connect(self.update_selection_count) 
            list_widget.addItem(item)
            list_widget.setItemWidget(item, checkbox) 
            self.checkboxes.append(checkbox)

        self.update_selection_count() 

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept) 
        buttons.rejected.connect(self.reject) 
        layout.addWidget(buttons)

    def update_selection_count(self):
        """更新已选通道计数，并根据是否达到上限来启用/禁用未选中的复选框"""
        self.selected_count = sum(1 for cb in self.checkboxes if cb.isChecked())
        self.count_label.setText(f"已选: {self.selected_count} / {self.max_selection}")

        # 如果已选通道数达到上限，则禁用所有未选中的复选框
        # 否则全部启用
        enabled = self.selected_count < self.max_selection
        for cb in self.checkboxes:
            if not cb.isChecked():
                cb.setEnabled(enabled)

    def get_selection_mask_and_names(self):
        """
        获取用户选择的通道掩码和对应的信号名称列表。

        Returns:
            tuple: (mask, selected_names)
                mask (int): 根据选中的信号生成对应的位掩码 (高位对应列表第一个信号)。
                selected_names (list): 选中的信号名称列表 (最多16个)。
        """
        mask = 0
        selected_names = []
        num_signals = len(self.available_signals)
        for i, cb in enumerate(self.checkboxes):
            if cb.isChecked():
                # 计算掩码位 (高位对应列表第一个信号)
                mask |= (1 << (num_signals - 1 - i))
                selected_names.append(cb.text())
        # 返回掩码和最多前16个选中的名称
        return mask, selected_names[:self.max_selection]

# --- 类: WaveformWidget (保持不变) ---
# [!] 注意：这个 WaveformWidget 是 logic_analyzer_widget.py 文件内部的
# 它与 software_parser_window.py 内部的 _ParserWaveformWidget 是不同的类
class WaveformWidget(QWidget):
    """
    波形显示控件。
    用于绘制逻辑分析仪捕获的数字波形，支持缩放、平移和光标测量。
    固定显示16个通道，标签从 CH15 到 CH0。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.channels = 16 # 固定显示16通道
        self.display_depth = 256 # 当前显示的数据深度 (采样点数)
        # 存储波形数据 (每个通道一个列表), 索引 0 对应 FPGA 的 bit 0 (最低位)
        # 但显示时，最高行 (row_index=0) 对应 CH15 (data_index=15)
        self.data = [[] for _ in range(self.channels)]
        # 通道显示名称 (索引 0 对应最高行 CH15)
        self.display_names = [f"CH{15-i}" for i in range(self.channels)]

        self.setMinimumSize(800, 400) # 设置最小尺寸

        # --- 视图控制参数 ---
        self.offset = 0.0 # 水平滚动偏移量 (单位: 采样点)
        self.zoom = 12.0 # 水平缩放系数 (像素/采样点)
        self.x_offset = 80.0 # 左侧标签区域宽度 (像素)
        self._dragging_divider = False # 是否正在拖动分隔条
        self._divider_hit_margin = 5 # 分隔条的可点击范围 (像素)

        # --- 光标控制参数 ---
        self.cursor_enabled = True # 是否启用光标
        self.cursor1_pos = 0 # 光标1的位置 (单位: 采样点)
        self.cursor2_pos = 10 # 光标2的位置 (单位: 采样点)
        self._dragging_cursor = None # 正在拖动的光标编号 (1 或 2)，None表示未拖动
        self._dragging_waveform = False # 是否正在拖动波形区域 (右键平移)
        self._last_mouse_x = 0 # 上一次鼠标事件的X坐标

        # --- 时间刻度参数 ---
        self.period = 20.0 # 每个采样点的周期 (由采样频率决定, 单位由 unit 决定, 默认对应 50MHz)
        self.unit = 'ns' # 周期的单位

    def update_channel_names(self, selected_names: list):
        """
        更新通道的显示名称。

        Args:
            selected_names (list): 用户选择的信号名称列表 (最多16个)。
                                   [!! 规则 !!]: 此列表是按掩码位从高到低排序的。
                                   selected_names[0] = 选中的最高位信号 (e.g., "i2c_scl")
                                   selected_names[15] = 选中的最低位信号 (e.g., "la_in[0]")
        """
        
        # self.display_names 索引 0 对应 CH15 (最顶行)
        # self.display_names 索引 15 对应 CH0 (最底行)
        new_names = ["---"] * self.channels
        
        # [!! FPGA 规则 !!]
        # FPGA 从 *最低位* 信号开始扫描，映射到 word[0], word[1], ...
        # word[0] -> data[0] -> CH0 (最底行, display_names[15])
        # word[1] -> data[1] -> CH1 (倒数第二行, display_names[14])
        # ...
        # word[15] -> data[15] -> CH15 (最顶行, display_names[0])
        
        # [!! 软件绑定 !!]
        # 我们需要将 selected_names (高到低) 反转，得到 FPGA 的 word 顺序 (低到高)
        
        # e.g., selected_names = ["i2c_scl", "i2c_sda"] (高到低)
        #      signals_low_to_high = ["i2c_sda", "i2c_scl"] (低到高)
        signals_low_to_high = list(reversed(selected_names))
        
        num_selected = len(signals_low_to_high)

        for i in range(min(num_selected, self.channels)):
            # i = 0: 对应 FPGA word[0] (e.g., "i2c_sda")
            #      应映射到 CH0 (最底行)
            #      CH0 对应 display_names[15] (即 15 - 0)
            
            # i = 1: 对应 FPGA word[1] (e.g., "i2c_scl")
            #      应映射到 CH1 (倒数第二行)
            #      CH1 对应 display_names[14] (即 15 - 1)
            
            new_names_index = 15 - i
            new_names[new_names_index] = signals_low_to_high[i]
            
        self.display_names = new_names
        self.update() # 触发重绘

    def paintEvent(self, event):
        """绘制波形界面"""
        rect = self.rect()
        painter = QPainter(self)
        painter.fillRect(rect, Qt.black) # 黑色背景

        w, h = rect.width(), self.height()
        if self.channels <= 0: return # 防止除零错误
        row_h = h / self.channels # 每个通道的高度

        int_x_offset = int(self.x_offset) # 标签区宽度取整
        plot_area_width = w - int_x_offset # 波形绘制区域宽度
        y_offset = 10 # 顶部留白，避免波形贴顶

        colors = [QColor(0, 255, 0, 127)] # 波形颜色 (绿色半透明)
        painter.setPen(QPen(Qt.white)) # 默认画笔颜色
        font = QFont("Consolas", 8) # 使用等宽字体
        painter.setFont(font)
        fm = QFontMetrics(font) # 用于计算文本宽度
        max_name_width = int_x_offset - 10 # 标签最大显示宽度 (留点边距)

        # --- 绘制通道标签和波形 ---
        for row_index in range(self.channels): # row_index 从 0 到 15
            y_base = int((row_index + 0.5) * row_h) + y_offset # 通道中心Y坐标

            # 绘制通道标签 (格式: CH{15-i}: {信号名})
            painter.setPen(QPen(Qt.white)) # 标签使用白色
            # display_names 的索引 0 对应 CH15, 所以直接用 row_index
            name_from_list = self.display_names[row_index] if row_index < len(self.display_names) else "---"
            label_text = f"CH{15-row_index}: {name_from_list}" # 组合标签文本 (CH15, CH14, ...)
            # 如果标签过长，进行省略 (...)
            name_to_draw = fm.elidedText(label_text, Qt.ElideRight, max_name_width)
            painter.drawText(5, y_base + 4, name_to_draw) # 绘制标签 (稍微向下调整)

            # 绘制波形
            # 数据索引 data_index 对应 FPGA bit 位 (0 到 15)
            # row_index=0 (CH15) 对应 data_index=15
            # row_index=1 (CH14) 对应 data_index=14
            # ...
            data_index = 15 - row_index
            painter.setPen(QPen(colors[data_index % len(colors)], 2)) # 设置波形颜色

            # 检查数据是否存在且有效
            if data_index < 0 or data_index >= len(self.data) or not self.data[data_index]:
                 continue # 如果数据索引无效或该通道无数据，则跳过

            path = QPainterPath() # 用于绘制波形路径

            # 计算需要绘制的数据索引范围 (根据视图偏移和缩放)
            start_idx = max(0, int(self.offset - (int_x_offset / self.zoom if self.zoom > 1e-6 else 0)))
            end_idx = min(self.display_depth, int(self.offset + (plot_area_width / self.zoom if self.zoom > 1e-6 else self.display_depth)) + 2)


            # 如果起始索引超出范围或无效，则跳过此通道
            current_channel_data = self.data[data_index]
            if start_idx >= end_idx or start_idx >= len(current_channel_data):
                 continue

            try:
                # 计算第一个点的屏幕坐标
                y_start = y_base - int(current_channel_data[start_idx] * (row_h * 0.4)) # 高低电平偏移 (1 向上, 0 向下)
                x_start = int(int_x_offset + (start_idx - self.offset) * self.zoom)
                path.moveTo(x_start, y_start) # 移动到路径起点

                # 遍历后续点，绘制路径
                for idx in range(start_idx + 1, min(end_idx, len(current_channel_data))):
                    x = int(int_x_offset + (idx - self.offset) * self.zoom) # 计算X坐标
                    val = current_channel_data[idx] # 当前点的值 (0或1)
                    prev_val = current_channel_data[idx-1] # 上一个点的值

                    y_prev = y_base - int(prev_val * (row_h * 0.4)) # 上一个点的Y坐标
                    y_curr = y_base - int(val * (row_h * 0.4)) # 当前点的Y坐标

                    # 如果电平发生跳变，先画一条垂直线段到跳变点
                    if val != prev_val:
                        path.lineTo(x, y_prev)
                    # 再画一条水平线段到当前点
                    path.lineTo(x, y_curr)

                # --- 设置剪切区域并绘制路径 ---
                painter.save() # 保存绘制状态
                # 定义剪切区域，限制绘制在波形区域内
                clip_rect = QRect(int_x_offset, 0, plot_area_width, h)
                painter.setClipRect(clip_rect)
                painter.drawPath(path) # 绘制波形路径
                painter.restore() # 恢复绘制状态 (移除剪切)

            except IndexError:
                # 捕获潜在的索引越界错误 (理论上前面已处理，但保留以防万一)
                print(f"绘图索引错误: data_index={data_index}, start={start_idx}, end={end_idx}, idx={idx if 'idx' in locals() else 'unknown'}, len={len(current_channel_data)}")
                continue
            except Exception as e:
                print(f"绘制通道 {data_index} 时发生未知错误: {e}")
                continue


        # --- 绘制网格、时间刻度、光标、分隔条 ---
        # 绘制垂直网格线和时间刻度 (只在波形区域内绘制)
        time_scale_step = 1 # 默认每隔1个采样点画线
        min_pixels_per_step = 10 # 网格线之间最小像素间隔
        if self.zoom < min_pixels_per_step:
            time_scale_step = int(np.ceil(min_pixels_per_step / self.zoom))

        grid_pen = QPen(QColor(180, 180, 180, 80)) # 灰色半透明网格线
        time_text_pen = QPen(QColor(180, 180, 180, 255)) # 不透明时间文本

        first_visible_idx = max(0, int(np.floor(self.offset)))
        last_visible_idx = min(self.display_depth, int(np.ceil(self.offset + plot_area_width / self.zoom if self.zoom > 1e-6 else self.display_depth)))

        # 找到第一个可见的刻度点
        start_grid_idx = int(np.ceil(first_visible_idx / time_scale_step)) * time_scale_step

        for i in range(start_grid_idx, last_visible_idx + 1, time_scale_step):
            x = int(int_x_offset + (i - self.offset) * self.zoom)
            if int_x_offset <= x <= w: # 只绘制可见范围内的线
                # 绘制灰色网格线
                painter.setPen(grid_pen)
                painter.drawLine(x, 0, x, h - 10) # 底部留出空间给刻度
                # 绘制时间刻度文本 (仅当缩放级别足够大时显示每个刻度)
                if self.zoom >= 3: # 缩放较大时才显示时间刻度
                    painter.setPen(time_text_pen)
                    # 时间刻度 = 采样点索引 * 每个采样点的时间周期
                    time_val = i * self.period
                    time_str = f"{time_val:.1f}{self.unit}" # 格式化时间
                    # 避免文本重叠
                    text_width = fm.width(time_str)
                    if self.zoom * time_scale_step > text_width * 1.5: # 确保有足够空间
                        painter.drawText(x - text_width // 2, h - 2, time_str) # 居中显示

        # 绘制光标 (如果启用且有数据)
        if self.cursor_enabled and self.data and any(d for d in self.data if d):
            pen = QPen(Qt.yellow, 2, Qt.DashLine) # 黄色虚线
            painter.setPen(pen)
            # 绘制两个光标线
            valid_cursor = False
            for cursor_pos in [self.cursor1_pos, self.cursor2_pos]:
                cursor_x = int(int_x_offset + (cursor_pos - self.offset) * self.zoom)
                # 只绘制在波形区域内的部分
                if int_x_offset <= cursor_x <= w:
                    painter.drawLine(cursor_x, 0, cursor_x, h)
                    valid_cursor = True # 至少有一个光标可见

            # 计算并显示光标间的时间差 (只有当至少一个光标可见时)
            if valid_cursor:
                delta = abs(self.cursor2_pos - self.cursor1_pos) # 采样点差值
                delta_time = delta * self.period # 时间差 = 采样点数 * 每个点的时间
                # 根据时间差大小选择合适的单位显示
                if self.unit == 'ns' and delta_time >= 1000:
                    delta_time /= 1000; unit_display = 'us'
                elif self.unit == 'us' and delta_time >= 1000:
                    delta_time /= 1000; unit_display = 'ms'
                elif self.unit == 'ms' and delta_time >= 1000:
                    delta_time /= 1000; unit_display = 's'
                else:
                    unit_display = self.unit

                painter.setPen(QPen(Qt.yellow)) # 黄色实线文本
                painter.drawText(int_x_offset + 20, 20, f"ΔX: {delta} samples, Δt: {delta_time:.3f} {unit_display}")

        # 绘制左侧标签区和波形区的分隔线
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.drawLine(int_x_offset, 0, int_x_offset, h)

    def wheelEvent(self, event):
        """处理鼠标滚轮事件以实现缩放"""
        int_x_offset = int(self.x_offset)
        # 如果滚轮在标签区，则忽略
        if event.pos().x() < int_x_offset: return

        delta = event.angleDelta().y() # 获取滚轮滚动方向和幅度
        factor = 1.2 if delta > 0 else (1/1.2) # 计算缩放因子
        old_zoom = self.zoom
        new_zoom = max(0.1, min(200.0, self.zoom * factor)) # 计算新缩放级别并限制范围 (最小0.1)

        # 检查缩放是否有实际变化
        if abs(new_zoom - old_zoom) < 1e-6:
             return # 缩放级别未变，无需继续处理

        self.zoom = new_zoom

        # --- 以鼠标指针位置为中心进行缩放 ---
        mouse_x_in_plot = event.pos().x() - int_x_offset # 鼠标在波形区的相对X坐标
        if mouse_x_in_plot >= 0:
            # 计算鼠标指向的采样点在缩放前后的偏移量变化
            mouse_offset_in_samples_before = mouse_x_in_plot / old_zoom if old_zoom > 1e-6 else 0
            mouse_offset_in_samples_after = mouse_x_in_plot / self.zoom if self.zoom > 1e-6 else 0

            # 调整视图偏移量以保持鼠标指向的采样点位置不变
            self.offset += mouse_offset_in_samples_before - mouse_offset_in_samples_after

            # 限制偏移量范围，防止滚动出界
            view_width_samples = (self.width() - int_x_offset) / self.zoom if self.zoom > 1e-6 else self.display_depth
            max_offset = self.display_depth - view_width_samples
            # 确保 max_offset 不小于 0
            self.offset = max(0, min(max_offset if max_offset > 0 else 0, self.offset))

        self.update() # 触发重绘

    def mousePressEvent(self, event):
        """处理鼠标按下事件 (拖动分隔条、右键平移、左键拖动光标)"""
        int_x_offset = int(self.x_offset)
        # 按下左键且靠近分隔条: 开始拖动分隔条
        if event.button() == Qt.LeftButton and abs(event.pos().x() - int_x_offset) <= self._divider_hit_margin:
            self._dragging_divider = True
            self._last_mouse_x = event.pos().x()
            self.setCursor(Qt.SplitHCursor) # 设置鼠标样式为水平分割
        # 在波形区按下
        elif event.pos().x() >= int_x_offset:
            self._last_mouse_x = event.pos().x()
            # 按下右键: 开始平移波形
            if event.button() == Qt.RightButton:
                self.setCursor(Qt.ClosedHandCursor) # 设置鼠标样式为抓手
                self._dragging_waveform = True
            # 按下左键且光标启用: 检查是否点中光标，开始拖动光标
            elif event.button() == Qt.LeftButton and self.cursor_enabled:
                x_click_in_plot = event.pos().x() - int_x_offset # 点击位置相对波形区的X坐标
                # 计算光标1和光标2的屏幕X坐标 (加上标签区偏移)
                cursor1_screen_x = int_x_offset + (self.cursor1_pos - self.offset) * self.zoom
                cursor2_screen_x = int_x_offset + (self.cursor2_pos - self.offset) * self.zoom
                # 判断点击位置是否靠近某个光标 (使用屏幕坐标判断)
                if abs(event.pos().x() - cursor1_screen_x) < 10: # 10像素容差
                    self._dragging_cursor = 1
                elif abs(event.pos().x() - cursor2_screen_x) < 10:
                    self._dragging_cursor = 2
                else:
                    self._dragging_cursor = None # 未点中光标
        else: # 在标签区按下，重置所有拖动状态
            self._dragging_divider = False
            self._dragging_waveform = False
            self._dragging_cursor = None

    def mouseMoveEvent(self, event):
        """处理鼠标移动事件 (执行拖动操作)"""
        int_x_offset = int(self.x_offset)
        effective_zoom = max(1e-6, self.zoom) # 避免除零

        # 拖动分隔条
        if self._dragging_divider:
            dx = event.pos().x() - self._last_mouse_x # 计算鼠标水平移动距离
            new_offset = self.x_offset + dx # 计算新的标签区宽度
            # 限制标签区宽度范围 (例如 50 到 300 像素)
            self.x_offset = max(50.0, min(300.0, new_offset))
            self._last_mouse_x = event.pos().x()
            self.update()
        # 拖动波形 (右键平移)
        elif self._dragging_waveform:
            dx = event.pos().x() - self._last_mouse_x
            self.offset -= dx / effective_zoom # 根据鼠标移动距离和缩放级别调整视图偏移量

            # 限制偏移量范围
            view_width_samples = (self.width() - int_x_offset) / effective_zoom
            max_offset = self.display_depth - view_width_samples
            self.offset = max(0, min(max_offset if max_offset > 0 else 0, self.offset))
            self._last_mouse_x = event.pos().x()
            self.update()
        # 拖动光标
        elif self._dragging_cursor is not None:
            if event.pos().x() >= int_x_offset: # 只在波形区内拖动有效
                # 将鼠标屏幕X坐标转换回采样点索引
                pos = self.offset + (event.pos().x() - int_x_offset) / effective_zoom
                # 限制光标位置在有效范围内 [0, display_depth - 1]
                pos = max(0, min(self.display_depth - 1, int(round(pos)))) # 四舍五入到最近的采样点
                # 更新对应光标的位置
                if self._dragging_cursor == 1: self.cursor1_pos = pos
                elif self._dragging_cursor == 2: self.cursor2_pos = pos
                self.update()

    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件 (结束拖动操作)"""
        if self._dragging_divider or self._dragging_waveform or self._dragging_cursor is not None:
            # 重置所有拖动状态
            self._dragging_divider = False
            self._dragging_waveform = False
            self._dragging_cursor = None
            self.setCursor(Qt.ArrowCursor) # 恢复默认鼠标样式

    def update_data(self, new_data, new_depth):
        """
        更新波形数据和显示深度。
        """
        self.display_depth = max(1, new_depth) # 确保深度至少为 1
        # 确保 new_data 至少有 self.channels 个通道，不足则补空列表
        while len(new_data) < self.channels:
             new_data.append([])
        self.data = new_data[:self.channels] # 只取前 self.channels 个通道的数据

        # 确保光标位置不超出新的数据深度范围 [0, depth-1]
        self.cursor1_pos = max(0, min(self.cursor1_pos, self.display_depth - 1))
        self.cursor2_pos = max(0, min(self.cursor2_pos, self.display_depth - 1))
        # 限制视图偏移量
        effective_zoom = max(1e-6, self.zoom)
        view_width_samples = (self.width() - self.x_offset) / effective_zoom
        max_offset = self.display_depth - view_width_samples
        self.offset = max(0, min(self.offset, max_offset if max_offset > 0 else 0))

        self.update()

    def clear_data(self):
        """清空所有通道的波形数据"""
        self.data = [[] for _ in range(self.channels)]
        self.update()

    def zoom_in(self):
        """放大波形 (以视图中心为焦点)"""
        center_sample = self.offset + (self.width() - self.x_offset) / (2 * self.zoom) if self.zoom > 1e-6 else self.offset
        new_zoom = min(200.0, self.zoom * 1.2) # 限制最大缩放级别
        if abs(new_zoom - self.zoom) > 1e-6:
             # 调整偏移以保持中心点不变
             self.offset = center_sample - (self.width() - self.x_offset) / (2 * new_zoom)
             self.zoom = new_zoom
             # 限制偏移
             view_width_samples = (self.width() - self.x_offset) / self.zoom
             max_offset = self.display_depth - view_width_samples
             self.offset = max(0, min(self.offset, max_offset if max_offset > 0 else 0))
             self.update()


    def zoom_out(self):
        """缩小波形 (以视图中心为焦点)"""
        center_sample = self.offset + (self.width() - self.x_offset) / (2 * self.zoom) if self.zoom > 1e-6 else self.offset
        new_zoom = max(0.1, self.zoom / 1.2) # 限制最小缩放级别
        if abs(new_zoom - self.zoom) > 1e-6:
             self.offset = center_sample - (self.width() - self.x_offset) / (2 * new_zoom)
             self.zoom = new_zoom
             # 限制偏移
             view_width_samples = (self.width() - self.x_offset) / self.zoom
             max_offset = self.display_depth - view_width_samples
             self.offset = max(0, min(self.offset, max_offset if max_offset > 0 else 0))
             self.update()


    def reset_offset(self):
        """重置视图偏移和缩放级别"""
        self.offset = 0
        self.zoom = 12 # 恢复默认缩放级别
        self.update()

    def set_period(self, period, unit_str):
        """
        设置每个采样点的时间周期和单位，用于光标时间差计算和显示。
        """
        self.period = max(0, period) # 周期不能为负
        self.unit = unit_str if unit_str else '?'
        self.update() # 重绘以更新光标时间差显示


# --- [新] 类: _LogicAnalyzerSettingsWidget (右侧配置栏) ---
class _LogicAnalyzerSettingsWidget(QWidget):
    """
    逻辑分析仪的右侧配置面板 (QWidget)。
    这个控件只包含UI元素，逻辑由 LogicAnalyzerController 处理。
    """
    log_message = pyqtSignal(str) # 日志信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # --- 信号列表 (保持不变) ---
        self.available_signals = [
            "i2c_scl", "i2c_sda", "uart_tx", "uart_rx", "spi_cs", "spi_sclk", "spi_mosi", "spi_miso",
            "pwm1", "pwm2", "can_tx", "can_rx",
            "dout[7]", "dout[6]", "dout[5]", "dout[4]", "dout[3]", "dout[2]", "dout[1]", "dout[0]",
            "la_in[7]", "la_in[6]", "la_in[5]", "la_in[4]", "la_in[3]", "la_in[2]", "la_in[1]", "la_in[0]"
        ]
        
        self.init_maps()
        self.init_ui()

    def init_maps(self):
        """初始化各种下拉框选项到协议值的映射字典"""
        self.trigger_mode_map = {"低电平": 0, "高电平": 1, "上升沿": 2, "下降沿": 3, "边沿": 4, "立即触发": 5}
        self.sampling_freq_map = { "500Hz":0, "1kHz":1, "2.5kHz":2, "5kHz":3, "10kHz":4, "25kHz":5, "50kHz":6, "100kHz":7, "250kHz":8, "500kHz":9, "1MHz":10, "2.5MHz":11, "5MHz":12, "10MHz":13, "25MHz":14, "50MHz":15}
        self.sampling_depth_map = {"256":0, "512":1, "1024":2, "2048":3}

    def init_ui(self):
        """创建和布局界面控件"""
        main_layout = QVBoxLayout(self) # 主垂直布局
        main_layout.setContentsMargins(5, 5, 5, 5) # 紧凑布局
        main_layout.setSpacing(10)

        # --- 参数配置区域 ---
        config_group = QGroupBox("参数配置")
        config_layout = QGridLayout(config_group) 
        config_layout.addWidget(QLabel("触发通道 (已选):"), 0, 0)
        self.trigger_bit = QComboBox(); self.trigger_bit.addItems(["无"]) 
        config_layout.addWidget(self.trigger_bit, 0, 1)
        
        config_layout.addWidget(QLabel("触发方式:"), 1, 0)
        self.trigger = QComboBox(); self.trigger.addItems(self.trigger_mode_map.keys())
        config_layout.addWidget(self.trigger, 1, 1)
        
        config_layout.addWidget(QLabel("采样频率:"), 2, 0)
        self.frequency = QComboBox(); self.frequency.addItems(self.sampling_freq_map.keys()); self.frequency.setCurrentIndex(15) 
        config_layout.addWidget(self.frequency, 2, 1)
        
        config_layout.addWidget(QLabel("采样深度:"), 3, 0)
        self.data_depth = QComboBox(); self.data_depth.addItems(self.sampling_depth_map.keys())
        config_layout.addWidget(self.data_depth, 3, 1)

        self.select_channels_btn = QPushButton("选择输入通道")
        config_layout.addWidget(self.select_channels_btn, 4, 0, 1, 2)
        
        self.apply_config_btn = QPushButton("应用配置")
        config_layout.addWidget(self.apply_config_btn, 5, 0, 1, 2)
        
        main_layout.addWidget(config_group)

        # --- 采集控制区域 ---
        control_group = QGroupBox("采集控制")
        control_layout = QGridLayout(control_group) # 使用网格
        self.enable_btn = QPushButton("使能开关"); self.enable_btn.setCheckable(True) 
        self.go_btn = QPushButton("单次采集") 
        self.timeout_btn = QPushButton("超时控制"); self.timeout_btn.setCheckable(True) 
        self.clear_waveform_btn = QPushButton("清空波形") 
        
        control_layout.addWidget(self.enable_btn, 0, 0)
        control_layout.addWidget(self.go_btn, 0, 1)
        control_layout.addWidget(self.timeout_btn, 1, 0)
        control_layout.addWidget(self.clear_waveform_btn, 1, 1)
        
        main_layout.addWidget(control_group)

        # --- 视图控制 (新) ---
        view_group = QGroupBox("视图控制")
        view_layout = QGridLayout(view_group)
        self.zoom_in_button = QPushButton("放大") 
        self.zoom_out_button = QPushButton("缩小") 
        self.reset_button = QPushButton("复位视图")
        self.open_parser_btn = QPushButton("协议解析") 
        self.open_parser_btn.setToolTip("使用已捕获的数据打开软件协议解析器")
        
        view_layout.addWidget(self.zoom_in_button, 0, 0)
        view_layout.addWidget(self.zoom_out_button, 0, 1)
        view_layout.addWidget(self.reset_button, 1, 0)
        view_layout.addWidget(self.open_parser_btn, 1, 1)
        
        main_layout.addWidget(view_group)


        # --- 数字频率测量区域 ---
        freq_measure_group = QGroupBox("数字频率测量")
        freq_measure_layout = QGridLayout(freq_measure_group)
        freq_measure_layout.addWidget(QLabel("测量通道:"), 0, 0)
        self.dig_freq_channel_combo = QComboBox()
        self.dig_freq_channel_combo.addItems(self.available_signals)
        freq_measure_layout.addWidget(self.dig_freq_channel_combo, 0, 1, 1, 2) 
        
        self.dig_freq_enable_check = QCheckBox("使能测量")
        freq_measure_layout.addWidget(self.dig_freq_enable_check, 1, 0)
        self.send_dig_freq_config_btn = QPushButton("发送配置")
        freq_measure_layout.addWidget(self.send_dig_freq_config_btn, 1, 1, 1, 2)
        
        freq_measure_layout.addWidget(QLabel("高电平时间:"), 2, 0)
        self.dig_freq_high_time_display = QLineEdit("N/A"); self.dig_freq_high_time_display.setReadOnly(True)
        freq_measure_layout.addWidget(self.dig_freq_high_time_display, 2, 1, 1, 2)
        
        freq_measure_layout.addWidget(QLabel("低电平时间:"), 3, 0)
        self.dig_freq_low_time_display = QLineEdit("N/A"); self.dig_freq_low_time_display.setReadOnly(True)
        freq_measure_layout.addWidget(self.dig_freq_low_time_display, 3, 1, 1, 2)
        
        freq_measure_layout.addWidget(QLabel("总周期时间:"), 4, 0)
        self.dig_freq_total_time_display = QLineEdit("N/A"); self.dig_freq_total_time_display.setReadOnly(True)
        freq_measure_layout.addWidget(self.dig_freq_total_time_display, 4, 1, 1, 2)
        
        freq_measure_layout.addWidget(QLabel("频率:"), 5, 0)
        self.dig_freq_frequency_display = QLineEdit("N/A"); self.dig_freq_frequency_display.setReadOnly(True)
        freq_measure_layout.addWidget(self.dig_freq_frequency_display, 5, 1, 1, 2)
        
        freq_measure_layout.setColumnStretch(1, 1)
        main_layout.addWidget(freq_measure_group)

        main_layout.addStretch() # 占满剩余空间


# --- [新] 类: LogicAnalyzerController (主控制器) ---
class LogicAnalyzerController(QObject):
    """
    逻辑分析仪的主控制器 (QObject)。
    它不直接显示，而是管理 DisplayWidget 和 SettingsWidget 之间的逻辑。
    """
    log_message = pyqtSignal(str) # 日志信号
    
    def __init__(self, comm_manager: CommunicationManager = None, parent=None):
        super().__init__(parent)
        self.comm_manager = comm_manager
        
        # --- 内部状态变量 ---
        self.is_enabled = False # LA 使能状态 (对应 F3 命令 bit 0)
        self.is_timeout_enabled = False # 超时控制使能状态 (对应 F3 命令 bit 2)
        self.data_buffer = bytearray() # 接收 LA 数据的缓冲区
        self.parser_window = None # 解析器窗口实例
        
        self.available_signals = [
            "i2c_scl", "i2c_sda", "uart_tx", "uart_rx", "spi_cs", "spi_sclk", "spi_mosi", "spi_miso",
            "pwm1", "pwm2", "can_tx", "can_rx", 
            "dout[7]", "dout[6]", "dout[5]", "dout[4]", "dout[3]", "dout[2]", "dout[1]", "dout[0]",
            "la_in[7]", "la_in[6]", "la_in[5]", "la_in[4]", "la_in[3]", "la_in[2]", "la_in[1]", "la_in[0]"
        ]
        
        # "待应用" (Pending) 配置
        self.la_sel_in_mask = 0 
        self.selected_signal_names = [] 
        
        # "已应用" (Active) 配置
        self.active_la_sel_in_mask = 0
        self.active_signal_names = []
        
        self.parser_window = None 

        # --- 实例化UI ---
        self.display_widget = WaveformWidget() # 中间显示区
        self.settings_widget = _LogicAnalyzerSettingsWidget() # 右侧配置区
        
        # --- 初始化UI状态 ---
        self.display_widget.update_channel_names(self.active_signal_names)
        self.freq_str_to_period_str() # 初始化时间刻度
        
        # --- 连接UI信号到控制器逻辑 ---
        self.connect_signals()

    # --- 提供给 MainWIndow 的接口 ---
    def get_display_widget(self) -> QWidget:
        """返回中间显示区的 QWidget"""
        return self.display_widget

    def get_settings_widget(self) -> QWidget:
        """返回右侧配置区的 QWidget"""
        return self.settings_widget

    def set_communication_manager(self, manager: CommunicationManager):
        """由 MainWindow 调用，设置或更新通信管理器实例"""
        self.comm_manager = manager

    # --- UI 信号连接 ---
    def connect_signals(self):
        """连接所有控件的信号到槽函数"""
        s = self.settings_widget # 引用右侧配置栏
        w = self.display_widget  # 引用中间显示栏
        
        # 1. 配置按钮
        s.apply_config_btn.clicked.connect(self.send_config_packet)
        s.select_channels_btn.clicked.connect(self.open_channel_selection_dialog)
        
        # 2. 控制按钮
        s.enable_btn.toggled.connect(self.send_control_packet) 
        s.go_btn.clicked.connect(lambda: self.send_control_packet(send_go=True))
        s.timeout_btn.toggled.connect(self.send_control_packet) 
        s.clear_waveform_btn.clicked.connect(self.clear_display_and_buffer) 
        
        # 3. 视图控制按钮
        s.zoom_in_button.clicked.connect(w.zoom_in)
        s.zoom_out_button.clicked.connect(w.zoom_out)
        s.reset_button.clicked.connect(w.reset_offset)
        
        # 4. 频率测量
        s.send_dig_freq_config_btn.clicked.connect(self.send_dig_freq_config)
        
        # 5. 协议解析
        s.open_parser_btn.clicked.connect(self.open_parser_window)
        
        # 6. 将 settings_widget 的日志信号转发出去
        s.log_message.connect(self.log_message)


    # --- 核心逻辑 (从原 LogicAnalyzerWidget 迁移而来) ---

    @pyqtSlot()
    def open_parser_window(self):
        """打开协议解析器弹出窗口，并传递所需数据 (非模态)"""
        
        if SoftwareParserWindow is None:
            self.log_message.emit("❌ 无法打开解析器：software_parser_window.py 加载失败。")
            QMessageBox.critical(self.settings_widget, "导入错误", "协议解析器模块加载失败，请检查文件。")
            return
            
        if not self.display_widget.data or not any(d for d in self.display_widget.data):
            self.log_message.emit("⚠️ 请先使用逻辑分析仪捕获数据，然后再打开解析器。")
            QMessageBox.warning(self.settings_widget, "无数据", "请先捕获波形数据，然后再打开协议解析窗口。")
            return

        if not self.active_signal_names:
            self.log_message.emit("⚠️ 无法打开解析器：无已应用的通道配置。")
            QMessageBox.warning(self.settings_widget, "无配置", "请先选择通道并点击“应用配置”，然后再进行解析。")
            return

        current_freq_str = self.settings_widget.frequency.currentText()
        
        try:
            if self.parser_window is None:
                self.parser_window = SoftwareParserWindow(
                    la_data=self.display_widget.data, 
                    la_channel_names=self.active_signal_names,
                    la_sample_freq_str=current_freq_str, 
                    parent=None 
                )
                self.parser_window.log_message.connect(self.log_message) # 转发日志
            else:
                self.parser_window.update_la_data(
                    la_data=self.display_widget.data, 
                    la_channel_names=self.active_signal_names,
                    la_sample_freq_str=current_freq_str 
                )
            
            self.parser_window.show()
            self.parser_window.activateWindow() 
            self.parser_window.raise_() 
            
        except Exception as e:
            self.log_message.emit(f"❌ 打开协议解析窗口失败: {e}")
            QMessageBox.critical(self.settings_widget, "错误", f"打开解析器失败: {e}")

    @pyqtSlot()
    def open_channel_selection_dialog(self):
        """
        打开通道选择对话框。
        """
        s = self.settings_widget
        dialog = ChannelSelectionDialog(self.available_signals, self.active_la_sel_in_mask, s)
        
        if dialog.exec_() == QDialog.Accepted: 
            old_trigger_text = s.trigger_bit.currentText()

            self.la_sel_in_mask, self.selected_signal_names = dialog.get_selection_mask_and_names()
            num_selected = len(self.selected_signal_names)
            
            s.select_channels_btn.setText(f"已选 {num_selected} (待应用)")

            # 立即更新触发通道下拉框
            s.trigger_bit.clear()
            signals_low_to_high = list(reversed(self.selected_signal_names))
            
            if signals_low_to_high:
                dropdown_names = [f"CH{i}: {name}" for i, name in enumerate(signals_low_to_high)]
                s.trigger_bit.addItems(dropdown_names)
                
                new_index = s.trigger_bit.findText(old_trigger_text)
                if new_index != -1:
                    s.trigger_bit.setCurrentIndex(new_index) 
                elif s.trigger_bit.count() > 0:
                    s.trigger_bit.setCurrentIndex(0) 
            else:
                s.trigger_bit.addItems(["无"])
            
            self.log_message.emit(f"逻辑分析仪输入通道已更新 (待应用): {', '.join(self.selected_signal_names)}")

    @pyqtSlot()
    def clear_display_and_buffer(self):
        """清空数据缓冲区和波形显示"""
        self.data_buffer.clear() 
        self.display_widget.clear_data() 
        self.log_message.emit("波形显示和缓冲区已清空")

    @pyqtSlot()
    def send_config_packet(self):
        """
        发送逻辑分析仪配置命令 (F2)。
        """
        s = self.settings_widget
        
        if not self.comm_manager or not self.comm_manager.is_running():
            self.log_message.emit("❌ 请先启动通信会话")
            return
        self.data_buffer.clear() 

        la_sel_in = self.la_sel_in_mask
        
        current_trigger_text = s.trigger_bit.currentText()
        if ":" in current_trigger_text:
            current_trigger_text = current_trigger_text.split(":", 1)[1].strip()

        pending_signals_low_to_high = list(reversed(self.selected_signal_names))
        
        channel_val = 0 
        try:
            channel_val = pending_signals_low_to_high.index(current_trigger_text)
        except ValueError:
            if pending_signals_low_to_high:
                channel_val = 0 
            else:
                channel_val = 0 
        
        trig_val = s.trigger_mode_map.get(s.trigger.currentText(), 0)         
        freq_val = s.sampling_freq_map.get(s.frequency.currentText(), 0)     
        depth_val = s.sampling_depth_map.get(s.data_depth.currentText(), 0)    

        config_value = 0
        config_value |= (channel_val & 0b1111) << 9  # [12:9] 触发通道 (0-15), 0=CH0, 15=CH15
        config_value |= (trig_val    & 0b111)  << 6  # [8:6] 触发方式
        config_value |= (freq_val    & 0b1111) << 2  # [5:2] 采样频率
        config_value |= (depth_val   & 0b11)   << 0  # [1:0] 采样深度
        config_value |= (la_sel_in & ((1 << 28) - 1)) << 13 # [40:13] 28位通道掩码

        try:
            payload = struct.pack('>Q', config_value)[-6:]
        except struct.error as e:
            self.log_message.emit(f"❌ 打包 LA 配置数据时出错: {e}. Value: {config_value}")
            return

        packet = struct.pack('!B', PacketType.LOGIC_ANALYZER_CONFIG) + payload
        
        if self.comm_manager.send_packet(packet):
            self.log_message.emit("✅ 逻辑分析仪配置(F2)已发送")
            
            # --- 关键: 发送成功后，更新 "Active" 状态并刷新UI ---
            
            self.active_la_sel_in_mask = self.la_sel_in_mask
            self.active_signal_names = self.selected_signal_names.copy() 
            
            s.select_channels_btn.setText(f"已选 {len(self.active_signal_names)} 通道")

            self.freq_str_to_period_str()
            
            s.trigger_bit.clear()
            signals_low_to_high = list(reversed(self.active_signal_names))
            
            if signals_low_to_high:
                dropdown_names = [f"CH{i}: {name}" for i, name in enumerate(signals_low_to_high)]
                s.trigger_bit.addItems(dropdown_names)
                
                if 0 <= channel_val < len(signals_low_to_high):
                    s.trigger_bit.setCurrentIndex(channel_val)
                elif s.trigger_bit.count() > 0:
                    s.trigger_bit.setCurrentIndex(0) 
            else:
                s.trigger_bit.addItems(["无"])

            self.display_widget.update_channel_names(self.active_signal_names)

    @pyqtSlot(bool)
    def send_control_packet(self, send_go=False):
        """
        发送逻辑分析仪控制命令 (F3)。
        """
        s = self.settings_widget
        
        if not self.comm_manager or not self.comm_manager.is_running():
            self.log_message.emit("❌ 请先启动通信会话")
            if send_go:
                pass
            else: 
                 sender = self.sender()
                 if isinstance(sender, QCheckBox) or isinstance(sender, QPushButton):
                      sender.blockSignals(True)
                      sender.setChecked(not sender.isChecked()) # 恢复状态
                      sender.blockSignals(False)
            return

        # 更新内部状态
        self.is_enabled = s.enable_btn.isChecked()
        self.is_timeout_enabled = s.timeout_btn.isChecked()

        if self.is_enabled or send_go:
            self.data_buffer.clear()
            self.log_message.emit("数据缓冲区已清空，准备接收新数据帧...")

        control_byte = 0
        if self.is_enabled: control_byte |= (1 << 0)
        if send_go:         control_byte |= (1 << 1)
        if self.is_timeout_enabled: control_byte |= (1 << 2)

        payload = struct.pack('!B', control_byte)
        packet = struct.pack('!B', PacketType.LOGIC_ANALYZER_CONTROL) + payload # 包头 F3
        if self.comm_manager.send_packet(packet):
            self.log_message.emit(f"▶️ 发送逻辑分析仪控制命令(F3), 控制字节: 0x{control_byte:02X}")

    @pyqtSlot()
    def send_dig_freq_config(self):
        """发送数字频率测量配置命令 (DB)"""
        s = self.settings_widget
        
        if not self.comm_manager or not self.comm_manager.is_running():
            self.log_message.emit("❌ 请先启动通信会话")
            return

        channel_index_from_ui = s.dig_freq_channel_combo.currentIndex()
        if channel_index_from_ui < 0:
            QMessageBox.warning(s, "选择错误", "请先选择一个测量通道。")
            return

        dig_sel_value = 27 - channel_index_from_ui # 范围 0-27
        enable_state = 1 if s.dig_freq_enable_check.isChecked() else 0
        payload_byte = (dig_sel_value << 1) | enable_state
        payload = struct.pack('!B', payload_byte)

        packet = struct.pack('!B', PacketType.DEBUG_DIGITAL_FREQ_CONFIG) + payload # 包头 DB
        if self.comm_manager.send_packet(packet):
            state_text = "使能" if enable_state else "关闭"
            channel_name = s.dig_freq_channel_combo.currentText()
            self.log_message.emit(f"✅ 发送数字频率测量配置(DB): 通道={channel_name} (协议值={dig_sel_value}), 状态={state_text}")

    def handle_data(self, packet_type, payload, source_id=None):
        """
        处理从 FPGA 接收到的数据包。
        """
        s = self.settings_widget
        w = self.display_widget
        
        if packet_type == PacketType.LOGIC_ANALYZER_DATA:
            self.data_buffer.extend(payload) 
            try:
                depth_text = s.data_depth.currentText() 
                depth_val = s.sampling_depth_map.get(depth_text, 0) 
                depth_points = [256, 512, 1024, 2048][depth_val]
            except Exception:
                depth_points = 256 
            
            expected_len = 2 * depth_points 

            if len(self.data_buffer) >= expected_len:
                full_frame_data = self.data_buffer[:expected_len]
                self.data_buffer = self.data_buffer[expected_len:]
                try:
                    raw_data = np.frombuffer(full_frame_data, dtype='<u2')
                except ValueError as e:
                    self.log_message.emit(f"❌ 解析LA数据时出错: {e}, 数据长度: {len(full_frame_data)}")
                    return

                new_data = [[] for _ in range(16)]
                for sample in raw_data: # sample 是一个 16 位整数
                    for ch in range(16): # ch 从 0 到 15
                        new_data[ch].append((sample >> ch) & 1)
                
                w.update_data(new_data, depth_points)

        elif packet_type == PacketType.DEBUG_DIGITAL_FREQ_RESULT:
            EXPECTED_PAYLOAD_LEN = 11 
            if len(payload) == EXPECTED_PAYLOAD_LEN:
                try:
                    padded_payload = b'\x00' * 5 + payload
                    full_value = int.from_bytes(padded_payload, byteorder='big', signed=False)

                    total_time_cycles = full_value & ((1 << 28) - 1)
                    low_time_cycles   = (full_value >> 28) & ((1 << 28) - 1)
                    high_time_cycles  = (full_value >> 56) & ((1 << 28) - 1)

                    fpga_clock = 50_000_000
                    if total_time_cycles > 0:
                        frequency = fpga_clock / total_time_cycles
                        freq_str = f"{frequency:.2f} Hz" 
                        total_time_str = format_time_ns(total_time_cycles, fpga_clock)
                        high_time_str = format_time_ns(high_time_cycles, fpga_clock)
                        low_time_str = format_time_ns(low_time_cycles, fpga_clock)
                    else: 
                        freq_str = "N/A (周期为0)"
                        total_time_str = "N/A"; high_time_str = "N/A"; low_time_str = "N/A"

                    s.dig_freq_high_time_display.setText(high_time_str)
                    s.dig_freq_low_time_display.setText(low_time_str)
                    s.dig_freq_total_time_display.setText(total_time_str)
                    s.dig_freq_frequency_display.setText(freq_str)
                
                except Exception as e:
                    self.log_message.emit(f"❌ 解析数字频率结果 (0xFF) 时出错: {e}, Payload: {payload.hex(' ')}")
                    s.dig_freq_high_time_display.setText("解析失败")
            else: 
                 self.log_message.emit(f"⚠️ 收到长度不符的数字频率结果包 (0xFF)，期望{EXPECTED_PAYLOAD_LEN}字节: {payload.hex(' ')}")
                 s.dig_freq_high_time_display.setText("长度错误")
                 
    # --- 辅助函数 ---
    def freq_str_to_hz(self, freq_str: str) -> float:
        """辅助函数：将频率字符串 (例如 "50MHz") 转换为 Hz (float)"""
        value_str = ''.join(filter(lambda x: x.isdigit() or x=='.', freq_str))
        unit_str = ''.join(filter(str.isalpha, freq_str)).lower()
        if value_str:
            value = float(value_str)
            if 'k' in unit_str: value *= 1e3
            elif 'm' in unit_str: value *= 1e6
            return value
        return 0

    def freq_str_to_period_str(self):
        """根据选择的采样频率，计算每个采样点的时间周期，并更新波形显示控件"""
        freq_str = self.settings_widget.frequency.currentText() 
        freq_hz = self.freq_str_to_hz(freq_str)

        if freq_hz <= 1e-9: 
             period_s = 0
             p_val, p_unit = 0, '?'
        else:
            period_s = 1.0 / freq_hz
            p_val, p_unit = period_s, 's' 
            if period_s < 1e-6: p_val, p_unit = period_s * 1e9, 'ns'
            elif period_s < 1e-3: p_val, p_unit = period_s * 1e6, 'us'
            elif period_s < 1: p_val, p_unit = period_s * 1e3, 'ms'

        self.display_widget.set_period(p_val, p_unit)