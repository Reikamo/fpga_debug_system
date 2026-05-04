# test.py

import sys
import socket
import struct
from enum import IntEnum
from datetime import datetime
from typing import Callable

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTabWidget, QGroupBox, QLabel,
                             QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox,
                             QComboBox, QTextEdit, QGridLayout, QCheckBox,
                             QMessageBox, QRadioButton)
from PyQt5.QtCore import QThread, pyqtSignal, QSettings, Qt
from PyQt5.QtGui import QFont

# --- 辅助函数：获取本机IP ---
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

# --- 1. 网络客户端 (UDP) ---
class UdpClient(QThread):
    listening_status = pyqtSignal(bool, str)
    data_received = pyqtSignal(bytes, tuple)
    log_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._socket = None
        self._is_running = False
        self.target_address = None
        self.local_address = None

    def start_listening(self, local_ip: str, local_port: int, target_host: str, target_port: int):
        self.local_address = (local_ip, local_port)
        self.target_address = (target_host, target_port)
        self._is_running = True
        self.start()

    def stop_listening(self):
        self._is_running = False
        if self._socket:
            try: self._socket.close()
            except OSError: pass
        self.wait()

    def send_packet(self, packet_data: bytes) -> bool:
        if self._socket and self.target_address:
            try:
                self._socket.sendto(packet_data, self.target_address)
                return True
            except socket.error as e:
                self.log_message.emit(f"发送错误: {e}")
                return False
        else:
            self.log_message.emit("发送失败: 未设置目标或监听未启动。")
            return False

    def run(self):
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.bind(self.local_address)
            self.listening_status.emit(True, f"正在监听 {self.local_address[0]}:{self.local_address[1]}...")
        except Exception as e:
            self.listening_status.emit(False, f"绑定本地地址失败: {e}")
            self._is_running = False
            return

        while self._is_running:
            try:
                data, address = self._socket.recvfrom(4096)
                if data and address[0] == self.target_address[0]:
                    self.data_received.emit(data, address)
            except socket.error:
                break
        
        self.listening_status.emit(False, "监听已停止。")


# --- 2. 数据包构建器 (简化版) ---
class CommandType(IntEnum):
    SPI_CONFIG=0x01; I2C_CONFIG=0x02; UART_CONFIG=0x03; PWM_CONFIG=0x04
    SPI_TRANSFER=0x11; I2C_TRANSFER=0x12; UART_TRANSFER=0x13; PWM_SET=0x14
class PacketBuilder:
    @staticmethod
    def build_packet(cmd_type: CommandType, payload: bytes = b''):
        header = struct.pack('!B', cmd_type)
        return header + payload

# --- 3. UI 控件 ---
class SPIWidget(QWidget):
    def __init__(self, packet_sender: Callable):
        super().__init__(); self.packet_sender = packet_sender; self.init_ui()
    def init_ui(self):
        layout=QVBoxLayout(self); config_group=QGroupBox("SPI配置"); config_layout=QGridLayout()
        config_layout.addWidget(QLabel("时钟分频:"),0,0); self.clock_div_spin=QSpinBox(); self.clock_div_spin.setRange(1,65535); self.clock_div_spin.setValue(100); config_layout.addWidget(self.clock_div_spin,0,1)
        config_layout.addWidget(QLabel("SPI模式:"),1,0); self.mode_combo=QComboBox(); self.mode_combo.addItems(["模式0","模式1","模式2","模式3"]); config_layout.addWidget(self.mode_combo,1,1)
        config_layout.addWidget(QLabel("CS极性:"),2,0); self.cs_polarity_combo=QComboBox(); self.cs_polarity_combo.addItems(["低电平有效","高电平有效"]); config_layout.addWidget(self.cs_polarity_combo,2,1)
        config_btn=QPushButton("配置SPI"); config_btn.clicked.connect(self.configure_spi); config_layout.addWidget(config_btn,3,0,1,2)
        config_group.setLayout(config_layout); layout.addWidget(config_group); transfer_group=QGroupBox("SPI传输"); transfer_layout=QVBoxLayout(); send_layout=QHBoxLayout()
        send_layout.addWidget(QLabel("发送数据(HEX):")); self.send_data_edit=QLineEdit(); self.send_data_edit.setPlaceholderText("例如: 01 02 03 FF"); send_layout.addWidget(self.send_data_edit)
        send_btn=QPushButton("发送"); send_btn.clicked.connect(self.send_spi_data); send_layout.addWidget(send_btn); transfer_layout.addLayout(send_layout)
        transfer_layout.addWidget(QLabel("接收数据:")); self.receive_data_text=QTextEdit(); self.receive_data_text.setReadOnly(True); transfer_layout.addWidget(self.receive_data_text)
        transfer_group.setLayout(transfer_layout); layout.addWidget(transfer_group); layout.addStretch()
    def configure_spi(self):
        payload = struct.pack('!HBB', self.clock_div_spin.value(), self.mode_combo.currentIndex(), self.cs_polarity_combo.currentIndex())
        self.packet_sender(PacketBuilder.build_packet(CommandType.SPI_CONFIG, payload))
    def send_spi_data(self):
        try: self.packet_sender(PacketBuilder.build_packet(CommandType.SPI_TRANSFER, bytes.fromhex(self.send_data_edit.text().strip().replace(' ',''))))
        except ValueError: QMessageBox.warning(self, "错误", "无效的十六进制数据格式")

