import sys
import socket
import struct
from datetime import datetime
import numpy as np
import math # <--- 新增导入 math

# 从 PyQt5 导入更多控件
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QGroupBox, QLabel,
                             QLineEdit, QPushButton, QSpinBox, QComboBox,
                             QTextEdit, QGridLayout, QMessageBox, QRadioButton,
                             QFormLayout, QFrame, QDoubleSpinBox)
from PyQt5.QtCore import QThread, pyqtSignal, QSettings, Qt, QPoint, QTimer, QRect
from PyQt5.QtGui import QFont, QPainter, QPen, QColor, QPainterPath

# 尝试导入 PacketType
try:
    # 假设 protocol 在同一目录下或父目录的 fpga_debug_system 下
    from protocol import PacketType
except ImportError:
    print("警告: 未找到 protocol.py，将使用临时 PacketType 定义。")
    from enum import IntEnum
    class PacketType(IntEnum):
        OSC_DATA = 0xAA
        LOGIC_ANALYZER_DATA = 0xAB
        # 添加 DDS 相关类型 (虽然不直接发送这些，但可能有用)
        DDS_CONFIG = 0xE0
        DDS_OUTPUT_ENABLE = 0xE1

# --- 图形化逻辑波形编辑器 (LogicWaveEditor) 类代码保持不变 ---
class LogicWaveEditor(QWidget):
    """
    一个用于图形化绘制和编辑逻辑分析仪波形的控件 (v4 - 交互增强版)。
    - 支持鼠标滚轮缩放
    - 支持右键拖动平移
    """
    def __init__(self, channels=16, depth=256, parent=None):
        super().__init__(parent)
        self.channels = channels
        self.depth = depth
        self.data = np.zeros((self.channels, self.depth), dtype=int)

        self.offset = 0.0
        self.zoom = 4.0
        self._dragging_pan = False
        self._last_mouse_x = 0

        self.setMinimumHeight(300)

    def set_depth(self, new_depth: int):
        old_depth = self.depth
        new_data = np.zeros((self.channels, new_depth), dtype=int)
        copy_len = min(old_depth, new_depth)
        if copy_len > 0:
            new_data[:, :copy_len] = self.data[:, :copy_len]

        self.depth = new_depth
        self.data = new_data
        view_width = self.width() - 50
        effective_zoom = max(0.1, self.zoom)
        max_offset = max(0, self.depth - (view_width / effective_zoom if effective_zoom > 0 else 0))
        self.offset = max(0, min(self.offset, max_offset))
        self.update()


    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), Qt.black)

        w, h = self.width(), self.height()
        row_h = h / self.channels if self.channels > 0 else h

        view_width = w - 50
        start_idx = max(0, int(self.offset))
        effective_zoom = max(0.1, self.zoom)
        end_idx = min(self.depth, int(self.offset + view_width / effective_zoom) + 2)

        painter.setPen(QPen(QColor(60, 60, 60), 1, Qt.SolidLine))
        if effective_zoom > 0:
            for i in range(start_idx, end_idx):
                x = int(50 + (i - self.offset) * effective_zoom)
                if x >= 50:
                    painter.drawLine(x, 0, x, h)

        painter.setFont(QFont("Consolas", 8))
        for i in range(self.channels):
            painter.setPen(QPen(Qt.white))
            painter.drawText(5, int((i + 0.7) * row_h), f"CH{i}")
            painter.setPen(QPen(QColor(60, 60, 60), 1, Qt.SolidLine))
            painter.drawLine(0, int((i + 1) * row_h), w, int((i + 1) * row_h))

        painter.setPen(QPen(QColor(0, 255, 0), 2))
        for ch in range(self.channels):
            y_base = int((ch + 0.5) * row_h)
            path = QPainterPath()

            if start_idx < self.depth:
                y_start = y_base - self.data[ch, start_idx] * int(row_h * 0.4)
                x_start = 50 + (start_idx - self.offset) * effective_zoom
                path.moveTo(x_start, y_start)

                for i in range(start_idx + 1, end_idx):
                    if i < self.depth:
                        x_curr = 50 + (i - self.offset) * effective_zoom
                        val_prev = self.data[ch, i-1]
                        val_curr = self.data[ch, i]

                        y_prev = y_base - val_prev * int(row_h * 0.4)
                        y_curr = y_base - val_curr * int(row_h * 0.4)

                        if val_curr != val_prev:
                            path.lineTo(x_curr, y_prev)
                        path.lineTo(x_curr, y_curr)

            painter.save()
            clip_rect = QRect(50, 0, view_width, h)
            painter.setClipRect(clip_rect)
            painter.drawPath(path)
            painter.restore()


    def wheelEvent(self, event):
        if event.x() < 50: return

        delta = event.angleDelta().y()
        factor = 1.2 if delta > 0 else (1 / 1.2)
        old_zoom = self.zoom
        self.zoom = max(0.1, min(100.0, self.zoom * factor))

        mouse_x_in_plot = event.x() - 50
        effective_old_zoom = max(0.1, old_zoom)
        effective_zoom = max(0.1, self.zoom)

        mouse_offset_in_samples_before = mouse_x_in_plot / effective_old_zoom
        mouse_offset_in_samples_after = mouse_x_in_plot / effective_zoom

        self.offset += mouse_offset_in_samples_before - mouse_offset_in_samples_after

        view_width_samples = (self.width() - 50) / effective_zoom if effective_zoom != 0 else self.depth
        max_offset = max(0, self.depth - view_width_samples)
        self.offset = max(0, min(self.offset, max_offset))

        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_level(event.pos())
        elif event.button() == Qt.RightButton and event.x() >= 50:
            self._dragging_pan = True
            self._last_mouse_x = event.x()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        effective_zoom = max(0.1, self.zoom)
        if event.buttons() & Qt.LeftButton:
            self._toggle_level(event.pos(), force_set=True)
        elif self._dragging_pan:
            dx = event.x() - self._last_mouse_x
            self.offset -= dx / effective_zoom

            view_width_samples = (self.width() - 50) / effective_zoom if effective_zoom != 0 else self.depth
            max_offset = max(0, self.depth - view_width_samples)
            self.offset = max(0, min(self.offset, max_offset))

            self._last_mouse_x = event.x()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self._dragging_pan = False
            self.setCursor(Qt.ArrowCursor)

    def _toggle_level(self, pos: QPoint, force_set=False):
        h, w = self.height(), self.width()
        if pos.x() < 50 or self.channels <= 0: return

        ch = int(pos.y() / (h / self.channels))
        effective_zoom = max(0.1, self.zoom)
        t = int(self.offset + (pos.x() - 50) / effective_zoom)

        if 0 <= ch < self.channels and 0 <= t < self.depth:
            if force_set:
                row_h = h / self.channels
                y_in_row = pos.y() % row_h
                self.data[ch, t] = 1 if y_in_row < row_h / 2 else 0
            else:
                self.data[ch, t] = 1 - self.data[ch, t]
            self.update()

    def set_channel_to_zero(self, channel: int):
        if 0 <= channel < self.channels:
            self.data[channel, :] = 0
            self.update()

    def set_channel_to_one(self, channel: int):
        if 0 <= channel < self.channels:
            self.data[channel, :] = 1
            self.update()

    def generate_clock(self, channel: int, period: int = 2):
        if 0 <= channel < self.channels and period > 0:
            half_period = max(1, period // 2)
            self.data[channel, :] = [(i // half_period) % 2 for i in range(self.depth)]
            self.update()

    def get_la_payload(self) -> bytes:
        payload_array = []
        for i in range(self.depth):
            sample_word = 0
            for ch in range(self.channels):
                if 0 <= ch < self.data.shape[0] and 0 <= i < self.data.shape[1]:
                    if self.data[ch, i] == 1:
                        sample_word |= (1 << ch)
            payload_array.append(sample_word)

        try:
            if len(payload_array) != self.depth:
                 print(f"错误: payload_array 长度 ({len(payload_array)}) 与 depth ({self.depth}) 不匹配。")
                 payload_array.extend([0] * (self.depth - len(payload_array)))

            payload = struct.pack(f'<{self.depth}H', *payload_array)
            return payload
        except struct.error as e:
            print(f"打包 LA payload 时出错: {e}. Depth={self.depth}, Array size={len(payload_array)}")
            return b''


# --- 独立的波形编辑器窗口 (WaveformEditorWindow) 类代码保持不变 ---
class WaveformEditorWindow(QWidget):
    data_ready_to_send = pyqtSignal(bytes)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("LA 波形编辑器")
        self.setGeometry(150, 150, 1000, 600)

        main_layout = QVBoxLayout(self)

        control_group = QGroupBox("控制面板")
        control_layout = QHBoxLayout()

        control_layout.addWidget(QLabel("采样深度:"))
        self.depth_combo = QComboBox()
        self.depth_combo.addItems(["256", "512", "1024", "2048"])
        control_layout.addWidget(self.depth_combo)

        control_layout.addSpacing(20)

        control_layout.addWidget(QLabel("通道:"))
        self.channel_spin = QSpinBox()
        self.channel_spin.setRange(0, 15)
        control_layout.addWidget(self.channel_spin)

        self.set_zero_btn = QPushButton("置 0")
        self.set_one_btn = QPushButton("置 1")
        self.gen_clock_btn = QPushButton("生成时钟")
        control_layout.addWidget(self.set_zero_btn)
        control_layout.addWidget(self.set_one_btn)
        control_layout.addWidget(self.gen_clock_btn)

        control_layout.addStretch()

        self.send_btn = QPushButton("发送 LA 数据 (0xAB)")
        control_layout.addWidget(self.send_btn)

        control_group.setLayout(control_layout)

        self.wave_editor = LogicWaveEditor(channels=16, depth=int(self.depth_combo.currentText()))

        main_layout.addWidget(control_group)
        main_layout.addWidget(self.wave_editor, 1)

        self.depth_combo.currentTextChanged.connect(lambda txt: self.wave_editor.set_depth(int(txt)))
        self.set_zero_btn.clicked.connect(lambda: self.wave_editor.set_channel_to_zero(self.channel_spin.value()))
        self.set_one_btn.clicked.connect(lambda: self.wave_editor.set_channel_to_one(self.channel_spin.value()))
        self.gen_clock_btn.clicked.connect(lambda: self.wave_editor.generate_clock(self.channel_spin.value()))
        self.send_btn.clicked.connect(self.prepare_and_send_data)

    def prepare_and_send_data(self):
        try:
            header = struct.pack('!B', PacketType.LOGIC_ANALYZER_DATA)
        except NameError:
             QMessageBox.critical(self, "错误", "PacketType 未定义，请确保 protocol.py 文件存在。")
             return

        payload = self.wave_editor.get_la_payload()
        if not payload:
             QMessageBox.critical(self, "错误", "生成 LA Payload 失败，请检查控制台输出。")
             return

        full_packet = header + payload
        self.data_ready_to_send.emit(full_packet)
        QMessageBox.information(self, "成功", f"LA 数据包 ({len(full_packet)} 字节) 已准备发送!")


# --- 辅助函数：获取本机IP (get_local_ips) 代码保持不变 ---
def get_local_ips():
    """获取本机所有IPv4地址"""
    ips = ['127.0.0.1', '0.0.0.0']
    try:
        hostname = socket.gethostname()
        addr_info = socket.gethostbyname_ex(hostname)
        for ip in addr_info[2]:
            if ip not in ips:
                ips.insert(0, ip)
    except Exception as e:
        print(f"获取本机IP失败: {e}")
    return ips

# --- 后台网络线程 (UdpClient) 代码保持不变 ---
class UdpClient(QThread):
    listening_status = pyqtSignal(bool, str)
    data_received = pyqtSignal(bytes, tuple)
    log_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._socket = None
        self._is_running = False
        self.local_address = None

    def start_listening(self, local_ip: str, local_port: int):
        self.local_address = (local_ip, local_port)
        self._is_running = True
        self.start()

    def stop_listening(self):
        self._is_running = False
        if self._socket:
            try: self._socket.close()
            except OSError: pass
        self.wait()

    def run(self):
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind(self.local_address)
            self.listening_status.emit(True, f"正在监听 {self.local_address[0]}:{self.local_address[1]}...")
        except Exception as e:
            self.listening_status.emit(False, f"绑定本地地址失败: {e}")
            self._is_running = False
            return

        while self._is_running:
            try:
                data, address = self._socket.recvfrom(65535)
                if data:
                    self.data_received.emit(data, address)
            except socket.error as e:
                if self._is_running:
                    self.log_message.emit(f"接收错误: {e}")
                break

        self._socket = None
        self.listening_status.emit(False, "监听已停止。")


# --- 主窗口 ---
class UdpGuiTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("MyCompany", "UdpGuiTool")
        self.udp_client = UdpClient()
        self.send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.target_address = None
        self.waveform_editor_window = None
        # --- 新增 DDS 模拟相关 ---
        self.dds_sim_timer = QTimer(self) # 用于定时发送波形数据
        self.dds_sim_phase_accumulator = 0.0 # 相位累加器，用于连续生成波形
        self.dds_sim_samples = 512 # 示波器采样点数
        # --- 结束新增 ---

        self.init_ui()
        self.setup_connections()
        self.load_settings()

    def init_ui(self):
        self.setWindowTitle("简易UDP调试与模拟工具")
        # 增加窗口高度以容纳 DDS 模拟设置
        self.setGeometry(100, 100, 800, 650) # <--- 调整高度
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- UDP 通信设置 (保持不变) ---
        connection_group = QGroupBox("UDP 通信设置")
        connection_layout = QGridLayout()
        connection_layout.addWidget(QLabel("本地IP:"), 0, 0); self.local_ip_combo = QComboBox(); self.local_ip_combo.setEditable(True); self.local_ip_combo.addItems(get_local_ips()); connection_layout.addWidget(self.local_ip_combo, 0, 1)
        connection_layout.addWidget(QLabel("本地端口:"), 0, 2); self.local_port_spin = QSpinBox(); self.local_port_spin.setRange(1, 65535); self.local_port_spin.setValue(8080); connection_layout.addWidget(self.local_port_spin, 0, 3)
        connection_layout.addWidget(QLabel("目标IP:"), 1, 0); self.target_ip_input = QLineEdit(); self.target_ip_input.setText("127.0.0.1"); connection_layout.addWidget(self.target_ip_input, 1, 1)
        connection_layout.addWidget(QLabel("目标端口:"), 1, 2); self.target_port_spin = QSpinBox(); self.target_port_spin.setRange(1, 65535); self.target_port_spin.setValue(8088); connection_layout.addWidget(self.target_port_spin, 1, 3)
        self.connect_btn = QPushButton("开始监听"); self.connect_btn.setCheckable(True); connection_layout.addWidget(self.connect_btn, 0, 4, 2, 1)
        self.status_label = QLabel("空闲"); self.status_label.setAlignment(Qt.AlignCenter); connection_layout.addWidget(self.status_label, 0, 5, 2, 1)
        connection_group.setLayout(connection_layout)
        main_layout.addWidget(connection_group)

        # --- 手动发送数据 (保持不变) ---
        send_group = QGroupBox("手动发送数据")
        send_layout = QVBoxLayout()
        send_format_layout = QHBoxLayout(); send_format_layout.addWidget(QLabel("发送格式:")); self.ascii_radio = QRadioButton("ASCII"); self.ascii_radio.setChecked(True); self.hex_radio = QRadioButton("HEX"); send_format_layout.addWidget(self.ascii_radio); send_format_layout.addWidget(self.hex_radio); send_format_layout.addStretch()
        send_data_layout = QHBoxLayout(); self.send_data_edit = QLineEdit(); self.send_data_edit.setPlaceholderText("在此输入要发送的内容..."); self.send_btn = QPushButton("发送"); send_data_layout.addWidget(self.send_data_edit); send_data_layout.addWidget(self.send_btn)
        send_layout.addLayout(send_format_layout); send_layout.addLayout(send_data_layout); send_group.setLayout(send_layout)
        main_layout.addWidget(send_group)

        # --- FPGA 模拟器 ---
        sim_group = QGroupBox("FPGA模拟器")
        sim_main_layout = QVBoxLayout(sim_group) # 主布局

        # --- LA 模拟部分 ---
        la_sim_layout = QHBoxLayout()
        self.open_la_editor_btn = QPushButton("打开LA波形编辑器")
        la_sim_layout.addWidget(self.open_la_editor_btn)
        la_sim_layout.addStretch()
        sim_main_layout.addLayout(la_sim_layout)

        # --- DDS 波形模拟部分 (新增) ---
        dds_sim_group = QGroupBox("模拟示波器波形数据 (0xAA)")
        dds_sim_layout = QGridLayout(dds_sim_group)

        dds_sim_layout.addWidget(QLabel("波形类型:"), 0, 0)
        self.dds_sim_wave_combo = QComboBox()
        self.dds_sim_wave_combo.addItems(["Sine", "Square", "Triangle", "Sawtooth"])
        dds_sim_layout.addWidget(self.dds_sim_wave_combo, 0, 1)

        dds_sim_layout.addWidget(QLabel("频率 (Hz):"), 0, 2)
        self.dds_sim_freq_spin = QSpinBox()
        self.dds_sim_freq_spin.setRange(1, 10_000_000) # 1Hz to 10MHz
        self.dds_sim_freq_spin.setValue(1000)
        dds_sim_layout.addWidget(self.dds_sim_freq_spin, 0, 3)

        dds_sim_layout.addWidget(QLabel("幅度 (0-1):"), 1, 0)
        self.dds_sim_amp_spin = QDoubleSpinBox()
        self.dds_sim_amp_spin.setRange(0.0, 1.0)
        self.dds_sim_amp_spin.setSingleStep(0.1)
        self.dds_sim_amp_spin.setValue(1.0)
        dds_sim_layout.addWidget(self.dds_sim_amp_spin, 1, 1)

        dds_sim_layout.addWidget(QLabel("直流偏置 (-1 to 1):"), 1, 2)
        self.dds_sim_offset_spin = QDoubleSpinBox()
        self.dds_sim_offset_spin.setRange(-1.0, 1.0)
        self.dds_sim_offset_spin.setSingleStep(0.1)
        self.dds_sim_offset_spin.setValue(0.0)
        dds_sim_layout.addWidget(self.dds_sim_offset_spin, 1, 3)


        dds_sim_layout.addWidget(QLabel("发送间隔 (ms):"), 2, 0)
        self.dds_sim_interval_spin = QSpinBox()
        self.dds_sim_interval_spin.setRange(10, 1000) # 10ms to 1s interval
        self.dds_sim_interval_spin.setValue(50) # Default 50ms (20 FPS)
        dds_sim_layout.addWidget(self.dds_sim_interval_spin, 2, 1)

        self.dds_sim_send_btn = QPushButton("开始发送波形")
        self.dds_sim_send_btn.setCheckable(True)
        dds_sim_layout.addWidget(self.dds_sim_send_btn, 2, 2, 1, 2) # Span 2 columns

        sim_main_layout.addWidget(dds_sim_group)
        # --- DDS 模拟结束 ---

        main_layout.addWidget(sim_group)

        # --- 通信日志 (保持不变) ---
        log_group = QGroupBox("通信日志 (包含接收到的数据)")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 9)); log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group, 1) # 让日志区域可扩展

    def setup_connections(self):
        self.connect_btn.clicked.connect(self.toggle_listening)
        self.send_btn.clicked.connect(self.send_manual_data)
        self.open_la_editor_btn.clicked.connect(self.open_waveform_editor)

        # --- 新增连接 ---
        self.dds_sim_send_btn.clicked.connect(self.toggle_dds_simulation)
        self.dds_sim_timer.timeout.connect(self.send_simulated_osc_data_tick) # 连接定时器
        # --- 结束新增 ---

        self.udp_client.listening_status.connect(self.on_listening_status_changed)
        self.udp_client.data_received.connect(self.on_data_received)
        self.udp_client.log_message.connect(self.log_message)

    def open_waveform_editor(self):
        """打开或激活波形编辑器窗口"""
        if self.waveform_editor_window is None:
            self.waveform_editor_window = WaveformEditorWindow()
            self.waveform_editor_window.data_ready_to_send.connect(self._send_packet_and_log) # 修改连接的目标
        self.waveform_editor_window.show()
        self.waveform_editor_window.activateWindow()

    def toggle_listening(self):
        if self.connect_btn.isChecked():
            local_ip = self.local_ip_combo.currentText(); local_port = self.local_port_spin.value()
            target_ip = self.target_ip_input.text(); target_port = self.target_port_spin.value()
            # 验证 IP 和端口
            # (省略了 IP 验证逻辑，假设输入有效)
            if not target_ip or target_port <= 0:
                 QMessageBox.warning(self, "错误", "请输入有效的目标 IP 和端口。")
                 self.connect_btn.setChecked(False)
                 return
            self.target_address = (target_ip, target_port)
            self.log_message(f"准备启动会话: 本地 {local_ip}:{local_port}, 目标 {target_ip}:{target_port}")
            self.udp_client.start_listening(local_ip, local_port)
        else:
            self.udp_client.stop_listening()
            # 如果 DDS 模拟正在运行，则停止它
            if self.dds_sim_timer.isActive():
                self.stop_dds_simulation()


    def on_listening_status_changed(self, is_listening: bool, message: str):
        self.log_message(message)
        if is_listening:
            self.connect_btn.setText("停止监听"); self.connect_btn.setChecked(True)
            self.status_label.setText("监听中")
            if self.target_address:
                self.log_message(f"✅ 会话已启动. 目标: {self.target_address[0]}:{self.target_address[1]}")
            else:
                 self.log_message(f"✅ 会话已启动, 但目标地址未设置。")
            for w in [self.local_ip_combo, self.local_port_spin, self.target_ip_input, self.target_port_spin]: w.setEnabled(False)
        else:
            self.connect_btn.setText("开始监听"); self.connect_btn.setChecked(False)
            self.status_label.setText("空闲"); self.log_message("🔌 会话已停止。")
            # 如果 DDS 模拟正在运行，也停止它
            if self.dds_sim_timer.isActive():
                self.stop_dds_simulation()
            for w in [self.local_ip_combo, self.local_port_spin, self.target_ip_input, self.target_port_spin]: w.setEnabled(True)

    def _send_packet(self, data_to_send: bytes) -> bool:
        """内部方法，用于发送数据包（不记录日志）"""
        if not self.udp_client.isRunning() or not self.target_address:
            QMessageBox.warning(self, "发送错误", "发送数据包失败。请先设置目标并开始监听。")
            return False
        try:
            self.send_socket.sendto(data_to_send, self.target_address)
            return True
        except Exception as e:
            self.log_message(f"发送错误: {e}")
            QMessageBox.critical(self, "发送错误", f"发送数据失败: {e}")
            return False

    def _send_packet_and_log(self, data_to_send: bytes, source_description: str = "未知"):
        """发送数据包并记录日志"""
        if self._send_packet(data_to_send):
            hex_string = ' '.join([f'{b:02X}' for b in data_to_send])
            self.log_message(f"发送 ({source_description}) >> {hex_string}")

    def send_manual_data(self):
        """发送手动输入的数据"""
        text_to_send = self.send_data_edit.text()
        if not text_to_send: return
        data_to_send = b''
        try:
            if self.ascii_radio.isChecked():
                data_to_send = text_to_send.encode('utf-8')
            else: # HEX 格式
                hex_string = text_to_send.strip().replace(' ', '').replace(',', '')
                if len(hex_string) % 2 != 0:
                    hex_string = '0' + hex_string
                data_to_send = bytes.fromhex(hex_string)
        except ValueError:
            QMessageBox.warning(self, "格式错误", "无效的十六进制数据格式。"); return
        except Exception as e:
             QMessageBox.warning(self, "编码错误", f"处理输入数据时出错: {e}"); return

        self._send_packet_and_log(data_to_send, "手动")


    # --- 新增 DDS 模拟相关方法 ---
    def toggle_dds_simulation(self):
        """开始或停止发送模拟 DDS 波形数据"""
        if self.dds_sim_send_btn.isChecked(): # 如果按下按钮（开始）
            if not self.udp_client.isRunning() or not self.target_address:
                 QMessageBox.warning(self, "错误", "请先开始监听并设置目标地址。")
                 self.dds_sim_send_btn.setChecked(False)
                 return
            self.start_dds_simulation()
        else: # 如果按钮弹起（停止）
            self.stop_dds_simulation()

    def start_dds_simulation(self):
        """启动 DDS 模拟定时器"""
        interval_ms = self.dds_sim_interval_spin.value()
        self.dds_sim_timer.setInterval(interval_ms)
        self.dds_sim_phase_accumulator = 0.0 # 重置相位
        self.dds_sim_timer.start()
        self.dds_sim_send_btn.setText("停止发送波形")
        self.log_message(f"🟢 开始发送模拟示波器波形 (间隔: {interval_ms}ms)")
        # 禁用参数设置控件
        for w in [self.dds_sim_wave_combo, self.dds_sim_freq_spin, self.dds_sim_amp_spin, self.dds_sim_offset_spin, self.dds_sim_interval_spin]:
             w.setEnabled(False)

    def stop_dds_simulation(self):
        """停止 DDS 模拟定时器"""
        self.dds_sim_timer.stop()
        self.dds_sim_send_btn.setText("开始发送波形")
        self.dds_sim_send_btn.setChecked(False) # 确保按钮状态正确
        self.log_message("🔴 停止发送模拟示波器波形")
        # 启用参数设置控件
        for w in [self.dds_sim_wave_combo, self.dds_sim_freq_spin, self.dds_sim_amp_spin, self.dds_sim_offset_spin, self.dds_sim_interval_spin]:
             w.setEnabled(True)

    def generate_waveform(self, wave_type, frequency, amplitude, offset, samples, start_phase):
        """生成指定类型的波形数据 (-1.0 to 1.0)"""
        t = np.arange(samples)
        # 计算每个样本点的相位增量
        # 注意：这里的 frequency 是信号本身的频率，与 FPGA 内部的采样率无关
        # 我们模拟的是最终输出给示波器的采样点，需要计算每个点对应的相位
        # 假设 FPGA 内部有一个固定的高采样率 Fs_internal，而我们发送的 512 点代表一个时间窗口 Tw
        # 信号频率 f 对应的每个点的相位增量 = 2 * pi * f / Fs_output
        # Fs_output = samples / Tw
        # Tw 不确定，我们简化模型，假设这 512 个点覆盖了若干个信号周期
        # 相位 = 2 * pi * frequency * (t / samples) # 这样频率的单位更像是 "周期数/窗口"
        # 或者更真实的模拟：相位 = start_phase + 2 * pi * frequency * (t / output_sample_rate)
        # 这里我们使用累加相位的方式，更接近 DDS
        # 估算输出采样率 (假设发送间隔就是采样窗口时间)
        output_sample_rate_est = samples / (self.dds_sim_interval_spin.value() / 1000.0)
        phase_increment = 2 * math.pi * frequency / output_sample_rate_est if output_sample_rate_est > 0 else 0
        phases = start_phase + phase_increment * t
        new_end_phase = phases[-1] % (2 * math.pi) # 计算结束相位用于下次累加


        if wave_type == "Sine":
            wave = np.sin(phases)
        elif wave_type == "Square":
            wave = np.sign(np.sin(phases))
        elif wave_type == "Triangle":
            # 归一化相位到 0-1
            norm_phase = (phases / (2 * math.pi)) % 1.0
            wave = 2 * (2 * np.abs(norm_phase - 0.5) - 0.5) # 从 -1 到 1
        elif wave_type == "Sawtooth":
            # 归一化相位到 0-1
            norm_phase = (phases / (2 * math.pi)) % 1.0
            wave = 2 * norm_phase - 1.0 # 从 -1 到 1
        else:
            wave = np.zeros(samples)

        # 应用幅度和偏置
        wave = offset + amplitude * wave
        # 限制在 -1.0 到 1.0
        wave = np.clip(wave, -1.0, 1.0)
        return wave, new_end_phase

    # ### 优化部分 START ###
    def send_simulated_osc_data_tick(self):
        """定时器触发的函数，生成并发送一帧模拟的示波器数据 (0xAA)"""
        try:
            # 1. 获取参数
            wave_type = self.dds_sim_wave_combo.currentText()
            frequency = self.dds_sim_freq_spin.value()
            amplitude = self.dds_sim_amp_spin.value()
            offset = self.dds_sim_offset_spin.value()

            # 2. 生成波形数据 (-1.0 to 1.0)
            wave_float, next_phase = self.generate_waveform(
                wave_type, frequency, amplitude, offset,
                self.dds_sim_samples, self.dds_sim_phase_accumulator
            )
            self.dds_sim_phase_accumulator = next_phase # 更新相位累加器

            # 3. 转换为 uint8 (0-255)
            wave_uint8 = np.clip(np.round((wave_float + 1.0) / 2.0 * 255), 0, 255).astype(np.uint8)
            wave_bytes = wave_uint8.tobytes()

            # 4. 模拟频率值 (使用设置的频率)
            mock_freq_val = frequency
            # 频率打包为 4 字节大端序无符号整数
            freq_bytes = struct.pack('>I', mock_freq_val) # <--- 修改为 '>I' (4 bytes)

            # 5. 组合数据包 (Header 0xAA + 4字节Freq + 512字节Wave)
            try:
                 mock_header = bytes([PacketType.OSC_DATA])
            except NameError:
                 mock_header = bytes([0xAA]) # Fallback if PacketType fails

            full_packet = mock_header + freq_bytes + wave_bytes # <--- 包结构改变

            # 6. 发送数据包
            self._send_packet(full_packet) # 只发送，不记录日志避免刷屏

        except Exception as e:
            error_msg = f"生成或发送模拟示波器数据时出错: {e}"
            self.log_message(error_msg)
            # 停止发送防止连续出错
            self.stop_dds_simulation()
            QMessageBox.critical(self, "模拟错误", error_msg)
    # ### 优化部分 END ###


    def on_data_received(self, data: bytes, address: tuple):
        """处理接收到的数据，只记录日志"""
        if self.target_address and address[0] != self.target_address[0]:
             self.log_message(f"忽略 << 来自 {address[0]}:{address[1]} 的数据 (非目标IP)")
             return

        hex_string = ' '.join([f'{b:02X}' for b in data])
        self.log_message(f"接收 << 来自 {address[0]}:{address[1]} : {hex_string}")

    def log_message(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.ensureCursorVisible()

    def load_settings(self):
        self.target_ip_input.setText(self.settings.value("target_ip", "127.0.0.1"))
        self.target_port_spin.setValue(int(self.settings.value("target_port", 8088)))
        self.local_port_spin.setValue(int(self.settings.value("local_port", 8080)))
        saved_local_ip = self.settings.value("local_ip", "")
        if saved_local_ip and self.local_ip_combo.findText(saved_local_ip) != -1:
            self.local_ip_combo.setCurrentText(saved_local_ip)
        elif self.local_ip_combo.count() > 0:
             self.local_ip_combo.setCurrentIndex(0)

        self.log_message("加载已保存的网络设置。")

    def save_settings(self):
        self.settings.setValue("target_ip", self.target_ip_input.text())
        self.settings.setValue("target_port", self.target_port_spin.value())
        self.settings.setValue("local_ip", self.local_ip_combo.currentText())
        self.settings.setValue("local_port", self.local_port_spin.value())
        self.log_message("网络设置已保存。")

    def closeEvent(self, event):
        self.save_settings()
        self.udp_client.stop_listening()
        self.send_socket.close()
        # 停止 DDS 模拟定时器
        if self.dds_sim_timer.isActive():
            self.dds_sim_timer.stop()
        if self.waveform_editor_window:
            self.waveform_editor_window.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setOrganizationName("MyCompany")
    app.setApplicationName("UdpGuiTool")
    tool = UdpGuiTool()
    tool.show()
    sys.exit(app.exec_())