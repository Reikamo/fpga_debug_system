# fpga_debugger_widget.py
import sys
import struct
from datetime import datetime
from typing import Callable  # 用于类型提示 Callable

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGroupBox,
                             QLabel, QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox,
                             QComboBox, QTextEdit, QGridLayout, QCheckBox, QMessageBox,
                             QRadioButton, QTableWidget, QHeaderView, QTableWidgetItem,
                             QDialog, QFormLayout)
from PyQt5.QtCore import pyqtSignal, Qt, QRegExp, QByteArray
from PyQt5.QtGui import QFont, QRegExpValidator, QIntValidator

from protocol import PacketType
from communication_manager import CommunicationManager
from oled_widget import OLEDWidget  # 导入独立的 OLED 控制窗口
from styles import apply_modern_theme

# ================== 辅助类: _PacketBuilder ==================
class _PacketBuilder:
    """内部辅助类，用于构建此模块专用的简化协议包。"""
    @staticmethod
    def build_packet(cmd_type: PacketType, payload: bytes = b''):
        """
        构建一个包含包头和载荷的数据包。
        Args:
            cmd_type (PacketType): 包类型枚举。
            payload (bytes): 数据包的有效载荷。
        Returns:
            bytes: 完整的协议数据包。
        """
        header = struct.pack('!B', cmd_type)
        return header + payload

# ================== 子控件: CANWidget ==================
class CANWidget(QWidget):
    """CAN 总线调试功能的界面控件。"""
    def __init__(self, packet_sender: Callable):
        super().__init__()
        self.packet_sender = packet_sender
        # 波特率名称到协议值的映射
        self.baud_rate_map = { "500 Kbps": 0, "250 Kbps": 1, "125 Kbps": 2, "62.5 Kbps": 3, "31.25 Kbps": 4 }
        self.init_ui()

    def init_ui(self):
        """初始化CAN控件的用户界面。"""
        layout = QVBoxLayout(self)

        # CAN 配置组
        config_group = QGroupBox("CAN配置")
        config_layout = QHBoxLayout()
        config_layout.addWidget(QLabel("波特率:"))
        self.baud_rate_combo = QComboBox()
        self.baud_rate_combo.addItems(self.baud_rate_map.keys()) # 添加波特率选项
        config_layout.addWidget(self.baud_rate_combo, 1) # 让下拉框占据更多空间
        config_btn = QPushButton("配置CAN")
        config_btn.clicked.connect(self.configure_can)
        config_layout.addWidget(config_btn)
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # CAN 传输组
        transfer_group = QGroupBox("CAN传输")
        transfer_layout = QGridLayout() # 使用网格布局更整齐
        transfer_layout.addWidget(QLabel("CAN ID (Hex, 11-bit):"), 0, 0)
        self.can_id_edit = QLineEdit("000") # 默认ID
        # 验证器限制输入为1到3位十六进制字符
        self.can_id_edit.setValidator(QRegExpValidator(QRegExp("[0-9A-Fa-f]{1,3}")))
        transfer_layout.addWidget(self.can_id_edit, 0, 1)
        transfer_layout.addWidget(QLabel("Data (Hex, 1 Byte):"), 1, 0)
        self.data_edit = QLineEdit()
        self.data_edit.setPlaceholderText("XX") # 提示输入格式
        # 验证器限制输入为0到2位十六进制字符
        self.data_edit.setValidator(QRegExpValidator(QRegExp("[0-9A-Fa-f]{0,2}")))
        transfer_layout.addWidget(self.data_edit, 1, 1)
        send_btn = QPushButton("发送CAN帧")
        send_btn.clicked.connect(self.send_can_frame)
        # 发送按钮跨两行
        transfer_layout.addWidget(send_btn, 0, 2, 2, 1)
        transfer_group.setLayout(transfer_layout)
        layout.addWidget(transfer_group)

        # CAN 接收数据组
        receive_group = QGroupBox("接收数据")
        receive_layout = QVBoxLayout()
        self.receive_data_text = QTextEdit()
        self.receive_data_text.setReadOnly(True) # 设置为只读
        self.receive_data_text.setFont(QFont("Courier", 9)) # 使用等宽字体
        receive_layout.addWidget(self.receive_data_text)
        receive_group.setLayout(receive_layout)
        layout.addWidget(receive_group)

        layout.addStretch() # 添加弹性空间

    def configure_can(self):
        """发送 CAN 波特率配置命令 (A4)。"""
        selected_baud_text = self.baud_rate_combo.currentText()
        baud_val = self.baud_rate_map.get(selected_baud_text, 0) # 获取对应的协议值
        # 协议载荷：1字节，低3位有效
        payload = struct.pack('!B', baud_val & 0b111)
        # 发送数据包
        if self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_CAN_CONFIG, payload)):
            QMessageBox.information(self, "成功", f"CAN波特率配置({selected_baud_text})命令(A4)已发送。")
        # else: 发送失败的消息由 packet_sender 处理

    def send_can_frame(self):
        """发送 CAN 数据帧传输命令 (A5)。"""
        try:
            # 获取并验证 CAN ID
            can_id_str = self.can_id_edit.text().strip()
            if not can_id_str:
                QMessageBox.warning(self, "错误", "CAN ID 不能为空。")
                return
            can_id = int(can_id_str, 16)
            if not (0 <= can_id <= 0x7FF): # 11位标准帧 ID 范围
                QMessageBox.warning(self, "错误", "CAN ID 超出 11 位范围 (0x000 - 0x7FF)。")
                return

            # 获取并验证 CAN 数据 (限制为1字节)
            data_str = self.data_edit.text().strip()
            hex_str = "".join(data_str.split()) # 移除空格
            if len(hex_str) == 0:
                can_data_byte = 0 # 如果为空，默认为0
            elif len(hex_str) <= 2:
                hex_str = hex_str.zfill(2) # 不足两位前面补0
                can_data_byte = int(hex_str, 16)
            else:
                QMessageBox.warning(self, "错误", "Data 必须为 1 字节 (0-2 个十六进制字符)。")
                return

            # 构建协议载荷 (3字节)
            # 协议格式: [23:13] CAN ID (11位), [12:5] CAN Data (8位), [4:0] 保留 (5位)
            # 将它们组合成一个24位的值
            value_24bit = (can_id << 13) | (can_data_byte << 5)
            # 打包为大端序4字节整数，然后取后3个字节
            payload = struct.pack('>I', value_24bit)[-3:]

            # 发送数据包
            if self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_CAN_TRANSFER, payload)):
                QMessageBox.information(self, "成功", f"CAN帧发送命令(A5)已发送。ID=0x{can_id:03X}, Data=0x{can_data_byte:02X}")
            # else: 发送失败的消息由 packet_sender 处理

        except ValueError:
            QMessageBox.warning(self, "格式错误", "无效的十六进制数据格式 (ID 或 Data)。")
        except Exception as e:
            QMessageBox.critical(self, "发送错误", f"发送CAN帧时发生未知错误: {e}")