class I2CWidget(QWidget):
    def __init__(self, packet_sender: Callable):
        super().__init__(); self.packet_sender=packet_sender; self.init_ui()
    def init_ui(self):
        layout=QVBoxLayout(self); config_group=QGroupBox("I2C配置"); config_layout=QGridLayout()
        config_layout.addWidget(QLabel("时钟分频:"),0,0); self.clock_div_spin=QSpinBox(); self.clock_div_spin.setRange(1,65535); self.clock_div_spin.setValue(400); config_layout.addWidget(self.clock_div_spin,0,1)
        config_layout.addWidget(QLabel("从设备地址 (7-bit):"),1,0); self.slave_addr_spin=QSpinBox(); self.slave_addr_spin.setRange(0,127); self.slave_addr_spin.setDisplayIntegerBase(16); self.slave_addr_spin.setPrefix("0x"); config_layout.addWidget(self.slave_addr_spin,1,1)
        config_btn=QPushButton("配置I2C"); config_btn.clicked.connect(self.configure_i2c); config_layout.addWidget(config_btn,2,0,1,2)
        config_group.setLayout(config_layout); layout.addWidget(config_group); transfer_group=QGroupBox("I2C传输"); transfer_layout=QVBoxLayout(); write_layout=QHBoxLayout()
        write_layout.addWidget(QLabel("写入数据 (HEX):")); self.write_data_edit=QLineEdit(); write_layout.addWidget(self.write_data_edit)
        write_btn=QPushButton("写入"); write_btn.clicked.connect(self.write_i2c_data); write_layout.addWidget(write_btn); transfer_layout.addLayout(write_layout)
        read_layout=QHBoxLayout(); read_layout.addWidget(QLabel("读取字节数:")); self.read_count_spin=QSpinBox(); self.read_count_spin.setRange(1,255); read_layout.addWidget(self.read_count_spin)
        read_btn=QPushButton("读取"); read_btn.clicked.connect(self.read_i2c_data); read_layout.addWidget(read_btn); transfer_layout.addLayout(read_layout)
        transfer_layout.addWidget(QLabel("接收数据:")); self.receive_data_text=QTextEdit(); self.receive_data_text.setReadOnly(True); transfer_layout.addWidget(self.receive_data_text)
        transfer_group.setLayout(transfer_layout); layout.addWidget(transfer_group); layout.addStretch()
    def configure_i2c(self):
        payload = struct.pack('!HB', self.clock_div_spin.value(), self.slave_addr_spin.value())
        self.packet_sender(PacketBuilder.build_packet(CommandType.I2C_CONFIG, payload))
    def write_i2c_data(self):
        try: payload=struct.pack('!B',0)+bytes.fromhex(self.write_data_edit.text().strip().replace(' ','')); self.packet_sender(PacketBuilder.build_packet(CommandType.I2C_TRANSFER,payload))
        except ValueError: QMessageBox.warning(self,"错误","无效的十六进制数据格式")
    def read_i2c_data(self):
        payload = struct.pack('!BB',1,self.read_count_spin.value()); self.packet_sender(PacketBuilder.build_packet(CommandType.I2C_TRANSFER,payload))

