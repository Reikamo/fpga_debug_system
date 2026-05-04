# signal_generator_widget.py
import sys
import time
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QComboBox,
                             QPushButton, QDialog, QDialogButtonBox, QLineEdit,
                             QFormLayout, QMainWindow, QMessageBox, QSlider, QGroupBox,
                             QButtonGroup, QCheckBox, QGridLayout) 
from PyQt5.QtCore import QSize, Qt, pyqtSignal, QPointF, QObject # <--- 导入 QObject
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QIcon
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import struct
from protocol import PacketType 
from scipy import signal
# 导入通信管理器基类
from communication_manager import CommunicationManager

# 设置 Matplotlib 使用支持中文的字体
matplotlib.rcParams['font.sans-serif'] = ['SimHei'] 
matplotlib.rcParams['axes.unicode_minus'] = False 

# ===================================================================
# 辅助类 1: WaveDrawWidget (手绘画布)
# (保持不变)
# ===================================================================
class WaveDrawWidget(QWidget):
    """手绘波形绘制控件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1200, 600)
        self.path_points = []
        self.drawing = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            x_ratio = event.pos().x() / self.width()
            if x_ratio > 0.15: 
                QMessageBox.warning(self, "提示", "请尽量从最左侧开始绘图~")
            self.drawing = True
            self.path_points = [QPointF(x_ratio, event.pos().y() / self.height())]
            self.update()

    def mouseMoveEvent(self, event):
        if self.drawing:
            x_ratio = event.pos().x() / self.width()
            if (not self.path_points or x_ratio > self.path_points[-1].x()) and 0.0 <= x_ratio <= 1.0:
                y_ratio = event.pos().y() / self.height()
                y_ratio = max(0.0, min(1.0, y_ratio)) 
                self.path_points.append(QPointF(x_ratio, y_ratio))
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drawing = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), Qt.black) 
        w, h = self.width(), self.height()
        painter.setPen(QPen(QColor(255, 255, 255), 1)) 
        font = QFont("Arial", 9)
        painter.setFont(font)
        for i in range(11):
            val = 5 - i
            y_pos = h * (1 - (val + 5) / 10) 
            painter.drawLine(0, int(y_pos), 10, int(y_pos))
            painter.drawText(12, int(y_pos + 4), f"{val}") 
        zero_y = h / 2
        painter.setPen(QPen(QColor(200, 200, 200), 1, Qt.DashLine)) 
        painter.drawLine(0, int(zero_y), w, int(zero_y))
        if not self.path_points:
            painter.setPen(QColor(180, 180, 180))
            painter.setFont(QFont("微软雅黑", 16, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignLeft | Qt.AlignTop, "👉 请从最左侧开始绘图")
        if self.path_points:
            painter.setPen(QPen(QColor(0, 255, 0), 2)) 
            for i in range(1, len(self.path_points)):
                p1, p2 = self.path_points[i-1], self.path_points[i]
                painter.drawLine(QPointF(p1.x() * w, p1.y() * h), QPointF(p2.x() * w, p2.y() * h))

    def get_waveform_data(self, num_points=100):
        if not self.path_points:
            return np.zeros(num_points) 
        x_vals, y_vals = [], []
        last_x = -1.0
        for pt in self.path_points:
            if 0.0 <= pt.x() <= 1.0 and pt.x() > last_x: 
                x_vals.append(pt.x())
                y_vals.append((1.0 - pt.y() * 2)) # (0~1) -> (+1~-1)
                last_x = pt.x()
        if len(x_vals) < 2: 
            return np.zeros(num_points)
        interpolated_y = np.interp(np.linspace(0, 1.0, num_points), x_vals, y_vals)
        return interpolated_y * 5.0 # 将 (+1~-1) 转换为 (+5V~-5V)

    def clear(self):
        self.path_points.clear()
        self.update() 

# ===================================================================
# 辅助类 2: WaveDrawWindow (手绘弹窗)
# (保持不变, 由 Controller 管理)
# ===================================================================
class WaveDrawWindow(QWidget):
    """手绘波形独立窗口 (移除使能控制)"""
    log_message = pyqtSignal(str) # 日志信号

    def __init__(self, comm_manager: CommunicationManager = None, parent=None):
        super().__init__(parent, Qt.Window)
        self.comm_manager = comm_manager

        self.freq_map = {"500kHz":0, "250kHz":1, "125kHz":2, "67.5kHz":3,
                         "500kHz (alt)":4, "250kHz (alt)":5, "125kHz (alt)":6, "67.5kHz (alt)":7}

        self.setWindowTitle("手绘波形编辑器")
        self.setMinimumSize(1200, 800)
        main_layout = QVBoxLayout(self)
        self.canvas = WaveDrawWidget()
        main_layout.addWidget(self.canvas)

        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("频率:"))
        self.frequency = QComboBox()
        self.frequency.addItems(self.freq_map.keys())
        control_layout.addWidget(self.frequency)

        self.btn_send = QPushButton("应用配置和数据") 
        self.btn_send.setToolTip("将当前频率配置和绘制的波形发送给FPGA")
        self.btn_clear = QPushButton("清空绘制")
        self.btn_clear.setToolTip("清除画布上的波形")

        control_layout.addStretch()
        control_layout.addWidget(self.btn_send)
        control_layout.addWidget(self.btn_clear)
        main_layout.addLayout(control_layout)

        self.btn_send.clicked.connect(self.apply_config_and_data) 
        self.btn_clear.clicked.connect(self.canvas.clear)

    def set_communication_manager(self, manager: CommunicationManager):
        self.comm_manager = manager

    def send_frequency_config(self):
        """发送 E2 命令配置手绘波形频率 (现在由 apply_config_and_data 调用)"""
        if not self.comm_manager or not self.comm_manager.is_running():
            self.log_message.emit("❌ (内部错误) 尝试发送频率配置但通信未连接")
            return False

        current_display_text = self.frequency.currentText()
        freq_val = self.freq_map.get(current_display_text, 0)
        payload = struct.pack('!B', freq_val & 0b111)
        packet = struct.pack('!B', PacketType.DDS_HAND_DRAWN_CONFIG) + payload

        if self.comm_manager.send_packet(packet):
            self.log_message.emit(f"✅ 发送手绘波形频率配置 (E2): {current_display_text}")
            return True
        else:
             self.log_message.emit(f"❌ 发送手绘波形频率配置 (E2) 失败")
             return False

    def apply_config_and_data(self):
        """发送 E2 命令配置频率，然后发送 E3 命令传输波形数据"""
        if not self.send_frequency_config():
            return 
        if not self.comm_manager or not self.comm_manager.is_running():
            self.log_message.emit("❌ 请先启动通信会话")
            return

        waveform = self.canvas.get_waveform_data(num_points=100)
        uint8_data = np.clip(np.round((waveform + 5.0) / 10.0 * 255.0), 0, 255).astype(np.uint8)
        wave_payload = uint8_data.tobytes()
        wave_packet = struct.pack('!B', PacketType.DDS_HAND_DRAWN_WAVEFORM) + wave_payload

        if self.comm_manager.send_packet(wave_packet):
            self.log_message.emit(f"✅ 发送手绘波形数据 (E3): {len(wave_payload)} 字节")
        else:
            self.log_message.emit(f"❌ 发送手绘波形数据 (E3) 失败")

    def closeEvent(self, event):
        self.hide()
        event.ignore()

# ===================================================================
# [新] 类 3: _SignalGeneratorDisplayWidget (中间显示栏)
# ===================================================================
class _SignalGeneratorDisplayWidget(QWidget):
    """
    信号发生器的中间显示面板 (QWidget)。
    仅包含两个 Matplotlib 画布。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0) # 紧凑布局
        
        # 创建画布和轴
        self.figure_1, self.ax_1 = plt.subplots()
        self.canvas_1 = FigureCanvas(self.figure_1)
        
        self.figure_2, self.ax_2 = plt.subplots()
        self.canvas_2 = FigureCanvas(self.figure_2)
        
        layout.addWidget(self.canvas_1)
        layout.addWidget(self.canvas_2)

