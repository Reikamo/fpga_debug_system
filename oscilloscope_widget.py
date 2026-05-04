# oscilloscope_widget.py
import sys
import time
import numpy as np
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QSize
from scipy.fft import fft, fftfreq
from numpy.fft import fftshift
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout,
    QHBoxLayout, QLabel, QCheckBox, QDialog, QFormLayout,
    QLineEdit, QDialogButtonBox, QFileDialog, QInputDialog, QComboBox,
    QScrollArea, QSplitter, QGroupBox, QDoubleSpinBox, QSpinBox, QTextEdit, QGridLayout
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QObject
import pyqtgraph as pg
import struct
from collections import deque
from protocol import PacketType
from communication_manager import CommunicationManager


pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

# --- OpenGL settings (可选) ---
try:
    import OpenGL
    pg.setConfigOptions(useOpenGL=True)
    print("PyQtGraph OpenGL enabled.")
except ImportError:
    pg.setConfigOptions(useOpenGL=False)
    print("PyQtGraph OpenGL disabled (PyOpenGL not found).")


# ===================================================================
# [新] 类 1: _OscilloscopeSettingsWidget (右侧配置栏)
# ===================================================================
class _OscilloscopeSettingsWidget(QWidget):
    """
    示波器的右侧配置面板 (QWidget)。
    包含所有配置选项和按钮。
    """
    log_message = pyqtSignal(str) # 日志信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_maps()
        self.init_ui()

    def init_maps(self):
        """初始化协议值映射"""
        self.trigger_map = {"上升沿": 0, "下降沿": 1, "峰值触发": 2, "低谷触发": 3}
        self.freq_map = {
            "100Hz": 0, "500Hz": 1, "1kHz": 2, "5kHz": 3, "10kHz": 4, "50kHz": 5,
            "100kHz": 6, "200kHz": 7, "500kHz ": 8,
            "1MHz": 9, "2MHz": 10, "5MHz": 11, "25MHz": 12
        }
        self.channel_map = {"无效": 0, "外部 ad0": 1, "DDS1 输出": 2, "DDS2 输出": 3}

    def init_ui(self):
        """初始化用户界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- 参数配置组 ---
        config_group = QGroupBox("参数配置")
        config_layout = QGridLayout(config_group) # 使用网格布局

        config_layout.addWidget(QLabel("通道选择:"), 0, 0)
        self.channel_select = QComboBox()
        self.channel_select.addItems(self.channel_map.keys())
        config_layout.addWidget(self.channel_select, 0, 1)

        config_layout.addWidget(QLabel("模式选择:"), 1, 0)
        self.trigger = QComboBox()
        self.trigger.addItems(self.trigger_map.keys())
        config_layout.addWidget(self.trigger, 1, 1)

        config_layout.addWidget(QLabel("采样频率:"), 2, 0)
        self.frequency = QComboBox()
        self.frequency.addItems(self.freq_map.keys())
        config_layout.addWidget(self.frequency, 2, 1)
        
        config_layout.setColumnStretch(1, 1) # 让下拉框伸展
        main_layout.addWidget(config_group)

        # --- 采集控制组 ---
        control_group = QGroupBox("采集控制")
        control_layout = QVBoxLayout(control_group) # 垂直布局
        self.send_button = QPushButton("开始采集") # 开始/停止按钮
        self.send_button.setCheckable(True) # 设置为可切换状态
        control_layout.addWidget(self.send_button)
        main_layout.addWidget(control_group)

        # --- 状态显示组 ---
        status_group = QGroupBox("状态显示")
        status_layout = QFormLayout(status_group)
        self.freq_test = QLineEdit()
        self.freq_test.setReadOnly(True)
        status_layout.addRow("波形频率 (Hz):", self.freq_test)
        main_layout.addWidget(status_group)
        
        main_layout.addStretch() # 占满剩余空间

# ===================================================================
# [新] 类 2: _OscilloscopeDisplayWidget (中间显示栏)
# ===================================================================
class _OscilloscopeDisplayWidget(QWidget):
    """
    示波器的中间显示面板 (QWidget)。
    仅包含 pyqtgraph 图表。
    """
    def __init__(self, fft_samples, fft_x_coords, parent=None):
        super().__init__(parent)
        self.fft_samples = fft_samples
        self.fft_x_coords = fft_x_coords
        self.init_ui()

    def init_ui(self):
        """初始化图表界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # --- 图表布局 (使用 QSplitter 分割波形和频谱) ---
        plot_splitter = QSplitter(Qt.Vertical)

        # 波形图
        self.plot_widget = pg.PlotWidget(title="波形显示")
        self.plot_widget.setLabel("bottom", "采样点")
        self.plot_widget.setLabel("left", "幅度")
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_data = self.plot_widget.plot(pen=(0, 191, 255)) # 蓝色

        # 频谱图 (双边谱)
        self.fft_plot_widget = pg.PlotWidget(title="频谱显示 (双边)")
        self.fft_plot_widget.setLabel("bottom", "频率 (点索引)")
        self.fft_plot_widget.setLabel("left", "幅度")
        self.fft_plot_widget.showGrid(x=True, y=True)

        self.bar_graph = pg.BarGraphItem(
            x=self.fft_x_coords,
            height=np.zeros(self.fft_samples), 
            width=0.8,
            brush=(0, 191, 255)
        )
        self.fft_plot_widget.addItem(self.bar_graph)

        self.fft_plot_widget.getViewBox().setXRange(-self.fft_samples // 2, self.fft_samples // 2, padding=0)
        self.fft_plot_widget.getViewBox().setLimits(xMin=-self.fft_samples // 2, xMax=self.fft_samples // 2)

        plot_splitter.addWidget(self.plot_widget)
        plot_splitter.addWidget(self.fft_plot_widget)

        main_layout.addWidget(plot_splitter) # 图表区域占据所有空间
        
        # 连接双击信号
        self.plot_widget.scene().sigMouseClicked.connect(self.reset_view)
        self.fft_plot_widget.scene().sigMouseClicked.connect(self.reset_fft_view)

    def reset_view(self, event):
        """双击波形图时重置视图范围"""
        if event.double():
            self.plot_widget.getViewBox().autoRange()

    def reset_fft_view(self, event):
        """双击频谱图时重置视图范围"""
        if event.double():
            self.fft_plot_widget.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis)
            self.fft_plot_widget.getViewBox().setXRange(-self.fft_samples // 2, self.fft_samples // 2, padding=0)

# ===================================================================
# [新] 类 3: OscilloscopeController (主控制器)
# ===================================================================
class OscilloscopeController(QObject):
    """
    示波器的主控制器 (QObject)。
    管理 Display 和 Settings 控件之间的逻辑。
    """
    log_message = pyqtSignal(str) # 日志消息信号

    def __init__(self, comm_manager: CommunicationManager = None, parent=None):
        super().__init__(parent)
        self.comm_manager = comm_manager
        self.connected = False

        # --- 缓冲区 ---
        self.latest_wave_data = None
        self.latest_freq_data = None
        self.new_data_available = False

        self.display_timer = QTimer(self)
        self.display_timer.setInterval(50)
        self.display_timer.timeout.connect(self.update_display)

        # --- FFT 相关变量 ---
        self.fft_samples = 512 
        self.fft_x_coords = np.arange(-self.fft_samples // 2, self.fft_samples // 2)
        
        # --- 实例化UI ---
        self.display_widget = _OscilloscopeDisplayWidget(self.fft_samples, self.fft_x_coords)
        self.settings_widget = _OscilloscopeSettingsWidget()
        
        self.connect_signals()

    # --- 提供给 MainWIndow 的接口 ---
    def get_display_widget(self) -> QWidget:
        return self.display_widget

    def get_settings_widget(self) -> QWidget:
        return self.settings_widget

    def set_communication_manager(self, manager: CommunicationManager):
        """由 MainWindow 调用，设置或更新通信管理器实例"""
        self.comm_manager = manager
        if not self.comm_manager or not self.comm_manager.is_running():
             if self.connected:
                  self.stop_acquisition_logic()

    # --- 信号连接 ---
    def connect_signals(self):
        """连接信号槽"""
        # 连接设置面板的按钮到控制器的槽
        self.settings_widget.send_button.clicked.connect(self.toggle_acquisition)
        # (显示面板的双击信号已在其内部连接)

    # --- 核心逻辑 (槽函数和数据处理) ---
    
    @pyqtSlot(bool)
    def toggle_acquisition(self, checked):
        """处理开始/停止采集按钮点击事件"""
        s = self.settings_widget # 引用配置面板
        
        if not self.comm_manager or not self.comm_manager.is_running():
             self.log_message.emit("❌ 请先连接通信接口 (UDP 或 Serial)。")
             s.send_button.setChecked(False) 
             return

        if checked: # 如果按下按钮（开始采集）
            mode_val = s.trigger_map.get(s.trigger.currentText(), 0)
            freq_val = s.freq_map.get(s.frequency.currentText(), 0)
            channel_val = s.channel_map.get(s.channel_select.currentText(), 0)
            control_byte = ((mode_val & 0b11) << 6) | ((freq_val & 0b1111) << 2) | (channel_val & 0b11)

            config_payload = struct.pack('!B', control_byte)
            config_packet = struct.pack('!B', PacketType.OSC_CONFIG_NEW) + config_payload

            if self.comm_manager.send_packet(config_packet):
                enable_payload = struct.pack('!B', 1) 
                enable_packet = struct.pack('!B', PacketType.OSC_ENABLE) + enable_payload
                if self.comm_manager.send_packet(enable_packet):
                    self.log_message.emit("✅ 示波器配置并使能，开始采集...")
                    s.send_button.setText("停止采集") 
                    self.connected = True 
                    self.display_timer.start() 
                else: 
                    self.log_message.emit("❌ 示波器使能命令(F1)发送失败")
                    s.send_button.setChecked(False) 
                    disable_payload = struct.pack('!B', 0)
                    disable_packet = struct.pack('!B', PacketType.OSC_ENABLE) + disable_payload
                    self.comm_manager.send_packet(disable_packet) 
            else: 
                self.log_message.emit("❌ 示波器配置命令(F0)发送失败")
                s.send_button.setChecked(False)
        else: # 如果按钮弹起（停止采集）
            self.stop_acquisition_logic()

    def stop_acquisition_logic(self):
         """停止采集的内部逻辑"""
         s = self.settings_widget
         
         disable_payload = struct.pack('!B', 0) 
         disable_packet = struct.pack('!B', PacketType.OSC_ENABLE) + disable_payload
         
         if self.comm_manager and self.comm_manager.is_running():
             if self.comm_manager.send_packet(disable_packet):
                 self.log_message.emit("⏹️ 示波器停止采集")
             else:
                 self.log_message.emit("⚠️ 发送示波器停止命令(F1)失败，但仍停止本地处理")
         else:
              self.log_message.emit("⏹️ 停止本地示波器处理 (通信已断开)")

         s.send_button.setText("开始采集") 
         s.send_button.setChecked(False) 
         self.connected = False 
         self.display_timer.stop() 

    def handle_data(self, packet_type, payload, source_id=None):
        """处理接收到的数据包 (由 MainWindow 调用)，仅缓存数据"""
        if packet_type == PacketType.OSC_DATA and self.connected:
            expected_len = 4 + 512
            if len(payload) >= expected_len:
                self.latest_freq_data = payload[0:4]
                self.latest_wave_data = payload[4:4+512]
                self.new_data_available = True
            else:
                self.log_message.emit(f"⚠️ 示波器数据包(AA)长度不足: 期望 {expected_len}, 收到 {len(payload)}")
                self.new_data_available = False 

    @pyqtSlot()
    def update_display(self):
        """
        更新UI显示 (在UI线程执行，处理缓存的数据)
        """
        if not self.new_data_available or not self.connected:
            return
        self.new_data_available = False 

        s = self.settings_widget
        d = self.display_widget

        if self.latest_freq_data:
            try:
                frequency_value = struct.unpack('>I', self.latest_freq_data)[0]
                s.freq_test.setText(str(frequency_value)) 
            except Exception as e:
                self.log_message.emit(f"❌ 解析频率数据失败: {e}")
                s.freq_test.setText("错误")

        if self.latest_wave_data:
            try:
                wave_data_uint8 = np.frombuffer(self.latest_wave_data, dtype=np.uint8)
                wave_data_float = (wave_data_uint8.astype(np.float32) - 128.0) / 128.0

                d.plot_data.setData(wave_data_float) # 更新波形图

                if len(wave_data_float) == self.fft_samples:
                    fft_result = np.fft.fft(wave_data_float)
                    fft_magnitude = np.abs(fft_result)
                    fft_magnitude_shifted = fftshift(fft_magnitude)
                    
                    d.bar_graph.setOpts(x=self.fft_x_coords, height=fft_magnitude_shifted) # 更新频谱图
                else:
                    self.log_message.emit(f"⚠️ 波形数据长度 ({len(wave_data_float)}) 与预期 FFT 点数 ({self.fft_samples}) 不符")
                    d.bar_graph.setOpts(x=[], height=[])

            except Exception as e: 
                self.log_message.emit(f"❌ 处理或绘制波形/FFT时发生错误: {e}")
                d.plot_data.setData([])
                d.bar_graph.setOpts(x=[], height=[])