class UARTWidget(QWidget):
    def __init__(self, packet_sender: Callable):
        super().__init__(); self.packet_sender = packet_sender; self.init_ui()
    def init_ui(self):
        layout = QVBoxLayout(self); config_group = QGroupBox("UART配置"); config_layout = QGridLayout()
        config_layout.addWidget(QLabel("波特率:"), 0, 0); self.baud_rate_combo = QComboBox(); self.baud_rate_combo.addItems(["9600", "19200", "38400", "57600", "115200", "921600", "1000000"]); self.baud_rate_combo.setCurrentText("115200"); config_layout.addWidget(self.baud_rate_combo, 0, 1)
        config_layout.addWidget(QLabel("停止位:"), 2, 0); self.stop_bits_combo = QComboBox(); self.stop_bits_combo.addItems(["1", "2"]); config_layout.addWidget(self.stop_bits_combo, 2, 1)
        config_layout.addWidget(QLabel("校验位:"), 3, 0); self.parity_combo = QComboBox(); self.parity_combo.addItems(["无", "奇校验", "偶校验"]); config_layout.addWidget(self.parity_combo, 3, 1)
        config_btn = QPushButton("配置UART"); config_btn.clicked.connect(self.configure_uart); config_layout.addWidget(config_btn, 4, 0, 1, 2)
        config_group.setLayout(config_layout); layout.addWidget(config_group)
        transfer_group = QGroupBox("UART传输"); transfer_layout = QVBoxLayout()
        send_format_layout = QHBoxLayout(); send_format_layout.addWidget(QLabel("发送格式:")); self.ascii_radio = QRadioButton("ASCII"); self.ascii_radio.setChecked(True); self.hex_radio = QRadioButton("HEX"); send_format_layout.addWidget(self.ascii_radio); send_format_layout.addWidget(self.hex_radio); send_format_layout.addStretch(); transfer_layout.addLayout(send_format_layout)
        send_layout = QHBoxLayout(); send_layout.addWidget(QLabel("发送数据:")); self.send_data_edit = QLineEdit(); send_layout.addWidget(self.send_data_edit)
        send_btn = QPushButton("发送"); send_btn.clicked.connect(self.send_uart_data); send_layout.addWidget(send_btn); transfer_layout.addLayout(send_layout)
        transfer_layout.addWidget(QLabel("接收数据:")); self.receive_data_text = QTextEdit(); self.receive_data_text.setReadOnly(True); transfer_layout.addWidget(self.receive_data_text)
        transfer_group.setLayout(transfer_layout); layout.addWidget(transfer_group); layout.addStretch()
    def configure_uart(self):
        FPGA_CLOCK = 50_000_000; baud_rate = int(self.baud_rate_combo.currentText()); baud_divisor = round(FPGA_CLOCK / baud_rate)
        if not (0 <= baud_divisor <= 65535): QMessageBox.warning(self, "错误", f"波特率 {baud_rate} 计算得分频值 {baud_divisor} 超出范围 (0-65535)"); return
        stop_bits_val = self.stop_bits_combo.currentIndex() & 0b11; parity_val = self.parity_combo.currentIndex() & 0b11
        flags = (stop_bits_val << 2) | parity_val; payload = struct.pack('!BH', flags, baud_divisor)
        self.packet_sender(PacketBuilder.build_packet(CommandType.UART_CONFIG, payload))
    def send_uart_data(self):
        text_to_send = self.send_data_edit.text(); data_to_send = b''
        if self.ascii_radio.isChecked(): data_to_send = text_to_send.encode('utf-8')
        else:
            try: data_to_send = bytes.fromhex(text_to_send.strip().replace(' ', '').replace(',', ''))
            except ValueError: QMessageBox.warning(self, "格式错误", "无效的十六进制数据格式。\n请输入如 'AA BB 01 02' 的字符串。"); return
        self.packet_sender(PacketBuilder.build_packet(CommandType.UART_TRANSFER, data_to_send))