# ================== 子控件: CustomDOWidget ==================
class CustomDOWidget(QWidget):
    """8通道自定义数字信号输出 (DO) 的界面控件。"""
    def __init__(self, packet_sender: Callable):
        super().__init__()
        self.packet_sender = packet_sender
        self.init_ui()

    def init_ui(self):
        """初始化DO自定义控件的用户界面。"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        table_group = QGroupBox("8通道自定义输出配置")
        table_layout = QVBoxLayout()
        self.table = QTableWidget(8, 3) # 8行 (CH0-CH7), 3列
        self.table.setHorizontalHeaderLabels(["数据长度 (位)", "分频系数", "自定义数据 (二进制)"])
        self.table.setVerticalHeaderLabels([f"CH{i}" for i in range(8)]) # 行标签
        # 让最后一列 (自定义数据) 自动伸展
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        # 验证器
        uint32_validator = QRegExpValidator(QRegExp("[0-9]{1,10}")) # 限制输入为最多10位数字
        bin_validator = QRegExpValidator(QRegExp("[01]+")) # 限制输入为0或1

        for i in range(8):
            # 数据长度 SpinBox
            len_spin = QSpinBox()
            len_spin.setRange(0, 255) # 协议限制
            self.table.setCellWidget(i, 0, len_spin)

            # 分频系数 SpinBox
            period_spin = QSpinBox()
            period_spin.setRange(0, 65535) # 协议限制
            self.table.setCellWidget(i, 1, period_spin)

            # 自定义数据 LineEdit
            data_edit = QLineEdit()
            data_edit.setPlaceholderText("例如: 1111000010101010")
            data_edit.setValidator(bin_validator)
            # 当数据变化时，自动更新对应的长度 SpinBox
            data_edit.textChanged.connect(lambda text, spin_box=len_spin: self._on_data_text_changed(text, spin_box))
            self.table.setCellWidget(i, 2, data_edit)

        table_layout.addWidget(self.table)
        table_group.setLayout(table_layout)

        # 控制按钮
        button_layout = QHBoxLayout()
        apply_config_btn = QPushButton("应用长度与周期")
        send_data_btn = QPushButton("发送通道数据")
        apply_config_btn.clicked.connect(self.apply_lengths_and_periods)
        send_data_btn.clicked.connect(self.send_channel_data)
        button_layout.addStretch() # 按钮靠右
        button_layout.addWidget(apply_config_btn)
        button_layout.addWidget(send_data_btn)

        main_layout.addWidget(table_group)
        main_layout.addLayout(button_layout)

    def _on_data_text_changed(self, text: str, len_spin: QSpinBox):
        """当自定义数据文本框内容改变时，更新对应行的数据长度 SpinBox。"""
        current_len = len(text)
        len_spin.blockSignals(True) # 暂时阻止信号，避免循环触发
        len_spin.setMinimum(current_len) # 确保长度不小于实际输入
        len_spin.setValue(current_len) # 设置为当前长度
        len_spin.blockSignals(False) # 恢复信号

    def apply_lengths_and_periods(self):
        """发送 DO 配置命令 (B2)，设置所有通道的数据长度和分频系数。"""
        data_lengths = bytearray()
        period_lengths = bytearray()
        try:
            # 协议要求数据从 CH7 到 CH0 依次排列
            for i in range(7, -1, -1):
                len_val = self.table.cellWidget(i, 0).value() # 获取数据长度 (0-255)
                period_val = self.table.cellWidget(i, 1).value() # 获取分频系数 (0-65535)
                # 数据长度 (8 * 1 byte)
                data_lengths.extend(struct.pack('!B', len_val))
                # 分频系数 (8 * 2 bytes, 大端)
                period_lengths.extend(struct.pack('!H', period_val))

            # 组合载荷 (8字节长度 + 16字节周期 = 24字节)
            payload = data_lengths + period_lengths
            if self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_DO_CONFIG, payload)):
                QMessageBox.information(self, "成功", "长度与周期配置命令(B2)已发送。")
            # else: 发送失败消息由 packet_sender 处理
        except Exception as e:
             QMessageBox.critical(self, "错误", f"构建或发送DO配置时出错: {e}")

    def send_channel_data(self):
        """发送 DO 数据命令 (B3)，包含所有通道的自定义数据。"""
        final_payload = bytearray()
        try:
            # 协议要求数据从 CH7 到 CH0 依次排列，每个通道固定 32 字节
            for i in range(7, -1, -1):
                bin_str = self.table.cellWidget(i, 2).text() # 获取二进制字符串
                total_len = self.table.cellWidget(i, 0).value() # 获取配置的数据长度

                # --- 数据处理和填充 ---
                # 1. 长度调整：如果输入不足，用0填充；如果超出，截断
                if len(bin_str) < total_len:
                    bin_str += '0' * (total_len - len(bin_str))
                elif len(bin_str) > total_len:
                    bin_str = bin_str[:total_len]

                # 2. 字节对齐：在前面补0，使长度成为8的倍数
                if len(bin_str) % 8 != 0:
                    padding = 8 - (len(bin_str) % 8)
                    bin_str = '0' * padding + bin_str

                # 3. 转换为字节
                if not bin_str:
                    channel_data = bytearray()
                else:
                    num_bytes = len(bin_str) // 8
                    channel_data = bytearray()
                    for j in range(num_bytes):
                        byte_val = int(bin_str[j*8 : (j+1)*8], 2) # 每8位转为一个字节
                        channel_data.append(byte_val)

                # 4. 填充到 32 字节：协议要求每个通道固定 32 字节
                if len(channel_data) > 32:
                    channel_data = channel_data[:32] # 超出则截断 (理论上不应发生，因为长度限制为255位)
                else:
                    channel_data.extend([0] * (32 - len(channel_data))) # 不足则补0

                # 将当前通道的 32 字节数据添加到总载荷
                final_payload.extend(channel_data)

            # 发送数据包 (总载荷 8 * 32 = 256 字节)
            if self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_DO_DATA, final_payload)):
                 QMessageBox.information(self, "成功", "通道数据(B3)已发送。")
            # else: 发送失败消息由 packet_sender 处理
        except Exception as e:
             QMessageBox.warning(self, "错误", f"处理通道 {i} 数据时出错: {e}")


# ================== 新增: SpiFlashToolDialog ==================
class SpiFlashToolDialog(QDialog):
    """
    一个用于发送 SPI Flash 特定指令的弹出对话框。
    (此版本适配 FPGADebuggerWidget 的 SPIWidget)
    """
    def __init__(self, packet_sender: Callable, spi_commands: dict, parent=None):
        super().__init__(parent)
        self.packet_sender = packet_sender # 预期是 SPIWidget.send_spi_data
        self.spi_commands = spi_commands  # 从主窗口加载的指令
        self.input_widgets = {} # 存储 QLineEdit, QTextEdit 等
        self.setWindowTitle("SPI Flash 指令工具")
        self.setMinimumSize(500, 400)
        self.setup_ui()

    def setup_ui(self):
        """动态创建UI元素。"""
        main_layout = QVBoxLayout(self)

        # 指令发送区
        command_group = QGroupBox("发送指令 (使用当前SPI配置)")
        form_layout = QFormLayout()

        # 根据 spi_commands 字典动态创建界面
        for name, info in self.spi_commands.items():
            cmd_byte_str = info['cmd']
            params = info.get('params', []) # 获取参数列表，默认为空

            # 需要额外输入的指令 (地址、数据、长度)
            if name in ["页编程", "读数据", "块擦除(64KB)", "扇区擦除(4KB)"]:
                row_layout = QHBoxLayout() # 水平布局放输入框和按钮
                # 地址输入框
                if any("A" in p for p in params): # 如果参数中包含地址
                    addr_edit = QLineEdit()
                    addr_edit.setPlaceholderText("地址 (例如: 01A0FF)")
                    addr_edit.setValidator(QRegExpValidator(QRegExp("[0-9A-Fa-f]{0,6}"))) # 验证器
                    self.input_widgets[f"{name}_addr"] = addr_edit
                    row_layout.addWidget(QLabel("地址:"))
                    row_layout.addWidget(addr_edit)

                # 数据输入框 (仅页编程)
                if "Data" in params:
                    data_edit = QLineEdit()
                    data_edit.setPlaceholderText("数据 (HEX, e.g., AABBCCDD)")
                    data_edit.setValidator(QRegExpValidator(QRegExp("[0-9A-Fa-f ]*"))) # 允许空格
                    self.input_widgets[f"{name}_data"] = data_edit
                    row_layout.addWidget(QLabel("数据:"))
                    row_layout.addWidget(data_edit)

                # 长度输入框 (仅读数据)
                if name == "读数据":
                    len_edit = QLineEdit("16") # 默认读16字节
                    len_edit.setValidator(QIntValidator(1, 4096)) # 限制范围
                    self.input_widgets[f"{name}_len"] = len_edit
                    row_layout.addWidget(QLabel("长度(字节):"))
                    row_layout.addWidget(len_edit)

                send_btn = QPushButton(f"发送 {name}")
                # 使用 lambda 捕获循环变量 name 和 cmd_byte_str
                send_btn.clicked.connect(lambda _, n=name, c=cmd_byte_str: self.send_command_by_name(n, c))
                row_layout.addWidget(send_btn)
                form_layout.addRow(row_layout) # 将整行添加到表单

            else:
                # 简单指令 (无额外输入)
                send_btn = QPushButton(f"发送 {name} ({cmd_byte_str}h)")
                send_btn.clicked.connect(lambda _, n=name, c=cmd_byte_str: self.send_command_by_name(n, c))
                form_layout.addRow(send_btn)

        command_group.setLayout(form_layout)
        main_layout.addWidget(command_group)

        # 响应显示区
        response_group = QGroupBox("响应 (来自 MISO)")
        response_layout = QVBoxLayout()
        self.response_display = QTextEdit()
        self.response_display.setReadOnly(True)
        self.response_display.setFont(QFont("Courier New", 9)) # 等宽字体
        self.response_display.append("在此处查看 SPI 响应...")
        response_layout.addWidget(self.response_display)
        response_group.setLayout(response_layout)
        main_layout.addWidget(response_group)

    def log_error(self, message):
        """在响应窗口和消息框中显示错误。"""
        self.response_display.append(f"❌ 错误: {message}")
        QMessageBox.warning(self, "错误", message)

    def send_command_by_name(self, name, cmd_byte_str):
        """根据指令名称构建并发送 SPI 数据包。"""
        try:
            cmd_byte = int(cmd_byte_str, 16)
            payload = bytearray([cmd_byte]) # 指令字节作为载荷的第一个字节
            info = self.spi_commands.get(name, {}) # 获取指令信息

            # --- 根据不同指令构建载荷 ---
            if name == "检测FLASH状态":
                payload.extend(bytes.fromhex("FF")) # 需要发送一个虚拟字节来接收状态

            elif name in ["块擦除(64KB)", "扇区擦除(4KB)"]:
                addr_widget = self.input_widgets.get(f"{name}_addr")
                if not addr_widget: return # 防御性编程
                addr_str = addr_widget.text().strip()
                if len(addr_str) != 6:
                    self.log_error(f"{name} 地址必须是 3 字节 (6 个 HEX 字符)")
                    return
                payload.extend(bytes.fromhex(addr_str)) # 添加3字节地址

            elif name == "页编程":
                addr_widget = self.input_widgets.get(f"{name}_addr")
                data_widget = self.input_widgets.get(f"{name}_data")
                if not addr_widget or not data_widget: return
                addr_str = addr_widget.text().strip()
                data_str = data_widget.text().strip().replace(" ", "") # 移除空格
                if len(addr_str) != 6:
                    self.log_error("页编程地址必须是 3 字节 (6 个 HEX 字符)")
                    return
                if not data_str or len(data_str) % 2 != 0:
                    self.log_error("页编程数据不能为空且必须是偶数个 HEX 字符")
                    return
                payload.extend(bytes.fromhex(addr_str)) # 添加3字节地址
                payload.extend(bytes.fromhex(data_str)) # 添加N字节数据

            elif name == "读数据":
                addr_widget = self.input_widgets.get(f"{name}_addr")
                len_widget = self.input_widgets.get(f"{name}_len")
                if not addr_widget or not len_widget: return
                addr_str = addr_widget.text().strip()
                len_str = len_widget.text().strip()
                if len(addr_str) != 6:
                    self.log_error("读数据地址必须是 3 字节 (6 个 HEX 字符)")
                    return
                try:
                    read_len = int(len_str)
                    if read_len <= 0: raise ValueError()
                except ValueError:
                    self.log_error("读取长度必须是正整数")
                    return
                payload.extend(bytes.fromhex(addr_str)) # 添加3字节地址
                payload.extend([0xFF] * read_len) # 添加N个虚拟字节以产生时钟

            # --- 发送构建好的数据包 ---
            self.send_spi_packet(bytes(payload))

        except ValueError as e:
            self.log_error(f"HEX 值无效或处理错误: {e}")
        except Exception as e:
            self.log_error(f"发送 {name} 时出错: {e}")

    def send_spi_packet(self, data_bytes: bytes):
        """调用父控件 (SPIWidget) 的发送方法。"""
        self.response_display.append(f"发送 ->: {data_bytes.hex(' ')}")
        # 调用 SPIWidget.send_spi_data
        if not self.packet_sender(data_bytes):
             self.response_display.append(f"❌ 发送失败 (通信未连接或失败)")

    def handle_response(self, payload: bytes):
        """处理从 SPIWidget 转发过来的响应数据。"""
        response_hex = payload.hex(' ')
        # 仅显示原始 HEX 数据
        self.response_display.append(f"收到 <-: {response_hex}")


# ================== 子控件: SPIWidget ==================
class SPIWidget(QWidget):
    """SPI 总线调试功能的界面控件。"""
    def __init__(self, packet_sender: Callable):
        super().__init__()
        self.packet_sender = packet_sender
        self.spi_command_data = {}      # 存储 SPI 指令定义
        self.spi_flash_tool_dialog = None # 存储 Flash 工具对话框实例
        self.load_spi_commands()        # 加载指令
        self.init_ui()

    def load_spi_commands(self):
        """硬编码加载 Flash 指令。"""
        try:
            self.spi_command_data = {
                "写使能": {"cmd": "06", "params": [], "resp": 0, "note": "不记录返回数据"},
                "禁止写": {"cmd": "04", "params": [], "resp": 0, "note": "不记录返回数据"},
                "检测FLASH状态": {"cmd": "05", "params": ["FFh"], "resp": 1, "note": "00：空闲；11：繁忙"},
                "页编程": {"cmd": "02", "params": ["A23-A16", "A15-A8", "A7-A0", "Data"], "resp": 0, "note": "不记录返回数据"},
                "读数据": {"cmd": "03", "params": ["A23-A16", "A15-A8", "A7-A0", "FFh"], "resp": "dynamic", "note": "取第六个字节..."},
                "块擦除(64KB)": {"cmd": "D8", "params": ["A23-A16", "A15-A8", "A7-A0"], "resp": 0, "note": "不记录返回数据"},
                "扇区擦除(4KB)": {"cmd": "20", "params": ["A23-A16", "A15-A8", "A7-A0"], "resp": 0, "note": "不记录返回数据"},
            }
        except Exception as e:
            print(f"加载 SPI 指令失败: {e}")

    def init_ui(self):
        """初始化SPI控件的用户界面。"""
        layout=QVBoxLayout(self)

        # SPI 配置组
        config_group=QGroupBox("SPI配置")
        config_layout=QGridLayout()
        config_layout.addWidget(QLabel("分频系数:"),0,0)
        self.clock_div_spin=QSpinBox()
        self.clock_div_spin.setRange(0,255) # 0-255 对应协议
        self.clock_div_spin.setValue(100) # 默认值
        config_layout.addWidget(self.clock_div_spin,0,1)
        config_layout.addWidget(QLabel("SPI模式:"),1,0)
        self.mode_combo=QComboBox()
        self.mode_combo.addItems(["模式0 (CPOL=0, CPHA=0)", "模式1 (CPOL=0, CPHA=1)", "模式2 (CPOL=1, CPHA=0)", "模式3 (CPOL=1, CPHA=1)"])
        config_layout.addWidget(self.mode_combo,1,1)
        config_btn=QPushButton("配置SPI")
        config_btn.clicked.connect(self.configure_spi)
        config_layout.addWidget(config_btn,2,0,1,2) # 按钮跨两列
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # SPI 传输组
        transfer_group=QGroupBox("SPI传输")
        transfer_layout=QVBoxLayout()
        # 手动发送区域
        send_layout=QHBoxLayout()
        send_layout.addWidget(QLabel("发送数据(HEX):"))
        self.send_data_edit=QLineEdit()
        self.send_data_edit.setPlaceholderText("例如: 01 02 03 FF")
        self.send_data_edit.setValidator(QRegExpValidator(QRegExp("[0-9A-Fa-f ]*"))) # 验证器
        send_layout.addWidget(self.send_data_edit)
        send_btn=QPushButton("发送")
        send_btn.clicked.connect(lambda: self.send_spi_data()) # 手动发送按钮调用
        send_layout.addWidget(send_btn)
        transfer_layout.addLayout(send_layout)

        # Flash 工具按钮
        self.spi_flash_tool_btn = QPushButton("SPI Flash 指令工具")
        self.spi_flash_tool_btn.clicked.connect(self.open_spi_flash_tool)
        transfer_layout.addWidget(self.spi_flash_tool_btn)

        # 接收数据显示区域
        transfer_layout.addWidget(QLabel("接收数据 (来自 MISO):"))
        self.receive_data_text=QTextEdit()
        self.receive_data_text.setReadOnly(True)
        transfer_layout.addWidget(self.receive_data_text)

        transfer_group.setLayout(transfer_layout)
        layout.addWidget(transfer_group)
        layout.addStretch()

    def configure_spi(self):
        """发送 SPI 配置命令 (B0)。"""
        spi_mode = self.mode_combo.currentIndex() # 0, 1, 2, 3
        spi_period = self.clock_div_spin.value()  # 0-255
        # 协议载荷：16位，[15:8] 模式, [7:0] 分频系数
        config_word = (spi_mode << 8) | spi_period
        payload = struct.pack('!H', config_word) # 大端序 unsigned short
        self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_SPI_CONFIG, payload))
        # 可以在这里加一个 QMessageBox 显示发送成功

    def send_spi_data(self, data_to_send: bytes = None) -> bool:
        """
        发送 SPI 传输命令 (B1)。
        可由手动发送按钮调用 (data_to_send=None)，或由 Flash 工具调用 (传入 data_to_send)。
        返回发送操作是否成功尝试。
        """
        payload = b''
        try:
            if data_to_send is not None:
                payload = data_to_send # 来自 Flash 工具
            else:
                # 来自手动输入框
                hex_str = self.send_data_edit.text().strip().replace(' ', '')
                if not hex_str:
                     QMessageBox.warning(self, "错误", "发送数据不能为空。")
                     return False
                if len(hex_str) % 2 != 0: # 奇数长度补0
                    hex_str = '0' + hex_str
                payload = bytes.fromhex(hex_str)
        except ValueError:
            QMessageBox.warning(self, "错误", "无效的十六进制数据格式。")
            return False

        # 调用 FPGADebuggerWidget 的 send_packet 方法
        return self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_SPI_TRANSFER, payload))

    def open_spi_flash_tool(self):
        """打开或激活 SPI Flash 指令工具对话框。"""
        if not self.spi_command_data:
            self.load_spi_commands() # 尝试重新加载
            if not self.spi_command_data:
                QMessageBox.warning(self, "错误", "加载 SPI 指令失败，无法打开工具")
                return

        # 如果对话框未创建或已被关闭，则重新创建
        if not self.spi_flash_tool_dialog or not self.spi_flash_tool_dialog.isVisible():
            self.spi_flash_tool_dialog = SpiFlashToolDialog(
                self.send_spi_data,  # 将 send_spi_data 传递给对话框
                self.spi_command_data,
                parent=self # 父窗口设为 SPIWidget
            )
            # 可选：连接对话框关闭信号，清理引用 (如果需要)
            # self.spi_flash_tool_dialog.finished.connect(lambda: setattr(self, 'spi_flash_tool_dialog', None))
        apply_modern_theme(self.spi_flash_tool_dialog, theme="light")
        self.spi_flash_tool_dialog.show()
        self.spi_flash_tool_dialog.activateWindow()
        self.spi_flash_tool_dialog.raise_() # 确保在顶层

    def append_received_data(self, display_string: str, raw_data: bytes):
        """将收到的数据追加到文本框，并转发给 Flash 工具（如果打开）。"""
        self.receive_data_text.append(display_string)
        self.receive_data_text.ensureCursorVisible()

        # 如果 Flash 工具对话框存在且可见，则调用其 handle_response 方法
        if self.spi_flash_tool_dialog and self.spi_flash_tool_dialog.isVisible():
            self.spi_flash_tool_dialog.handle_response(raw_data)


# ================== 子控件: I2CWidget ==================
class I2CWidget(QWidget):
    """I2C 总线调试功能的界面控件，并提供打开 OLED 控制面板的入口。"""
    open_oled_panel_requested = pyqtSignal() # 用于请求打开 OLED 面板的信号
    def __init__(self, packet_sender: Callable):
        super().__init__()
        self.packet_sender=packet_sender
        self.speed_mode_map = { "标准模式 (100 kbps)": 0, "快速模式 (400 kbps)": 1, "高速模式 (3.4 Mbps)": 2, "超快速模式 (5 Mbps)": 3 }
        self.init_ui()
    def init_ui(self):
        """初始化I2C控件的用户界面。"""
        layout=QVBoxLayout(self)

        # I2C 配置组
        config_group=QGroupBox("I2C配置")
        config_layout=QGridLayout()
        config_layout.addWidget(QLabel("SCL时钟速率模式:"),0,0)
        self.speed_mode_combo = QComboBox()
        self.speed_mode_combo.addItems(self.speed_mode_map.keys())
        config_layout.addWidget(self.speed_mode_combo,0,1)
        config_btn=QPushButton("配置I2C")
        config_btn.clicked.connect(self.configure_i2c)
        config_layout.addWidget(config_btn,0,2) # 按钮放在右侧
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # I2C 传输组
        transfer_group=QGroupBox("I2C传输")
        transfer_layout=QGridLayout()
        transfer_layout.addWidget(QLabel("从机地址 (7-bit):"),0,0)
        self.slave_addr_spin=QSpinBox()
        self.slave_addr_spin.setRange(0,127) # 7位地址范围
        self.slave_addr_spin.setDisplayIntegerBase(16) # 显示为十六进制
        self.slave_addr_spin.setPrefix("0x") # 添加前缀
        transfer_layout.addWidget(self.slave_addr_spin,0,1)
        transfer_layout.addWidget(QLabel("写入数据 (HEX):"),1,0)
        self.write_data_edit=QLineEdit()
        self.write_data_edit.setPlaceholderText("例如: AA BB")
        self.write_data_edit.setValidator(QRegExpValidator(QRegExp("[0-9A-Fa-f ]*"))) # 验证器
        transfer_layout.addWidget(self.write_data_edit,1,1)
        write_btn=QPushButton("写入")
        write_btn.clicked.connect(self.write_i2c_data)
        transfer_layout.addWidget(write_btn,1,2) # 写入按钮
        transfer_layout.addWidget(QLabel("读取字节数:"),2,0)
        self.read_count_spin=QSpinBox()
        self.read_count_spin.setRange(1,255) # 协议限制？
        self.read_count_spin.setValue(4) # 默认读取4字节
        transfer_layout.addWidget(self.read_count_spin,2,1)
        read_btn=QPushButton("读取")
        read_btn.clicked.connect(self.read_i2c_data)
        transfer_layout.addWidget(read_btn,2,2) # 读取按钮
        transfer_group.setLayout(transfer_layout)
        layout.addWidget(transfer_group)

        # OLED 控制组
        oled_group = QGroupBox("OLED 控制")
        oled_layout = QHBoxLayout()
        self.oled_button = QPushButton("打开 OLED 控制面板")
        self.oled_button.clicked.connect(self.open_oled_panel_requested.emit) # 发射信号
        oled_layout.addWidget(self.oled_button)
        oled_layout.addStretch()
        oled_group.setLayout(oled_layout)
        layout.addWidget(oled_group)

        # I2C 接收数据组
        receive_group = QGroupBox("接收数据")
        receive_layout = QVBoxLayout()
        self.receive_data_text=QTextEdit()
        self.receive_data_text.setReadOnly(True)
        receive_layout.addWidget(self.receive_data_text)
        receive_group.setLayout(receive_layout)
        layout.addWidget(receive_group)

        layout.addStretch()
    def configure_i2c(self):
        """发送 I2C 配置命令 (A2)。"""
        selected_mode_text = self.speed_mode_combo.currentText()
        mode_val = self.speed_mode_map.get(selected_mode_text, 0)
        # 协议载荷：1字节，低2位有效
        payload = struct.pack('!B', mode_val & 0b11)
        if self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_I2C_CONFIG, payload)):
             QMessageBox.information(self, "成功", f"I2C速率模式配置({selected_mode_text})命令(A2)已发送。")
        # else: 发送失败由 packet_sender 处理
    def write_i2c_data(self):
        """发送 I2C 传输命令 (A3) - 写入数据。"""
        try:
            slave_addr = self.slave_addr_spin.value()
            # 协议要求载荷第一个字节是 地址 + R/W位 (0为写)
            address_byte = (slave_addr << 1) | 0x00
            # 获取写入数据
            hex_str = self.write_data_edit.text().strip().replace(' ', '')
            if not hex_str:
                QMessageBox.warning(self,"提示","写入数据不能为空。")
                return
            if len(hex_str) % 2 != 0: hex_str = '0' + hex_str # 补齐
            data_to_write = bytes.fromhex(hex_str)
            data_len = len(data_to_write)
            # 载荷第二个字节是数据长度
            header = struct.pack('!BB', address_byte, data_len)
            payload = header + data_to_write # 组合完整载荷
            # 发送包
            self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_I2C_TRANSFER, payload))
            # 可以在这里加一个发送成功的提示
        except ValueError:
             QMessageBox.warning(self,"错误","无效的十六进制数据格式")
        except Exception as e:
             QMessageBox.critical(self,"错误", f"发送 I2C 写入命令时出错: {e}")
    def read_i2c_data(self):
        """发送 I2C 传输命令 (A3) - 读取数据。"""
        try:
            slave_addr = self.slave_addr_spin.value()
            # 协议要求载荷第一个字节是 地址 + R/W位 (1为读)
            address_byte = (slave_addr << 1) | 0x01
            read_len = self.read_count_spin.value()
            # 载荷第二个字节是读取长度
            payload = struct.pack('!BB', address_byte, read_len)
            # 发送包
            self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_I2C_TRANSFER, payload))
            # 可以在这里加一个发送成功的提示
        except Exception as e:
             QMessageBox.critical(self,"错误", f"发送 I2C 读取命令时出错: {e}")


# ================== 子控件: GY25Widget ==================
# (!!! 此处包含关键修改 !!!)
class GY25Widget(QWidget):
    """GY-25 陀螺仪传感器专用控制窗口"""
    baud_rate_change_requested = pyqtSignal(str) # 请求主UART更改波特率的信号
    def __init__(self, packet_sender: Callable, parent=None):
        super().__init__(parent, Qt.Window) # 设置为独立窗口
        self.packet_sender = packet_sender
        self.setWindowTitle("GY-25 陀螺仪控制")
        self.setMinimumWidth(400)
        self.yaw = 0.0
        self.pitch = 0.0
        self.roll = 0.0
        self._receive_buffer = QByteArray() # 使用 QByteArray 作为缓冲区
        self.init_ui()

    def init_ui(self):
        """初始化GY25控件的用户界面。"""
        main_layout = QVBoxLayout(self)

        # 波特率设置
        baud_group = QGroupBox("波特率设置")
        baud_layout = QHBoxLayout()
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["115200", "9600"]) # GY25常用波特率
        baud_layout.addWidget(QLabel("选择波特率:"))
        baud_layout.addWidget(self.baud_combo)
        apply_baud_btn = QPushButton("应用波特率到主 UART")
        apply_baud_btn.clicked.connect(self._request_baud_change)
        baud_layout.addWidget(apply_baud_btn)
        baud_group.setLayout(baud_layout)
        main_layout.addWidget(baud_group)

        # 模式控制
        mode_group = QGroupBox("模式控制 (发送命令到 GY-25)")
        mode_layout = QGridLayout()
        query_btn = QPushButton("查询模式 (A5 51)"); query_btn.clicked.connect(lambda: self.send_gy25_command(b'\xA5\x51'))
        auto_hex_btn = QPushButton("自动模式 HEX (A5 52)"); auto_hex_btn.clicked.connect(lambda: self.send_gy25_command(b'\xA5\x52'))
        auto_ascii_btn = QPushButton("自动模式 ASCII (A5 53)"); auto_ascii_btn.clicked.connect(lambda: self.send_gy25_command(b'\xA5\x53'))
        mode_layout.addWidget(query_btn, 0, 0)
        mode_layout.addWidget(auto_hex_btn, 0, 1)
        mode_layout.addWidget(auto_ascii_btn, 1, 0, 1, 2) # 跨两列
        mode_group.setLayout(mode_layout)
        main_layout.addWidget(mode_group)

        # 校准控制
        calib_group = QGroupBox("校准控制 (发送命令到 GY-25)")
        calib_layout = QHBoxLayout()
        calib_pr_btn = QPushButton("校准俯仰/横滚零度 (A5 54)"); calib_pr_btn.clicked.connect(lambda: self.send_gy25_command(b'\xA5\x54'))
        calib_yaw_btn = QPushButton("校准航向零度 (A5 55)"); calib_yaw_btn.clicked.connect(lambda: self.send_gy25_command(b'\xA5\x55'))
        calib_layout.addWidget(calib_pr_btn)
        calib_layout.addWidget(calib_yaw_btn)
        calib_group.setLayout(calib_layout)
        main_layout.addWidget(calib_group)

        # 数据显示
        display_group = QGroupBox("实时角度数据")
        display_layout = QFormLayout()
        self.yaw_label = QLabel("-.-- °")
        self.pitch_label = QLabel("-.-- °")
        self.roll_label = QLabel("-.-- °")
        font = QFont(); font.setPointSize(14); font.setBold(True) # 设置字体
        for label in [self.yaw_label, self.pitch_label, self.roll_label]: label.setFont(font)
        display_layout.addRow("航向角 (Yaw):", self.yaw_label)
        display_layout.addRow("俯仰角 (Pitch):", self.pitch_label)
        display_layout.addRow("横滚角 (Roll):", self.roll_label)
        display_group.setLayout(display_layout)
        main_layout.addWidget(display_group)

        main_layout.addStretch()

    def _request_baud_change(self):
        """当用户点击应用波特率按钮时，发射信号通知主UART控件更改配置。"""
        selected_baud = self.baud_combo.currentText()
        self.baud_rate_change_requested.emit(selected_baud)
        QMessageBox.information(self, "请求发送", f"已请求将主 UART 波特率更改为 {selected_baud} bps。请确保 GY-25 模块也设置为此波特率。")

    def send_gy25_command(self, command: bytes):
        """通过主 UART 发送命令给 GY-25。"""
        # 使用 UART 传输命令 (A1)
        self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_UART_TRANSFER, command))
        # 可以在这里加一个发送成功的提示

    # [!!! 最终修复 - 已移除调试日志 !!!]
    def handle_uart_data(self, data: bytes):
        """处理从 UARTWidget 转发过来的原始字节数据，解析 GY-25 帧。"""
        self._receive_buffer.append(data) # 追加数据到缓冲区

        # 循环处理缓冲区中的数据，直到不足一个完整帧
        while self._receive_buffer.size() >= 8:
            # 查找帧头 0xAA
            start_index = self._receive_buffer.indexOf(b'\xAA', 0)

            # 如果没找到帧头，清空缓冲区并返回
            if start_index == -1:
                self._receive_buffer.clear()
                return

            # 如果帧头不在开头，丢弃之前的数据
            if start_index > 0:
                self._receive_buffer = self._receive_buffer.mid(start_index)

            # 检查剩余数据是否足够一个完整帧
            if self._receive_buffer.size() < 8:
                return # 等待更多数据

            # --- 修复 1：使用 ord(self._receive_buffer.at(7)) 获取帧尾整数值 ---
            try:
                frame_end_byte_int = ord(self._receive_buffer.at(7))
            except (IndexError, TypeError) as e:
                 # 捕获可能的错误，防止程序崩溃
                 print(f"[GY25 错误] 获取帧尾字节时出错: {e}, 缓冲区: {self._receive_buffer.data().hex()}")
                 self._receive_buffer = self._receive_buffer.mid(1) # 丢弃一个字节尝试恢复
                 continue # 继续下一次循环

            # 检查帧尾是否为 0x55
            if frame_end_byte_int == 0x55:
                # 提取完整帧 (8字节)
                frame = self._receive_buffer.mid(0, 8)
                # 从缓冲区移除已处理的帧
                self._receive_buffer = self._receive_buffer.mid(8)
                try:
                    # --- 修复 2：将 QByteArray 转换为 bytes 再解包 ---
                    yaw_bytes = bytes(frame.mid(1, 2))
                    pitch_bytes = bytes(frame.mid(3, 2))
                    roll_bytes = bytes(frame.mid(5, 2))

                    # 解包大端序 short int ('>h')
                    yaw_raw = struct.unpack('>h', yaw_bytes)[0]
                    pitch_raw = struct.unpack('>h', pitch_bytes)[0]
                    roll_raw = struct.unpack('>h', roll_bytes)[0]

                    # 计算角度值
                    self.yaw = yaw_raw / 100.0
                    self.pitch = pitch_raw / 100.0
                    self.roll = roll_raw / 100.0

                    # 更新UI标签
                    self.yaw_label.setText(f"{self.yaw:.2f} °")
                    self.pitch_label.setText(f"{self.pitch:.2f} °")
                    self.roll_label.setText(f"{self.roll:.2f} °")

                except struct.error as e:
                    print(f"GY-25 数据帧解析错误: {e}") # 打印解包错误
                except Exception as e:
                    print(f"处理 GY-25 数据时发生未知错误: {e}") # 打印其他错误
            else:
                # 帧尾不匹配，丢弃缓冲区第一个字节，继续寻找下一帧
                self._receive_buffer = self._receive_buffer.mid(1)

    def closeEvent(self, event):
        """重写关闭事件，使其隐藏而不是销毁，以便下次可以重新打开。"""
        self.hide()
        event.ignore() # 忽略默认的关闭操作


# ================== 子控件: UARTWidget ==================
class UARTWidget(QWidget):
    """UART 调试功能的界面控件。"""
    data_received_for_gy25 = pyqtSignal(bytes) # 将接收到的原始数据转发给 GY25Widget
    gy25_baud_request_signal = pyqtSignal(str) # GY25Widget 请求更改波特率的信号 (未使用?)

    def __init__(self, packet_sender: Callable):
        super().__init__()
        self.packet_sender = packet_sender
        self.init_ui()
        self.gy25_widget = None # 初始化 GY25 控件引用为 None

    def set_gy25_widget(self, widget: GY25Widget):
        """由 FPGADebuggerWidget 调用，设置 GY25 控件实例并连接信号。"""
        self.gy25_widget = widget
        if self.gy25_widget:
            # 连接 GY25 请求波特率改变的信号 到 UART 的处理槽
            self.gy25_widget.baud_rate_change_requested.connect(self.handle_gy25_baud_request)
            # 连接 UART 接收到数据 的信号 到 GY25 的处理槽
            self.data_received_for_gy25.connect(self.gy25_widget.handle_uart_data)

    def init_ui(self):
        """初始化UART控件的用户界面。"""
        layout = QVBoxLayout(self)

        # UART 配置组
        config_group = QGroupBox("UART配置")
        config_layout = QGridLayout()
        config_layout.addWidget(QLabel("波特率:"), 0, 0)
        self.baud_rate_combo = QComboBox()
        self.baud_rate_combo.addItems(["9600", "19200", "38400", "57600", "115200", "921600", "1000000"])
        self.baud_rate_combo.setCurrentText("115200") # 默认波特率
        config_layout.addWidget(self.baud_rate_combo, 0, 1)

        # === [修改点 1: 停止位选项] ===
        config_layout.addWidget(QLabel("停止位:"), 2, 0)
        self.stop_bits_combo = QComboBox()
        # 按照图片 [19:18] 的 2 位 4 种选项 (0=0.5, 1=1, 2=1.5, 3=2)
        self.stop_bits_combo.addItems(["0.5", "1", "1.5", "2"]) 
        self.stop_bits_combo.setCurrentText("1") # 默认 1
        config_layout.addWidget(self.stop_bits_combo, 2, 1)
        # === [修改结束] ===

        config_layout.addWidget(QLabel("校验位:"), 3, 0)
        self.parity_combo = QComboBox(); self.parity_combo.addItems(["无", "奇校验", "偶校验"])
        config_layout.addWidget(self.parity_combo, 3, 1)

        # === [修改点 2: 增加 MOL (大小端) 选项] ===
        config_layout.addWidget(QLabel("大小端:"), 4, 0)
        self.mol_combo = QComboBox()
        # 假设 0=MSB first, 1=LSB first (根据图片 "1: 先发低位")
        self.mol_combo.addItems(["MSB First (先发高位)", "LSB First (先发低位)"])
        self.mol_combo.setCurrentIndex(1) # 默认 LSB First
        config_layout.addWidget(self.mol_combo, 4, 1)
        # === [修改结束] ===

        config_btn = QPushButton("配置UART")
        config_btn.clicked.connect(self.configure_uart)
        config_layout.addWidget(config_btn, 5, 0, 1, 2) # 调整行索引

        # GY-25 控制按钮
        self.gy25_button = QPushButton("GY-25 陀螺仪控制")
        self.gy25_button.clicked.connect(self.show_gy25_panel) # 点击时显示GY25面板
        config_layout.addWidget(self.gy25_button, 6, 0, 1, 2) # 调整行索引

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # ... (UART 传输组 UI 保持不变) ...
        transfer_group = QGroupBox("UART传输")
        transfer_layout = QVBoxLayout()
        # 发送格式选择
        send_format_layout = QHBoxLayout()
        send_format_layout.addWidget(QLabel("发送格式:"))
        self.ascii_radio = QRadioButton("ASCII"); self.ascii_radio.setChecked(True) # 默认ASCII
        self.hex_radio = QRadioButton("HEX")
        send_format_layout.addWidget(self.ascii_radio); send_format_layout.addWidget(self.hex_radio)
        send_format_layout.addStretch()
        transfer_layout.addLayout(send_format_layout)
        # 发送数据区域
        send_layout = QHBoxLayout()
        send_layout.addWidget(QLabel("发送数据:"))
        self.send_data_edit = QLineEdit()
        self.send_data_edit.setValidator(QRegExpValidator(QRegExp("[0-9A-Fa-f ]*"))) # 限制HEX输入
        send_layout.addWidget(self.send_data_edit)
        send_btn = QPushButton("发送")
        send_btn.clicked.connect(self.send_uart_data)
        send_layout.addWidget(send_btn)
        transfer_layout.addLayout(send_layout)
        # 接收数据显示区域
        transfer_layout.addWidget(QLabel("接收数据:"))
        self.receive_data_text = QTextEdit(); self.receive_data_text.setReadOnly(True)
        transfer_layout.addWidget(self.receive_data_text)
        transfer_group.setLayout(transfer_layout)
        layout.addWidget(transfer_group)

        layout.addStretch()

    def configure_uart(self):
        """发送 UART 配置命令 (A0)。(已按图片协议修改)"""
        FPGA_CLOCK = 50_000_000 # FPGA 主时钟频率
        try:
            baud_rate = int(self.baud_rate_combo.currentText())
        except ValueError:
             QMessageBox.warning(self, "错误", "无效的波特率值"); return

        # 1. 波特率 [15:0] (来自图片)
        baud_divisor = round(FPGA_CLOCK / baud_rate)
        if not (0 <= baud_divisor <= 65535): # 检查是否在16位范围内
             QMessageBox.warning(self, "错误", f"波特率 {baud_rate} 计算得分频值 {baud_divisor} 超出范围 (0-65535)"); return

        # 2. 校验位 [17:16] (来自图片)
        # UI: ["无", "奇校验", "偶校验"] (索引 0, 1, 2)
        # 协议: 0: 无, 1: 奇, 2: 偶
        parity_val = self.parity_combo.currentIndex() & 0b11

        # 3. 停止位 [19:18] (来自图片)
        # UI: ["0.5", "1", "1.5", "2"] (索引 0, 1, 2, 3)
        # 协议: 0: 0.5, 1: 1, 2: 1.5, 3: 2 (推断)
        stop_bits_val = self.stop_bits_combo.currentIndex() & 0b11
        
        # 4. MOL [20] (来自图片)
        # UI: ["MSB First (先发高位)", "LSB First (先发低位)"] (索引 0, 1)
        # 协议: 1: 先发低位 (LSB first)
        mol_val = self.mol_combo.currentIndex() & 0b1

        # --- 构建 21 位配置值 ---
        config_value = 0
        config_value |= (baud_divisor & 0xFFFF)   # [15:0]
        config_value |= (parity_val << 16)        # [17:16]
        config_value |= (stop_bits_val << 18)     # [19:18]
        config_value |= (mol_val << 20)           # [20]

        # --- 打包 ---
        # 21 位数据需要 3 个字节 (24位)。
        # 使用大端序打包为 4 字节整数 ('>I')，然后取后 3 个字节 ([-3:])
        try:
            payload = struct.pack('>I', config_value)[-3:]
        except struct.error as e:
            QMessageBox.critical(self, "打包错误", f"构建 UART 配置包失败: {e}")
            return
            
        # 发送包 (A0)
        self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_UART_CONFIG, payload))
        # 可以在这里加一个发送成功的提示
        QMessageBox.information(self, "发送成功", "UART 配置命令已成功发送。")

    def send_uart_data(self):
        """发送 UART 数据传输命令 (A1)。"""
        text_to_send = self.send_data_edit.text()
        data_to_send = b''
        if self.ascii_radio.isChecked():
            # ASCII 模式，直接编码
            data_to_send = text_to_send.encode('utf-8', errors='replace') # 替换无法编码的字符
        else:
            # HEX 模式，转换十六进制字符串
            try:
                 hex_str = text_to_send.strip().replace(' ', '').replace(',', '')
                 if len(hex_str) % 2 != 0: hex_str = '0' + hex_str # 补齐
                 data_to_send = bytes.fromhex(hex_str)
            except ValueError:
                 QMessageBox.warning(self, "格式错误", "无效的十六进制数据格式。\n请输入如 'AA BB 01 02' 的字符串。"); return
        # 发送包
        self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_UART_TRANSFER, data_to_send))
        # 可以在这里加一个发送成功的提示

    def show_gy25_panel(self):
        """显示 GY-25 控制面板。"""
        if self.gy25_widget:
            self.gy25_widget.show()
            self.gy25_widget.activateWindow()
            self.gy25_widget.raise_()
        else:
             QMessageBox.warning(self, "错误", "GY-25 面板未初始化。")

    def handle_gy25_baud_request(self, baud_rate: str):
        """处理来自 GY-25 面板的波特率更改请求。"""
        index = self.baud_rate_combo.findText(baud_rate) # 查找请求的波特率
        if index != -1:
            # 如果找到，设置下拉框并重新发送 UART 配置
            self.baud_rate_combo.setCurrentIndex(index)
            self.configure_uart()
            QMessageBox.information(self, "UART 配置更新", f"已尝试将 UART 波特率配置为 {baud_rate} bps。")
        else:
             QMessageBox.warning(self, "错误", f"不支持的波特率: {baud_rate}")

    def append_received_data(self, display_string: str, raw_data: bytes):
        """将收到的数据追加到文本框，并转发给 GY-25 控件（如果存在）。"""
        self.receive_data_text.append(display_string)
        self.receive_data_text.ensureCursorVisible()
        # 如果 GY25 控件已设置，则发射信号将原始数据传递给它
        if self.gy25_widget:
            self.data_received_for_gy25.emit(raw_data)


# ================== 子控件: PWMWidget ==================
class PWMWidget(QWidget):
    """PWM 输出功能的界面控件。"""
    def __init__(self, packet_sender: Callable):
        super().__init__()
        self.packet_sender = packet_sender
        self.init_ui()
    def init_ui(self):
        """初始化PWM控件的用户界面。"""
        main_layout = QVBoxLayout(self)

        # 参数配置组
        params_group = QGroupBox("参数配置")
        grid_layout = QGridLayout()
        # 表头标签
        grid_layout.addWidget(QLabel(""), 0, 0) # 空白占位
        grid_layout.addWidget(QLabel("周期 (Period)"), 0, 1)
        grid_layout.addWidget(QLabel("占空比 (Duty)"), 0, 2)

        uint32_validator = QRegExpValidator(QRegExp("[0-9]{1,10}")) # 验证器

        # 通道 1 输入框
        grid_layout.addWidget(QLabel("通道 1:"), 1, 0)
        self.period1_edit = QLineEdit("0"); self.period1_edit.setValidator(uint32_validator)
        self.duty1_edit = QLineEdit("0"); self.duty1_edit.setValidator(uint32_validator)
        grid_layout.addWidget(self.period1_edit, 1, 1); grid_layout.addWidget(self.duty1_edit, 1, 2)

        # 通道 2 输入框
        grid_layout.addWidget(QLabel("通道 2:"), 2, 0)
        self.period2_edit = QLineEdit("0"); self.period2_edit.setValidator(uint32_validator)
        self.duty2_edit = QLineEdit("0"); self.duty2_edit.setValidator(uint32_validator)
        grid_layout.addWidget(self.period2_edit, 2, 1); grid_layout.addWidget(self.duty2_edit, 2, 2)

        params_group.setLayout(grid_layout)
        apply_params_btn = QPushButton("应用参数") # 应用参数按钮放在组外
        apply_params_btn.clicked.connect(self.apply_parameters)

        # 输出使能组
        enable_group = QGroupBox("输出使能")
        enable_layout = QHBoxLayout()
        self.enable1_check = QCheckBox("使能通道 1")
        self.enable2_check = QCheckBox("使能通道 2")
        apply_enable_btn = QPushButton("应用使能")
        apply_enable_btn.clicked.connect(self.apply_enable)
        enable_layout.addWidget(self.enable1_check); enable_layout.addWidget(self.enable2_check)
        enable_layout.addStretch(); enable_layout.addWidget(apply_enable_btn) # 按钮靠右
        enable_group.setLayout(enable_layout)

        main_layout.addWidget(params_group)
        main_layout.addWidget(apply_params_btn) # 添加应用参数按钮
        main_layout.addWidget(enable_group)
        main_layout.addStretch()

    def apply_parameters(self):
        """发送 PWM 参数配置命令 (C0)。"""
        try:
            # 获取输入值，如果为空则默认为 "0"
            p1_str = self.period1_edit.text() or "0"; d1_str = self.duty1_edit.text() or "0"
            p2_str = self.period2_edit.text() or "0"; d2_str = self.duty2_edit.text() or "0"
            # 转换为整数
            p1 = int(p1_str); d1 = int(d1_str); p2 = int(p2_str); d2 = int(d2_str)
            unsigned_32_max = 4294967295 # 2^32 - 1

            # 验证数值范围
            if not all(0 <= val <= unsigned_32_max for val in [p1, d1, p2, d2]):
                raise ValueError("值超出无符号32位整数范围 (0-4294967295)")
            # 验证占空比是否小于等于周期
            if p1 > 0 and d1 > p1:
                raise ValueError("通道1占空比不能大于周期")
            if p2 > 0 and d2 > p2:
                raise ValueError("通道2占空比不能大于周期")

            # 构建载荷 (4个 unsigned int, 大端序)
            payload = struct.pack('!IIII', p1, d1, p2, d2)
            # 发送包
            if self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_PWM_CONFIG, payload)):
                 QMessageBox.information(self, "成功", "PWM参数配置(C0)已发送。")
            # else: 发送失败由 packet_sender 处理
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", f"周期和占空比必须是有效的无符号32位整数。\n{e}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"应用PWM参数时出错: {e}")

    def apply_enable(self):
        """发送 PWM 使能命令 (C1)。"""
        val = 0
        if self.enable1_check.isChecked(): val |= (1 << 0) # bit 0 控制通道 1
        if self.enable2_check.isChecked(): val |= (1 << 1) # bit 1 控制通道 2
        # 协议载荷：1字节
        payload = struct.pack('!B', val)
        # 发送包
        if self.packet_sender(_PacketBuilder.build_packet(PacketType.DEBUG_PWM_ENABLE, payload)):
             QMessageBox.information(self, "成功", "PWM使能命令(C1)已发送。")
        # else: 发送失败由 packet_sender 处理


# ================== 主控件: FPGADebuggerWidget ==================
class FPGADebuggerWidget(QWidget):
    """FPGA调试器主控件，包含 SPI, I2C, UART, PWM, CAN, DO自定义 等功能页。"""
    log_message = pyqtSignal(str) # 用于向主窗口发送日志的信号

    def __init__(self, comm_manager: CommunicationManager = None, parent=None):
        super().__init__(parent)
        self.comm_manager = comm_manager # 通信管理器实例
        self.oled_panel: OLEDWidget = None # OLED 控制面板实例
        self.gy25_panel: GY25Widget = None # GY25 控制面板实例
        self.init_ui() # 初始化主 UI

        # --- 在 init_ui 之后实例化独立窗口，防止初始化顺序问题 ---
        # OLED 面板
        self.oled_panel = OLEDWidget(self.send_packet, parent=self.window()) # 父窗口设为主窗口
        apply_modern_theme(self.oled_panel, theme="light")
        self.oled_panel.hide() # 初始隐藏

        # GY25 面板
        self.gy25_panel = GY25Widget(self.send_packet, parent=self.window())
        apply_modern_theme(self.gy25_panel, theme="light")
        self.gy25_panel.hide()
        # <------------------------->

        # --- 连接子控件信号 ---
        # 连接 I2CWidget 请求打开 OLED 面板的信号
        if hasattr(self.i2c_widget, 'open_oled_panel_requested'):
            self.i2c_widget.open_oled_panel_requested.connect(self.show_oled_panel)

        # 将 GY25 实例传递给 UARTWidget，以便 UARTWidget 可以连接 GY25 的信号
        if hasattr(self.uart_widget, 'set_gy25_widget'):
            self.uart_widget.set_gy25_widget(self.gy25_panel)

    def set_communication_manager(self, manager: CommunicationManager):
        """由 MainWindow 调用，设置或更新通信管理器实例。"""
        self.comm_manager = manager
        # 可能需要将新的 manager 传递给独立的窗口（如果它们需要直接通信）
        # if self.oled_panel: self.oled_panel.set_communication_manager(manager) # OLEDWidget 不需要
        # if self.gy25_panel: self.gy25_panel.set_communication_manager(manager) # GY25Widget 不需要

    def init_ui(self):
        """初始化 FPGADebuggerWidget 的用户界面。"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10) # 设置边距
        self.tab_widget = QTabWidget() # 创建标签页控件

        # --- 创建并添加各个功能标签页 ---
        # 每个子控件在初始化时接收 self.send_packet 作为发送函数
        self.spi_widget = SPIWidget(self.send_packet)
        self.tab_widget.addTab(self.spi_widget, "SPI")

        self.i2c_widget = I2CWidget(self.send_packet)
        self.tab_widget.addTab(self.i2c_widget, "I2C")

        self.uart_widget = UARTWidget(self.send_packet)
        self.tab_widget.addTab(self.uart_widget, "UART")

        self.pwm_widget = PWMWidget(self.send_packet)
        self.tab_widget.addTab(self.pwm_widget, "PWM")

        self.can_widget = CANWidget(self.send_packet)
        self.tab_widget.addTab(self.can_widget, "CAN")

        self.custom_do_widget = CustomDOWidget(self.send_packet)
        self.tab_widget.addTab(self.custom_do_widget, "DO自定义")

        main_layout.addWidget(self.tab_widget) # 将标签页控件添加到主布局

        # --- 接收数据显示格式选项 ---
        display_options_group = QGroupBox("接收数据显示设置")
        display_options_layout = QHBoxLayout()
        display_options_layout.addWidget(QLabel("格式:"))
        self.hex_radio = QRadioButton("HEX"); self.hex_radio.setChecked(True) # 默认 HEX
        display_options_layout.addWidget(self.hex_radio)
        self.ascii_radio = QRadioButton("ASCII")
        display_options_layout.addWidget(self.ascii_radio)
        display_options_layout.addStretch() # 选项靠左
        display_options_group.setLayout(display_options_layout)
        main_layout.addWidget(display_options_group)

    def send_packet(self, packet_data: bytes) -> bool:
        """
        统一的数据包发送函数，供所有子控件调用。
        通过 self.comm_manager 发送数据。
        返回 True 表示尝试发送成功，False 表示失败。
        """
        if self.comm_manager and self.comm_manager.is_running():
            if self.comm_manager.send_packet(packet_data):
                return True # 发送成功
            else:
                # comm_manager 内部应该已经记录了详细的发送失败日志
                QMessageBox.warning(self, "发送错误", "发送数据包失败，请检查日志。")
                return False
        else:
            QMessageBox.warning(self, "发送错误", "发送数据包失败，通信未连接。")
            return False

    def show_oled_panel(self):
        """显示 OLED 控制面板。"""
        if self.oled_panel:
            self.oled_panel.show()
            self.oled_panel.activateWindow() # 激活窗口
            self.oled_panel.raise_() # 提升到顶层
        else:
             QMessageBox.warning(self, "错误", "OLED 面板实例尚未创建。")

    def show_gy25_panel(self):
        """显示 GY-25 控制面板。"""
        if self.gy25_panel:
            self.gy25_panel.show()
            self.gy25_panel.activateWindow()
            self.gy25_panel.raise_()
        else:
             QMessageBox.warning(self, "错误", "GY-25 面板实例尚未创建。")


    def handle_data(self, packet_type, payload, source_id=None):
        """
        处理来自 CommunicationManager 的所有数据包，并将其分派到正确的子控件。
        根据 packet_type 判断目标控件，并调用其 append_received_data 方法。
        """
        # 获取来源描述字符串
        source_desc = f"{source_id[0]}:{source_id[1]}" if isinstance(source_id, tuple) else str(source_id)

        target_widget_textarea = None # 目标简单文本框 (CAN, I2C)
        protocol_name = ""            # 用于日志的协议名称
        raw_data_target = None      # 目标复杂控件 (UART, SPI)，需要转发原始数据

        # --- 根据包类型确定目标控件和协议名称 ---
        if packet_type == PacketType.DEBUG_CAN_RECV:
            target_widget_textarea = self.can_widget.receive_data_text
            protocol_name = "CAN"
        elif packet_type == PacketType.DEBUG_UART_RECV:
            raw_data_target = self.uart_widget # UART 数据需要转发给 UARTWidget
            protocol_name = "UART"
        elif packet_type == PacketType.DEBUG_SPI_RECV:
            raw_data_target = self.spi_widget # SPI 数据需要转发给 SPIWidget
            protocol_name = "SPI"
        elif packet_type == PacketType.DEBUG_I2C_RECV:
            target_widget_textarea = self.i2c_widget.receive_data_text
            protocol_name = "I2C"
        else:
            return # 如果不是调试器关心的包类型，直接返回

        # --- 如果找到了目标控件 ---
        if target_widget_textarea or raw_data_target:
            # --- 统一格式化显示字符串 ---
            display_string = ""
            if self.ascii_radio.isChecked(): # 如果选择 ASCII 显示
                try:
                    # 尝试解码，替换无法解码的字节
                    decoded_string = payload.decode('ascii', errors='replace').replace('\ufffd', '?')
                    # 处理不可打印字符，将其显示为 <HEX>
                    display_string = "".join(c if c.isprintable() or c in '\n\r\t' else f'<{ord(c):02X}>' for c in decoded_string)
                except Exception:
                    # 解码失败，回退到 HEX 显示
                    display_string = "[ASCII解码错误] " + ' '.join(f'{b:02X}' for b in payload)
            else: # HEX 显示
                display_string = ' '.join(f'{b:02X}' for b in payload)

            # --- 添加时间戳和来源信息 ---
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            full_display_string = f"[{timestamp}] From {source_desc} ({protocol_name}): {display_string}"

            # --- 将数据分发给目标控件 ---
            if raw_data_target and hasattr(raw_data_target, 'append_received_data'):
                # 对于 UART 和 SPI，调用它们的 append_received_data 方法
                # 这个方法内部会处理文本显示，并可能将 raw_data 转发给更具体的处理逻辑 (如 GY25)
                raw_data_target.append_received_data(full_display_string, payload)
            elif target_widget_textarea:
                # 对于 CAN 和 I2C，直接在文本框中追加格式化后的字符串
                target_widget_textarea.append(full_display_string)
                target_widget_textarea.ensureCursorVisible() # 自动滚动到底部