# ===================================================================
# [新] 类 4: _SignalGeneratorSettingsWidget (右侧配置栏)
# ===================================================================
class _SignalGeneratorSettingsWidget(QWidget):
    """
    信号发生器的右侧配置面板 (QWidget)。
    包含所有配置选项和按钮。
    """
    log_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.init_maps() # 加载协议映射
        self.init_ui()

    def init_maps(self):
        """初始化各种参数到协议值的映射"""
        self.waveform_map = {"正弦波": 0, "方波": 1, "三角波": 2, "锯齿波": 3, "脉冲波": 4}
        self.freq_map = {"500kHz": 0, "250kHz": 1, "125kHz": 2, "100kHz": 3, "50kHz": 4, "20kHz": 5}
        self.angle_map = {"0°":0, "45°":1, "90°":2, "135°":3, "180°":4, "225°":5, "270°":6, "315°":7}
        self.amplitude_map = {"5V": 0, "2.5V": 1, "1V": 2, "0.5V": 3}
        self.offset_map = { "0V":0, "+0.5V":1, "-0.5V":2, "+1V":3, "-1V":4, "+1.5V":5, "-1.5V":6,
                            "+2V":7, "-2V":8, "+2.5V":9, "-2.5V":10, "+3V":11, "-3V":12, "+3.5V":13, "-3.5V":14 }
        self.duty_cycle_map = {"15%": 0, "25%": 1, "50%": 2, "75%": 3}
        self.source_map = {"关闭": 0b00, "CH1": 0b01, "CH2": 0b10, "手绘": 0b11}

    def init_ui(self):
        """初始化配置界面的UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 通道 1
        group1 = QGroupBox("通道 1 设置")
        form_layout_1 = self._create_channel_form("1")
        group1.setLayout(form_layout_1)
        
        # 通道 2
        group2 = QGroupBox("通道 2 设置")
        form_layout_2 = self._create_channel_form("2")
        group2.setLayout(form_layout_2)
        
        # 主控制
        button_group = QGroupBox("主控制")
        button_layout = self._create_button_layout()
        button_group.setLayout(button_layout)
        
        layout.addWidget(group1)
        layout.addWidget(group2)
        layout.addWidget(button_group)
        layout.addStretch()

    def _create_channel_form(self, ch_num):
        """创建单个通道的配置表单 (注意：不再连接信号)"""
        form_layout = QFormLayout()
        
        # 创建控件并保存为成员变量
        setattr(self, f"signal_type_{ch_num}", QComboBox()); combo_st = getattr(self, f"signal_type_{ch_num}")
        setattr(self, f"frequency_{ch_num}", QComboBox()); combo_f = getattr(self, f"frequency_{ch_num}")
        setattr(self, f"amplitude_{ch_num}", QComboBox()); combo_a = getattr(self, f"amplitude_{ch_num}")
        setattr(self, f"offset_{ch_num}", QComboBox()); combo_o = getattr(self, f"offset_{ch_num}")
        setattr(self, f"phase_{ch_num}", QComboBox()); combo_p = getattr(self, f"phase_{ch_num}")
        setattr(self, f"duty_cycle_{ch_num}", QComboBox()); combo_d = getattr(self, f"duty_cycle_{ch_num}")

        # 填充下拉框
        combo_st.addItems(self.waveform_map.keys())
        combo_f.addItems(self.freq_map.keys())
        combo_a.addItems(self.amplitude_map.keys())
        combo_o.addItems(self.offset_map.keys()); combo_o.setCurrentIndex(0)
        combo_p.addItems(self.angle_map.keys())
        combo_d.addItems(self.duty_cycle_map.keys()); combo_d.setCurrentIndex(2)
        
        # [修改] 仅连接用于切换占空比使能的信号
        combo_st.currentIndexChanged.connect(lambda: self._on_signal_type_changed(ch_num))
        
        # 添加到布局
        form_layout.addRow(f"信号类型:", combo_st)
        form_layout.addRow(f"频率:", combo_f)
        form_layout.addRow(f"幅度:", combo_a)
        form_layout.addRow(f"偏移:", combo_o)
        form_layout.addRow(f"相位:", combo_p)
        form_layout.addRow(f"占空比:", combo_d)
        
        # 初始化占空比使能状态
        self._on_signal_type_changed(ch_num)
        
        return form_layout

    def _on_signal_type_changed(self, ch_num):
        """根据信号类型启用/禁用相位和占空比下拉框"""
        signal_type_combo = getattr(self, f"signal_type_{ch_num}")
        phase_combo = getattr(self, f"phase_{ch_num}")
        duty_combo = getattr(self, f"duty_cycle_{ch_num}")
        signal_type = signal_type_combo.currentText()

        if signal_type == "脉冲波":
            phase_combo.setEnabled(True); duty_combo.setEnabled(True)
        elif signal_type == "正弦波":
            phase_combo.setEnabled(True); duty_combo.setEnabled(False)
        else:
            phase_combo.setEnabled(False); duty_combo.setEnabled(False)

    def _create_button_layout(self):
        """创建主控制按钮布局"""
        grid_layout = QGridLayout() 
        grid_layout.setSpacing(10) 

        self.open_button = QPushButton("手绘波形")
        self.send_button = QPushButton("应用参数") 

        self.source_select_ch1 = QComboBox()
        self.source_select_ch1.addItems(self.source_map.keys())
        self.source_select_ch2 = QComboBox()
        self.source_select_ch2.addItems(self.source_map.keys())

        self.apply_output_btn = QPushButton("应用输出配置") 

        grid_layout.addWidget(self.open_button, 0, 0)
        grid_layout.addWidget(self.send_button, 0, 1)
        grid_layout.addWidget(QLabel("CH1 输出源:"), 1, 0)
        grid_layout.addWidget(self.source_select_ch1, 1, 1)
        grid_layout.addWidget(QLabel("CH2 输出源:"), 2, 0)
        grid_layout.addWidget(self.source_select_ch2, 2, 1)
        grid_layout.addWidget(self.apply_output_btn, 3, 0, 1, 2, Qt.AlignRight)

        grid_layout.setColumnStretch(1, 1)
        return grid_layout


# ===================================================================
# [新] 类 5: SignalGeneratorController (主控制器)
# ===================================================================
class SignalGeneratorController(QObject):
    """
    信号发生器的主控制器 (QObject)。
    管理 Display 和 Settings 控件之间的逻辑。
    """
    log_message = pyqtSignal(str)

    def __init__(self, comm_manager: CommunicationManager = None, parent=None):
        super().__init__(parent)
        self.comm_manager = comm_manager
        
        # 实例化UI
        self.display_widget = _SignalGeneratorDisplayWidget()
        self.settings_widget = _SignalGeneratorSettingsWidget()
        
        # 实例化手绘弹窗 (初始为None)
        self.wave_window = None 
        
        self.connect_signals()
        
        # 初始绘图
        self.plot_waveform_1()
        self.plot_waveform_2()

    # --- 提供给 MainWIndow 的接口 ---
    def get_display_widget(self) -> QWidget:
        return self.display_widget

    def get_settings_widget(self) -> QWidget:
        return self.settings_widget

    def set_communication_manager(self, manager: CommunicationManager):
        self.comm_manager = manager
        if self.wave_window:
            self.wave_window.set_communication_manager(manager)

    # --- 信号连接 ---
    def connect_signals(self):
        s = self.settings_widget # 右侧配置栏
        
        # 1. 连接主控制按钮
        s.open_button.clicked.connect(self.open_wave_draw_window)
        s.send_button.clicked.connect(self.send_config)
        s.apply_output_btn.clicked.connect(self.apply_output_config)

        # 2. 连接通道1所有下拉框的 currentIndexChanged 到 plot_waveform_1
        for widget_name in ["signal_type_1", "frequency_1", "amplitude_1", "offset_1", "phase_1", "duty_cycle_1"]:
            widget = getattr(s, widget_name)
            widget.currentIndexChanged.connect(self.plot_waveform_1)

        # 3. 连接通道2所有下拉框的 currentIndexChanged 到 plot_waveform_2
        for widget_name in ["signal_type_2", "frequency_2", "amplitude_2", "offset_2", "phase_2", "duty_cycle_2"]:
            widget = getattr(s, widget_name)
            widget.currentIndexChanged.connect(self.plot_waveform_2)
            
        # 4. 连接日志
        s.log_message.connect(self.log_message)

    # --- 绘图逻辑 (槽函数) ---
    def plot_waveform_1(self): 
        self._plot_waveform(
            1, 
            self.display_widget.ax_1, 
            self.display_widget.canvas_1
        )
        
    def plot_waveform_2(self): 
        self._plot_waveform(
            2, 
            self.display_widget.ax_2, 
            self.display_widget.canvas_2
        )

    def _plot_waveform(self, ch_num, ax, canvas):
        """根据配置绘制波形预览图 (从 settings_widget 读取, 绘制到 display_widget)"""
        s = self.settings_widget # 右侧配置栏
        
        # 从 settings_widget 获取控件
        signal_type_combo = getattr(s, f"signal_type_{ch_num}")
        phase_combo = getattr(s, f"phase_{ch_num}")
        duty_combo = getattr(s, f"duty_cycle_{ch_num}")
        signal_type = signal_type_combo.currentText()
        freq_text = getattr(s, f"frequency_{ch_num}").currentText()
        amp_text = getattr(s, f"amplitude_{ch_num}").currentText()
        offset_text = getattr(s, f"offset_{ch_num}").currentText()
        phase_text = phase_combo.currentText()
        duty_text = duty_combo.currentText()

        # (注意：启用/禁用的逻辑由 _on_signal_type_changed 在 settings_widget 内部处理了)
        
        # (计算逻辑保持不变)
        freq_val = float(freq_text.replace("kHz","")) * 1000 if "kHz" in freq_text else float(freq_text.replace("Hz",""))
        amp = float(amp_text.replace("V",""))
        offset = float(offset_text.replace("V",""))
        phase = float(phase_text.replace("°",""))
        duty = float(duty_text.replace("%","")) / 100.0

        duration = 2 / freq_val if freq_val > 0 else 0.002
        t = np.linspace(0, duration, 1000)
        omega = 2 * np.pi * freq_val

        if signal_type == "正弦波": y = amp * np.sin(omega * t + np.radians(phase))
        elif signal_type == "方波": y = amp * signal.square(omega * t, duty=0.5)
        elif signal_type == "脉冲波": y = amp * signal.square(omega * t + np.radians(phase), duty=duty)
        elif signal_type == "三角波": y = amp * signal.sawtooth(omega * t + np.radians(phase), width=0.5)
        elif signal_type == "锯齿波": y = amp * signal.sawtooth(omega * t + np.radians(phase), width=1.0)
        else: y = np.zeros_like(t)
        y += offset

        if freq_val >= 1e6: t *= 1e6; xlabel = "时间 (us)"
        elif freq_val >= 1e3: t *= 1e3; xlabel = "时间 (ms)"
        else: xlabel = "时间 (s)"

        ax.clear(); ax.plot(t, y)
        ax.set_title(f"通道 {ch_num}: {signal_type}"); ax.set_xlabel(xlabel); ax.set_ylabel("电压 (V)")
        ax.grid(True); ax.figure.tight_layout(); canvas.draw()

    # --- 通信逻辑 (槽函数) ---
    def send_config(self):
        """发送 E0 命令配置 CH1 和 CH2 的参数"""
        s = self.settings_widget
        
        if not self.comm_manager or not self.comm_manager.is_running():
            self.log_message.emit("❌ 请先启动通信会话")
            return

        # 从 settings_widget 获取映射
        waveform_map = s.waveform_map
        freq_map = s.freq_map
        angle_map = s.angle_map
        amplitude_map = s.amplitude_map
        offset_map = s.offset_map
        duty_cycle_map = s.duty_cycle_map

        # 从 settings_widget 获取值
        wave1   = waveform_map.get(getattr(s, "signal_type_1").currentText(), 0)
        freq1   = freq_map.get(getattr(s, "frequency_1").currentText(), 0)
        phase1  = angle_map.get(getattr(s, "phase_1").currentText(), 0)
        amp1    = amplitude_map.get(getattr(s, "amplitude_1").currentText(), 0)
        offset1 = offset_map.get(getattr(s, "offset_1").currentText(), 0)
        duty1   = duty_cycle_map.get(getattr(s, "duty_cycle_1").currentText(), 2) if wave1 == waveform_map["脉冲波"] else 2
        
        wave2   = waveform_map.get(getattr(s, "signal_type_2").currentText(), 0)
        freq2   = freq_map.get(getattr(s, "frequency_2").currentText(), 0)
        phase2  = angle_map.get(getattr(s, "phase_2").currentText(), 0)
        amp2    = amplitude_map.get(getattr(s, "amplitude_2").currentText(), 0)
        offset2 = offset_map.get(getattr(s, "offset_2").currentText(), 0)
        duty2   = duty_cycle_map.get(getattr(s, "duty_cycle_2").currentText(), 2) if wave2 == waveform_map["脉冲波"] else 2

        # (构建 payload 逻辑不变)
        payload_val = 0
        payload_val |= (wave1   & 0b111) << 33
        payload_val |= (freq1   & 0b111) << 30
        payload_val |= (phase1  & 0b111) << 27
        payload_val |= (amp1    & 0b11)  << 25
        payload_val |= (offset1 & 0b1111) << 21
        payload_val |= (duty1   & 0b11)  << 19
        payload_val |= (wave2   & 0b111) << 16
        payload_val |= (freq2   & 0b111) << 13
        payload_val |= (phase2  & 0b111) << 10
        payload_val |= (amp2    & 0b11)  << 8
        payload_val |= (offset2 & 0b1111) << 4
        payload_val |= (duty2   & 0b11)  << 2

        payload_bytes = struct.pack('>Q', payload_val)[-5:]
        packet = struct.pack('!B', PacketType.DDS_CONFIG) + payload_bytes

        if self.comm_manager.send_packet(packet):
            self.log_message.emit("✅ 信号发生器参数配置 (E0) 成功")
        else:
            self.log_message.emit("❌ 信号发生器参数配置 (E0) 失败")

    def apply_output_config(self):
        """根据两个下拉框状态构建并发送 E1 命令 (输出使能控制)"""
        s = self.settings_widget
        
        if not self.comm_manager or not self.comm_manager.is_running():
            self.log_message.emit("❌ 请先启动通信会话")
            return

        src1_text = s.source_select_ch1.currentText()
        src2_text = s.source_select_ch2.currentText()
        src1_bits = s.source_map.get(src1_text, 0b00)
        src2_bits = s.source_map.get(src2_text, 0b00)
        payload_byte = (src2_bits << 2) | src1_bits
        payload = struct.pack('!B', payload_byte)
        packet = struct.pack('!B', PacketType.DDS_OUTPUT_ENABLE) + payload

        action_ch1 = f"CH1={src1_text}"
        action_ch2 = f"CH2={src2_text}"
        action_text = f"配置输出: {action_ch1}, {action_ch2}"

        if self.comm_manager.send_packet(packet):
            self.log_message.emit(f"▶️ 发送DDS输出命令 (E1): {action_text}, 控制字节: 0x{payload_byte:02X}")
            if self.wave_window and ("手绘" in [src1_text, src2_text]):
                 self.wave_window.set_communication_manager(self.comm_manager)
                 self.wave_window.send_frequency_config()
        else:
            self.log_message.emit(f"❌ 发送DDS输出命令 (E1) 失败")

    def open_wave_draw_window(self):
        """打开或激活手绘波形窗口"""
        if self.wave_window is None:
            self.wave_window = WaveDrawWindow(self.comm_manager)
            if hasattr(self, 'log_message'):
                self.wave_window.log_message.connect(self.log_message)
        self.wave_window.set_communication_manager(self.comm_manager)
        self.wave_window.show()
        self.wave_window.activateWindow()

    def handle_data(self, packet_type, payload, source_id=None):
        """处理接收到的数据包（当前为空）"""
        pass