class PWMWidget(QWidget):
    def __init__(self, packet_sender: Callable):
        super().__init__(); self.packet_sender=packet_sender; self.init_ui()
    def init_ui(self):
        layout=QVBoxLayout(self); config_group=QGroupBox("PWM配置"); config_layout=QGridLayout()
        config_layout.addWidget(QLabel("PWM通道:"),0,0); self.channel_spin=QSpinBox(); self.channel_spin.setRange(0,7); config_layout.addWidget(self.channel_spin,0,1)
        config_layout.addWidget(QLabel("频率(Hz):"),1,0); self.frequency_spin=QSpinBox(); self.frequency_spin.setRange(1,1000000); self.frequency_spin.setValue(1000); config_layout.addWidget(self.frequency_spin,1,1)
        config_layout.addWidget(QLabel("占空比(%):"),2,0); self.duty_cycle_spin=QDoubleSpinBox(); self.duty_cycle_spin.setRange(0.0,100.0); self.duty_cycle_spin.setValue(50.0); self.duty_cycle_spin.setSingleStep(0.1); config_layout.addWidget(self.duty_cycle_spin,2,1)
        self.enable_check=QCheckBox("使能PWM输出"); self.enable_check.setChecked(True); config_layout.addWidget(self.enable_check,3,0,1,2)
        config_btn=QPushButton("配置PWM"); config_btn.clicked.connect(self.configure_pwm); config_layout.addWidget(config_btn,4,0,1,2)
        config_group.setLayout(config_layout); layout.addWidget(config_group); layout.addStretch()
    def configure_pwm(self):
        duty = self.duty_cycle_spin.value() if self.enable_check.isChecked() else 0.0
        payload = struct.pack('!BIf', self.channel_spin.value(), self.frequency_spin.value(), duty / 100.0)
        self.packet_sender(PacketBuilder.build_packet(CommandType.PWM_CONFIG, payload))

