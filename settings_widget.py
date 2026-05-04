# fpga_debug_system/settings_widget.py

import sys
import inspect 
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QGroupBox, QLabel, QLineEdit, QPushButton, QSpinBox, QComboBox,
    QDialogButtonBox, QGridLayout, QTableWidget, QHeaderView, QTableWidgetItem,
    QMessageBox
)
from PyQt5.QtCore import QSettings, Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor

# 导入协议和串口管理器（用于获取端口）
try:
    from protocol import PacketType
    from serial_manager import SerialManager
    from utils import get_local_ips 
except ImportError:
    print("SettingsWidget: 无法导入依赖，请确保 utils.py, protocol.py 和 serial_manager.py 在路径中")
    from enum import IntEnum
    class PacketType(IntEnum):
        ERROR = 0xFF
    class SerialManager:
        @staticmethod
        def get_available_ports(): return ["COM1 (未找到)"]
    def get_local_ips(): return ["127.0.0.1"]


class SettingsWidget(QWidget):
    """
    应用程序设置控件（作为主标签页）。
    管理通信（UDP/Serial）和显示协议包头。
    """
    log_message = pyqtSignal(str)
    
    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget, 1)

        self.comm_tab = QWidget()
        self.protocol_tab = QWidget()
        self.tab_widget.addTab(self.comm_tab, "🔌 通信设置")
        self.tab_widget.addTab(self.protocol_tab, "📦 协议包头")

        self.setup_comm_tab()
        self.setup_protocol_tab()

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        self.save_btn = QPushButton("💾 保存设置")
        self.save_btn.clicked.connect(self.save_settings)
        bottom_layout.addWidget(self.save_btn)
        main_layout.addLayout(bottom_layout)

        self.load_settings()

    def setup_comm_tab(self):
        """构建通信设置标签页的UI。"""
        layout = QVBoxLayout(self.comm_tab)
        
        # --- UDP 设置 ---
        udp_group = QGroupBox("UDP (数据通道)")
        udp_layout = QGridLayout(udp_group)
        
        udp_layout.addWidget(QLabel("本地IP (监听):"), 0, 0)
        self.local_ip_combo = QComboBox()
        self.local_ip_combo.setEditable(True)
        self.local_ip_combo.addItems(get_local_ips())
        udp_layout.addWidget(self.local_ip_combo, 0, 1)
        
        udp_layout.addWidget(QLabel("本地端口 (监听):"), 0, 2)
        self.local_port_spin = QSpinBox()
        self.local_port_spin.setRange(1, 65535)
        udp_layout.addWidget(self.local_port_spin, 0, 3)
        
        udp_layout.addWidget(QLabel("目标IP (收/发):"), 1, 0) 
        self.target_ip_input = QLineEdit()
        udp_layout.addWidget(self.target_ip_input, 1, 1)
        
        udp_layout.addWidget(QLabel("目标端口 (收/发):"), 1, 2) 
        self.target_port_spin = QSpinBox()
        self.target_port_spin.setRange(1, 65535)
        udp_layout.addWidget(self.target_port_spin, 1, 3)
        
        udp_layout.setColumnStretch(1, 1)
        udp_layout.setColumnStretch(3, 1)
        layout.addWidget(udp_group)

        # --- Serial 设置 ---
        serial_group = QGroupBox("Serial (命令通道)")
        serial_layout = QGridLayout(serial_group)
        
        serial_layout.addWidget(QLabel("串口:"), 0, 0)
        self.serial_port_combo = QComboBox()
        serial_layout.addWidget(self.serial_port_combo, 0, 1)
        
        self.refresh_ports_btn = QPushButton("刷新")
        self.refresh_ports_btn.clicked.connect(self.refresh_serial_ports)
        serial_layout.addWidget(self.refresh_ports_btn, 0, 2)
        
        serial_layout.addWidget(QLabel("波特率:"), 1, 0)
        self.serial_baud_combo = QComboBox()
        self.serial_baud_combo.addItems(['9600', '19200', '38400', '57600', '115200', '230400', '460800', '921600'])
        serial_layout.addWidget(self.serial_baud_combo, 1, 1)
        
        serial_layout.setColumnStretch(1, 1)
        layout.addWidget(serial_group)
        
        self.refresh_serial_ports()
        
        layout.addStretch()

    def setup_protocol_tab(self):
        """构建协议包头显示标签页的UI。"""
        layout = QVBoxLayout(self.protocol_tab)
        
        info_label = QLabel("在此处修改包头值 (Hex)。 [!] 注意：保存后必须重启应用程序才能生效。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: orange; font-weight: bold;")
        layout.addWidget(info_label)

        self.protocol_table = QTableWidget()
        
        self.protocol_table.setColumnCount(4)
        self.protocol_table.setHorizontalHeaderLabels(["名称 (枚举)", "值 (Hex)", "名称 (枚举)", "值 (Hex)"])
        
        self.protocol_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.protocol_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.protocol_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.protocol_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        
        self.populate_protocol_table()
        
        layout.addWidget(self.protocol_table)

    def populate_protocol_table(self):
        """从 PacketType 枚举中读取数据并填充表格。"""
        try:
            enum_items = list(PacketType) 
            
            num_items = len(enum_items)
            num_rows = (num_items + 1) // 2 

            self.protocol_table.setRowCount(num_rows)
            
            for i in range(num_rows):
                # --- 填充左侧两列 (索引 i) ---
                if i < num_items:
                    member_left = enum_items[i]
                    name_left = member_left.name
                    value_left = member_left.value
                    
                    name_item_left = QTableWidgetItem(name_left)
                    name_item_left.setFlags(name_item_left.flags() & ~Qt.ItemIsEditable) 
                    name_item_left.setForeground(QColor(200, 200, 200)) 
                    self.protocol_table.setItem(i, 0, name_item_left)
                    
                    value_item_left = QTableWidgetItem(f"{value_left:02X}")
                    value_item_left.setFont(QFont("Courier New", 10)) 
                    self.protocol_table.setItem(i, 1, value_item_left)
    
                # --- 填充右侧两列 (索引 i + num_rows) ---
                index_right = i + num_rows
                if index_right < num_items:
                    member_right = enum_items[index_right]
                    name_right = member_right.name
                    value_right = member_right.value
                    
                    name_item_right = QTableWidgetItem(name_right)
                    name_item_right.setFlags(name_item_right.flags() & ~Qt.ItemIsEditable) 
                    name_item_right.setForeground(QColor(200, 200, 200)) 
                    self.protocol_table.setItem(i, 2, name_item_right)
                    
                    value_item_right = QTableWidgetItem(f"{value_right:02X}")
                    value_item_right.setFont(QFont("Courier New", 10))
                    self.protocol_table.setItem(i, 3, value_item_right)
                
        except Exception as e:
            self.protocol_table.setRowCount(1)
            self.protocol_table.setItem(0, 0, QTableWidgetItem("Error"))
            self.protocol_table.setItem(0, 1, QTableWidgetItem(str(e)))
            print(f"Failed to populate protocol table: {e}")

    def refresh_serial_ports(self):
        """刷新串口列表（从 SerialManager）。"""
        current_port = self.serial_port_combo.currentText()
        self.serial_port_combo.clear()
        ports = SerialManager.get_available_ports()
        self.serial_port_combo.addItems(ports)
        if not ports:
             self.serial_port_combo.addItem("无可用串口")
             self.serial_port_combo.setEnabled(False)
        else:
             self.serial_port_combo.setEnabled(True)
             index = self.serial_port_combo.findText(current_port)
             if index != -1:
                 self.serial_port_combo.setCurrentIndex(index)

    def load_settings(self):
        """从 QSettings 加载配置并更新UI。"""
        # UDP
        self.target_ip_input.setText(self.settings.value("target_ip", "192.168.1.100"))
        self.target_port_spin.setValue(int(self.settings.value("target_port", 8080)))
        self.local_port_spin.setValue(int(self.settings.value("local_port", 8088)))
        saved_local_ip = self.settings.value("local_ip", "")
        if saved_local_ip and self.local_ip_combo.findText(saved_local_ip) != -1:
            self.local_ip_combo.setCurrentText(saved_local_ip)
        elif self.local_ip_combo.count() > 0:
             self.local_ip_combo.setCurrentIndex(0)

        # Serial
        saved_serial_port = self.settings.value("serial_port", "")
        
        self.refresh_serial_ports() 
            
        if saved_serial_port and self.serial_port_combo.findText(saved_serial_port) != -1:
             self.serial_port_combo.setCurrentText(saved_serial_port)
        self.serial_baud_combo.setCurrentText(self.settings.value("serial_baud", "115200"))
    
    def save_settings(self):
        """将UI中的配置保存到 QSettings。"""
        # --- 1. 保存通信设置 ---
        self.settings.setValue("target_ip", self.target_ip_input.text())
        self.settings.setValue("target_port", self.target_port_spin.value())
        self.settings.setValue("local_ip", self.local_ip_combo.currentText())
        self.settings.setValue("local_port", self.local_port_spin.value())
        self.settings.setValue("serial_port", self.serial_port_combo.currentText())
        self.settings.setValue("serial_baud", self.serial_baud_combo.currentText())

        # --- 2. [新] 保存协议包头重写 ---
        overrides = {}
        invalid_entries = []
        
        for r in range(self.protocol_table.rowCount()):
            # 检查第1列 (名称) 和 第2列 (值)
            name_item_1 = self.protocol_table.item(r, 0)
            value_item_1 = self.protocol_table.item(r, 1)
            
            if name_item_1 and value_item_1:
                name = name_item_1.text()
                value_str = value_item_1.text().strip().upper()
                if self.validate_hex_value(value_str):
                    overrides[name] = f"0x{value_str.replace('0X', '')}"
                else:
                    invalid_entries.append(name)
            
            # 检查第3列 (名称) 和 第4列 (值)
            name_item_2 = self.protocol_table.item(r, 2)
            value_item_2 = self.protocol_table.item(r, 3)
            
            if name_item_2 and value_item_2:
                name = name_item_2.text()
                value_str = value_item_2.text().strip().upper()
                if self.validate_hex_value(value_str):
                    overrides[name] = f"0x{value_str.replace('0X', '')}"
                else:
                    invalid_entries.append(name)

        if invalid_entries:
            QMessageBox.warning(self, "保存失败", 
                f"以下包头的 '值 (Hex)' 格式无效，未保存：\n"
                f"{', '.join(invalid_entries)}\n\n"
                "请确保它们是有效的十六进制值 (例如: F0, AA, 0xAB)。")
            # --- [ 修复点 1 ] ---
            self.log_message.emit(f"❌ 协议包头保存失败：{len(invalid_entries)} 个条目无效。")
            return # 不保存任何设置
        
        # 将重写字典存入 QSettings
        self.settings.setValue("protocol_overrides", overrides)
        # --- [新] 结束 ---

        # --- [ 修复点 2: 导致您报错的行 ] ---
        self.log_message.emit("ℹ️ 系统设置已保存。请注意：协议包头更改需要重启应用程序才能生效。")
        
        QMessageBox.information(self, "已保存", 
            "设置已保存。\n\n"
            "**重要提示：** 协议包头 (Packet Headers) 的更改\n"
            "**需要重启应用程序** 才能生效。")
            
    def validate_hex_value(self, value_str: str) -> bool:
        """检查字符串是否为有效的十六进制值"""
        if not value_str:
            return False
        if value_str.startswith("0x") or value_str.startswith("0X"):
            value_str = value_str[2:]
        
        if not value_str: 
            return False
            
        try:
            int(value_str, 16)
            return True
        except ValueError:
            return False