# --- 4. 主窗口 ---
class FPGADebugger(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("MyCompany", "FPGADebuggerTest")
        self.udp_client = UdpClient()
        self.init_ui()
        self.setup_connections()
        self.load_settings()

    def init_ui(self):
        self.setWindowTitle("FPGA 调试器 (UDP独立版)")
        self.setGeometry(100, 100, 800, 700)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        connection_group = QGroupBox("UDP 通信设置")
        connection_layout = QGridLayout()
        connection_layout.addWidget(QLabel("本地IP:"), 0, 0); self.local_ip_combo = QComboBox(); self.local_ip_combo.setEditable(True); self.local_ip_combo.addItems(get_local_ips()); connection_layout.addWidget(self.local_ip_combo, 0, 1)
        connection_layout.addWidget(QLabel("本地端口:"), 0, 2); self.local_port_spin = QSpinBox(); self.local_port_spin.setRange(1, 65535); connection_layout.addWidget(self.local_port_spin, 0, 3)
        connection_layout.addWidget(QLabel("目标IP:"), 1, 0); self.target_ip_input = QLineEdit(); connection_layout.addWidget(self.target_ip_input, 1, 1)
        connection_layout.addWidget(QLabel("目标端口:"), 1, 2); self.target_port_spin = QSpinBox(); self.target_port_spin.setRange(1, 65535); connection_layout.addWidget(self.target_port_spin, 1, 3)
        self.connect_btn = QPushButton("开始监听"); self.connect_btn.setCheckable(True); connection_layout.addWidget(self.connect_btn, 0, 4, 2, 1)
        self.status_label = QLabel("空闲"); self.status_label.setAlignment(Qt.AlignCenter); connection_layout.addWidget(self.status_label, 0, 5, 2, 1)
        connection_group.setLayout(connection_layout); main_layout.addWidget(connection_group)

        self.tab_widget = QTabWidget()
        self.spi_widget = SPIWidget(self.send_packet)
        self.i2c_widget = I2CWidget(self.send_packet)
        self.uart_widget = UARTWidget(self.send_packet)
        self.pwm_widget = PWMWidget(self.send_packet)
        self.tab_widget.addTab(self.spi_widget, "SPI")
        self.tab_widget.addTab(self.i2c_widget, "I2C")
        self.tab_widget.addTab(self.uart_widget, "UART")
        self.tab_widget.addTab(self.pwm_widget, "PWM")
        main_layout.addWidget(self.tab_widget)
        
        display_options_group = QGroupBox("显示设置")
        display_options_layout = QHBoxLayout()
        display_options_layout.addWidget(QLabel("接收区显示格式:"))
        self.hex_radio = QRadioButton("HEX"); self.hex_radio.setChecked(True); display_options_layout.addWidget(self.hex_radio)
        self.ascii_radio = QRadioButton("ASCII"); display_options_layout.addWidget(self.ascii_radio); display_options_layout.addStretch()
        display_options_group.setLayout(display_options_layout)
        main_layout.addWidget(display_options_group)

        log_group = QGroupBox("通信日志")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 9)); log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

    def setup_connections(self):
        self.connect_btn.clicked.connect(self.toggle_listening)
        self.udp_client.listening_status.connect(self.on_listening_status_changed)
        self.udp_client.data_received.connect(self.on_data_received)
        self.udp_client.log_message.connect(self.log_message)

    def toggle_listening(self):
        if self.connect_btn.isChecked():
            local_ip = self.local_ip_combo.currentText(); local_port = self.local_port_spin.value()
            target_ip = self.target_ip_input.text(); target_port = self.target_port_spin.value()
            self.log_message(f"准备启动会话: 本地 {local_ip}:{local_port}, 目标 {target_ip}:{target_port}")
            self.udp_client.start_listening(local_ip, local_port, target_ip, target_port)
        else:
            self.udp_client.stop_listening()

    def on_listening_status_changed(self, is_listening: bool, message: str):
        self.log_message(message)
        if is_listening:
            self.connect_btn.setText("停止监听"); self.connect_btn.setChecked(True)
            self.status_label.setText("监听中")
            self.log_message(f"✅ 会话已启动. 目标: {self.udp_client.target_address[0]}:{self.udp_client.target_address[1]}")
            for w in [self.local_ip_combo, self.local_port_spin, self.target_ip_input, self.target_port_spin]: w.setEnabled(False)
        else:
            self.connect_btn.setText("开始监听"); self.connect_btn.setChecked(False)
            self.status_label.setText("空闲"); self.log_message("🔌 会话已停止。")
            for w in [self.local_ip_combo, self.local_port_spin, self.target_ip_input, self.target_port_spin]: w.setEnabled(True)
    
    def on_data_received(self, data: bytes, address: tuple):
        """根据包头分发接收到的数据，并添加时间戳和来源IP"""
        # --- MODIFIED SECTION START ---
        
        full_hex_string = ' '.join([f'{b:02X}' for b in data])
        self.log_message(f"接收: {full_hex_string}")

        if not data:
            return

        header = data[0]
        payload = data[1:]

        payload_hex_string = ' '.join([f'{b:02X}' for b in payload])
        
        if self.ascii_radio.isChecked():
            display_string = "".join(c if c.isprintable() or c in '\n\r\t' else f'<{ord(c):02X}>' for c in payload.decode('ascii', errors='ignore'))
        else:
            display_string = payload_hex_string
            
        # 构建带时间戳和来源IP的前缀
        timestamp = datetime.now().strftime("%H:%M:%S")
        source_ip = address[0]
        
        # 完整的显示信息
        full_display_string = f"[{timestamp}] From {source_ip}: {display_string}"
        
        # 根据包头分发
        if header == 0xDD: # UART
            self.uart_widget.receive_data_text.append(full_display_string)
        # elif header == 0xEE: # SPI (预留)
        #     self.spi_widget.receive_data_text.append(full_display_string)
        # elif header == 0xFF: # I2C (预留)
        #     self.i2c_widget.receive_data_text.append(full_display_string)
        else:
            self.log_message(f"警告: 收到未知包头 (0x{header:02X}) 的数据，未在接收区分发")
        
        # --- MODIFIED SECTION END ---

    def send_packet(self, packet_data: bytes) -> None:
        if self.udp_client.send_packet(packet_data):
            hex_string = ' '.join([f'{b:02X}' for b in packet_data])
            self.log_message(f"发送: {hex_string}")
        else:
            QMessageBox.warning(self, "发送错误", "发送数据包失败。请先设置目标并开始监听。")

    def log_message(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.ensureCursorVisible()

    def load_settings(self):
        self.target_ip_input.setText(self.settings.value("target_ip", "192.168.1.100"))
        self.target_port_spin.setValue(int(self.settings.value("target_port", 8080)))
        self.local_port_spin.setValue(int(self.settings.value("local_port", 8088)))
        saved_local_ip = self.settings.value("local_ip", self.local_ip_combo.itemText(0))
        if saved_local_ip and self.local_ip_combo.findText(saved_local_ip) != -1:
            self.local_ip_combo.setCurrentText(saved_local_ip)
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
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setOrganizationName("MyCompany")
    app.setApplicationName("FPGADebuggerTest")
    debugger = FPGADebugger()
    debugger.show()
    sys.exit(app.exec_())