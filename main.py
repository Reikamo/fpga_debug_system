# main.py

import sys
import socket
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QListWidget, QGroupBox, QLabel,
                             QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox,
                             QComboBox, QTextEdit, QGridLayout, QCheckBox,
                             QMessageBox, QRadioButton, QSplitter, QAction, QMenuBar,
                             QFrame, QMenu, QStackedWidget, QListWidgetItem,
                             QStyle) # <--- QStyle 仍然需要 (用于侧边栏的折叠按钮)
from PyQt5.QtCore import QSettings, Qt, QDateTime, pyqtSignal, QEvent, QPoint, QSize
from PyQt5.QtGui import QFont, QIcon # <--- QIcon 导入是必须的
from PyQt5.QtCore import pyqtSlot

# 导入管理器和基类
from communication_manager import CommunicationManager
from network_manager import NetworkManager
from serial_manager import SerialManager

# 导入新的可伸缩侧边栏
from collapsible_sidebar import CollapsibleNavWidget

# 导入功能标签页
from oscilloscope_widget import OscilloscopeController
from signal_generator_widget import SignalGeneratorController
from logic_analyzer_widget import LogicAnalyzerController 
from fpga_debugger_widget import FPGADebuggerWidget
from protocol import PacketType

try:
    from settings_widget import SettingsWidget
except ImportError as e:
    print(f"CRITICAL: 无法导入 SettingsWidget. {e}")
    class SettingsWidget(QWidget): 
        log_message = pyqtSignal(str)
        def __init__(self, settings, parent=None):
            super().__init__(parent)
            self.setLayout(QVBoxLayout())
            self.layout().addWidget(QLabel(f"错误: 无法加载 SettingsWidget。\n{e}"))
        def load_settings(self): pass
        def save_settings(self): pass

try:
    from utils import get_local_ips
except ImportError:
    print("CRITICAL: 无法从 utils.py 导入 get_local_ips")
    def get_local_ips(): return ["127.0.0.1"] 

# 从 styles.py 导入主题应用函数
try:
    from styles import apply_modern_theme
except ImportError:
    print("警告: 无法导入 styles.py, 将使用默认Qt样式。")
    def apply_modern_theme(widget, theme="dark", effects=None): 
        print(f"警告: styles.py 未找到, 无法应用 {theme} 主题。")
        pass 


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("MyCompany", "FPGADebugSystem")
        self.setWindowTitle("FPGA 调试系统 v4.0)") 
        self.resize(1600, 900)

        # --- 架构设置 (保持不变) ---
        self.data_listener: NetworkManager = NetworkManager(parent=self)
        self.command_manager: CommunicationManager = None 
        self.udp_command_manager: NetworkManager = self.data_listener 
        self.serial_command_manager: SerialManager = SerialManager(parent=self)
        # --- 架构结束 ---

        # 实例化所有子控件/控制器
        self.oscilloscope = OscilloscopeController(None, parent=self)
        self.signal_gen = SignalGeneratorController(None, parent=self)
        self.logic_analyzer_controller = LogicAnalyzerController(None) 
        self.fpga_debugger = FPGADebuggerWidget(None, parent=self)
        self.settings_widget = SettingsWidget(self.settings, self)
        
        self.placeholder_widgets = {}

        self.setup_ui()
        self.setup_connections()
        
        self.load_settings() 
        
        self.update_command_manager_instance(self.comm_method_combo.currentText())
        self.update_widgets_communication_manager()
        self.update_connection_bar_status()
        self.update_connect_button_state()
        
        self.navigation_list.setCurrentRow(0)


    def setup_ui(self):
        """初始化主窗口UI为三栏布局"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # 1. 顶部连接栏
        connection_bar = self.create_connection_bar()
        connection_bar.setObjectName("connection_bar") 
        main_layout.addWidget(connection_bar)

        # 2. 主内容区 (垂直分割器：上部为三栏，下部为日志)
        log_splitter = QSplitter(Qt.Vertical)
        
        # 2a. 上部三栏区域 (水平分割器)
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setHandleWidth(1) 

        # --- 左侧导航栏 ---
        self.navigation_list = self._create_left_navigation()
        main_splitter.addWidget(self.navigation_list)

        # --- 中间显示区域 (堆栈) ---
        self.main_stack = QStackedWidget()
        self.main_stack.setObjectName("main_stack") 
        
        # --- 右侧配置区域 (堆栈) ---
        self.settings_stack = QStackedWidget()
        self.settings_stack.setObjectName("settings_stack") 

        # --- 填充堆栈 (保持不变) ---
        # 0: 示波器
        self.main_stack.addWidget(self.oscilloscope.get_display_widget())
        self.settings_stack.addWidget(self.oscilloscope.get_settings_widget())
        # 1: 信号发生器
        self.main_stack.addWidget(self.signal_gen.get_display_widget())
        self.settings_stack.addWidget(self.signal_gen.get_settings_widget())
        # 2: 逻辑分析仪
        self.main_stack.addWidget(self.logic_analyzer_controller.get_display_widget())
        self.settings_stack.addWidget(self.logic_analyzer_controller.get_settings_widget())
        # 3: FPGA调试
        self.main_stack.addWidget(self.fpga_debugger)
        self.settings_stack.addWidget(self._create_placeholder_widget("FPGA调试\n\n(配置在中间)"))
        # 4: 系统设置
        self.main_stack.addWidget(self.settings_widget)
        self.settings_stack.addWidget(self._create_placeholder_widget("系统设置\n\n(配置在中间)"))
        # --- 填充结束 ---
        
        self.content_splitter = QSplitter(Qt.Horizontal) 
        self.content_splitter.setHandleWidth(1) 
        self.content_splitter.addWidget(self.main_stack)
        self.content_splitter.addWidget(self.settings_stack)
        self.content_splitter.setStretchFactor(0, 3) 
        self.content_splitter.setStretchFactor(1, 1) 
        
        main_splitter.addWidget(self.content_splitter) 
        
        main_splitter.setStretchFactor(0, 0) # 左侧导航栏不拉伸
        main_splitter.setStretchFactor(1, 1) # (中+右) 区域拉伸

        # 2b. 下部日志区域
        log_widget = self.create_log_widget()
        log_widget.setObjectName("log_widget") 

        log_splitter.addWidget(main_splitter)
        log_splitter.addWidget(log_widget)
        log_splitter.setSizes([int(self.height() * 0.75), int(self.height() * 0.25)])
        
        main_layout.addWidget(log_splitter)
        
    def _create_left_navigation(self) -> CollapsibleNavWidget:
        """[!! 重大修改 !!] 创建可伸缩的侧边导航栏 (使用自定义图标)"""
        nav_widget = CollapsibleNavWidget()
        
        # [!! 修改 !!] 使用 QIcon 从文件加载自定义图标
        # 确保您已经在 fpga_debug_system/icons/ 文件夹中准备好了这些 .png 文件
        
        # 定义图标路径（假设 icons 文件夹在 main.py 旁边）
        icon_path = "icons/" 
        
        items = [
            (QIcon(icon_path + "icon_oscilloscope.png"), " 示波器"),
            (QIcon(icon_path + "icon_signal_gen.png"), " 信号发生器"),
            (QIcon(icon_path + "icon_logic_analyzer.png"), " 逻辑分析仪"),
            (QIcon(icon_path + "icon_fpga.png"), " FPGA调试"),
            (QIcon(icon_path + "icon_settings.png"), " 系统设置")
        ]
        
        for icon, text in items:
            nav_widget.addItem(icon, text)
        
        # 连接信号
        nav_widget.currentRowChanged.connect(self.on_navigation_changed)
        
        return nav_widget
        
    def _create_placeholder_widget(self, name: str) -> QWidget:
        """为模块创建右侧空白占位符"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel(f"{name}")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        layout.setAlignment(Qt.AlignCenter) 
        
        self.placeholder_widgets[name] = widget 
        return widget

    def create_connection_bar(self):
        """(保持不变)"""
        bar = QWidget()
        bar.setFixedHeight(60) 
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        layout.addWidget(QLabel("数据通道 (UDP):"))
        self.udp_listen_btn = QPushButton("开始监听")
        self.udp_listen_btn.setCheckable(True)
        layout.addWidget(self.udp_listen_btn)
        self.udp_status_label = QLabel("UDP未监听")
        self.udp_status_label.setMinimumWidth(150)
        layout.addWidget(self.udp_status_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        layout.addWidget(QLabel("命令通道:"))
        self.comm_method_combo = QComboBox()
        self.comm_method_combo.addItems(["UDP", "Serial"])
        layout.addWidget(self.comm_method_combo)

        self.connect_btn = QPushButton("连接")
        self.connect_btn.setCheckable(True)
        layout.addWidget(self.connect_btn)

        self.status_label = QLabel("命令通道未连接")
        self.status_label.setMinimumWidth(150)
        layout.addWidget(self.status_label)

        layout.addStretch()
        return bar

    def create_log_widget(self):
        """(保持不变)"""
        widget = QGroupBox("系统日志")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        top_layout = QHBoxLayout()
        top_layout.addStretch() 
        self.clear_log_btn = QPushButton("清除日志")
        top_layout.addWidget(self.clear_log_btn)
        layout.addLayout(top_layout) 
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier New", 9))
        layout.addWidget(self.log_text)
        return widget

    def setup_connections(self):
        """(保持不变)"""
        self.udp_listen_btn.clicked.connect(self.toggle_network_session)
        self.data_listener.session_changed.connect(self.on_network_session_changed)
        self.data_listener.log_message.connect(self.log_message)
        self.data_listener.data_received.connect(self.dispatch_data)
        self.comm_method_combo.currentTextChanged.connect(self.on_comm_method_changed)
        self.connect_btn.clicked.connect(self.toggle_command_session) 
        self.serial_command_manager.session_changed.connect(self.on_serial_command_session_changed)
        self.serial_command_manager.log_message.connect(self.log_message)
        self.clear_log_btn.clicked.connect(self.log_text.clear)
        for module in [self.oscilloscope, self.signal_gen, self.logic_analyzer_controller, 
                       self.fpga_debugger, self.settings_widget]:
            if module is not None and hasattr(module, 'log_message') and isinstance(module.log_message, pyqtSignal):
                module.log_message.connect(self.log_message)
    
    @pyqtSlot(int)
    def on_navigation_changed(self, index: int):
        """(保持不变) 调整布局的逻辑"""
        
        self.main_stack.setCurrentIndex(index)
        self.settings_stack.setCurrentIndex(index)

        # 索引 3: FPGA调试, 索引 4: 系统设置
        if index in [3, 4]:
            self.settings_stack.hide()
            self.content_splitter.setSizes([1, 0]) 
        else:
            self.settings_stack.show()
            total_width = sum(self.content_splitter.sizes())
            if total_width > 0:
                self.content_splitter.setSizes([int(total_width * 0.75), int(total_width * 0.25)])
            else:
                self.content_splitter.setSizes([800, 200]) # 默认值

    def update_widgets_communication_manager(self):
        """(保持不变)"""
        manager = self.command_manager
        for widget in [self.oscilloscope, self.signal_gen,
                       self.logic_analyzer_controller, self.fpga_debugger]:
            if widget is None: continue
            if hasattr(widget, 'set_communication_manager') and callable(widget.set_communication_manager):
                 widget.set_communication_manager(manager)
            elif hasattr(widget, 'network'): 
                 widget.network = manager
            else:
                 print(f"警告: 控件 {type(widget).__name__} 没有 set_communication_manager 方法或 network 属性。")
        if hasattr(self.settings_widget, 'set_communication_manager') and callable(self.settings_widget.set_communication_manager):
            self.settings_widget.set_communication_manager(manager)

    def update_command_manager_instance(self, method: str):
        """(保持不变)"""
        if method == "Serial":
            self.command_manager = self.serial_command_manager
        else: 
            self.command_manager = self.udp_command_manager
            
    def update_connection_bar_status(self):
        """(保持不变)"""
        if self.data_listener.is_running():
            local_ip = self.settings.value("local_ip", "")
            local_port = self.settings.value("local_port", "")
            self.udp_status_label.setText(f"监听中: {local_ip}:{local_port}")
            self.udp_status_label.setStyleSheet("color: green;")
        else:
            self.udp_status_label.setText("UDP未监听")
            self.udp_status_label.setStyleSheet("")
        method = self.comm_method_combo.currentText()
        if self.command_manager and self.command_manager.is_running():
            if method == "Serial":
                port = self.settings.value("serial_port", "")
                self.status_label.setText(f"Serial 已连接: {port}")
                self.status_label.setStyleSheet("color: green;")
            else: 
                target_ip = self.settings.value("target_ip", "")
                self.status_label.setText(f"UDP 已激活 (-> {target_ip})")
                self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setText(f"命令通道未连接 ({method})")
            self.status_label.setStyleSheet("")
            if method == "UDP" and not self.data_listener.is_running():
                self.status_label.setText("命令 (UDP) - 需监听")
                self.status_label.setStyleSheet("color: orange;")

    @pyqtSlot(str)
    def on_comm_method_changed(self, method: str):
        """(保持不变)"""
        if self.command_manager and self.command_manager.is_running():
            self.log_message(f"ℹ️ 命令通道方式已更改，正在停止旧会话...")
            self.connect_btn.setChecked(False) 
            if isinstance(self.command_manager, SerialManager):
                self.serial_command_manager.stop_session()
            else: 
                self.on_udp_command_session_changed(False)
        self.update_command_manager_instance(method)
        self.update_widgets_communication_manager()
        self.update_connection_bar_status()
        self.update_connect_button_state()
        self.settings.setValue("comm_method", method)

    def update_connect_button_state(self):
        """(保持不变)"""
        if self.command_manager and self.command_manager.is_running():
            self.connect_btn.setEnabled(True); return
        method = self.comm_method_combo.currentText()
        if method == "UDP":
            is_listener_running = self.data_listener.is_running()
            self.connect_btn.setEnabled(is_listener_running)
            if not is_listener_running:
                self.update_connection_bar_status()
        else: 
            self.connect_btn.setEnabled(True)

    def toggle_command_session(self):
        """(保持不变)"""
        method = self.comm_method_combo.currentText()
        if not self.command_manager:
            self.log_message("❌ 错误：命令管理器未初始化"); self.connect_btn.setChecked(False); return
        if method == "Serial":
            if self.connect_btn.isChecked(): 
                self.connect_btn.setEnabled(False) 
                port_name = self.settings.value("serial_port", "")
                baud_rate = int(self.settings.value("serial_baud", "115200"))
                if not port_name or port_name == "无可用串口":
                     self.log_message("❌ 错误：请在 '系统设置' 标签页中选择一个有效的串口。")
                     self.connect_btn.setChecked(False); self.connect_btn.setEnabled(True); return
                self.log_message(f"准备启动 Serial 命令通道: 端口 {port_name}, 波特率 {baud_rate}")
                if not self.serial_command_manager.start_session(port_name=port_name, baud_rate=baud_rate):
                     self.connect_btn.setChecked(False); self.connect_btn.setEnabled(True)
                     self.log_message(f"❌ 启动 Serial 命令通道失败。"); self.update_connection_bar_status()
            else: 
                 if self.serial_command_manager.is_running():
                      self.connect_btn.setEnabled(False) 
                      self.serial_command_manager.stop_session()
        elif method == "UDP":
            if not self.data_listener.is_running():
                self.log_message("⚠️ 警告：请先启动 UDP 监听 (数据通道)。")
                self.connect_btn.setChecked(False); self.update_connection_bar_status(); return
            if self.connect_btn.isChecked(): 
                self.log_message("ℹ️ UDP 命令通道已激活 (复用监听通道)。"); self.on_udp_command_session_changed(True)
            else: 
                self.log_message("ℹ️ UDP 命令通道已断开 (监听器仍在运行)。"); self.on_udp_command_session_changed(False)

    def toggle_network_session(self):
        """(保持不变)"""
        if self.udp_listen_btn.isChecked(): 
            self.udp_listen_btn.setEnabled(False) 
            local_ip = self.settings.value("local_ip", "")
            local_port = int(self.settings.value("local_port", 8088))
            target_ip = self.settings.value("target_ip", "")
            target_port = int(self.settings.value("target_port", 8080))
            if not target_ip or target_port <= 0 or not local_ip or local_port <= 0:
                 self.log_message("❌ 错误：请在 '系统设置' 标签页中配置有效的 UDP IP 和端口。")
                 self.udp_listen_btn.setChecked(False); self.udp_listen_btn.setEnabled(True); return
            self.log_message(f"准备启动 UDP 监听: 本地 {local_ip}:{local_port}, 目标 {target_ip}:{target_port}")
            if not self.data_listener.start_session(local_ip=local_ip, local_port=local_port, target_ip=target_ip, target_port=target_port):
                 self.udp_listen_btn.setChecked(False); self.udp_listen_btn.setEnabled(True)
                 self.log_message(f"❌ 启动 UDP 监听失败。"); self.update_connection_bar_status()
        else: 
             if self.data_listener.is_running():
                  self.udp_listen_btn.setEnabled(False) 
                  self.data_listener.stop_session()

    @pyqtSlot(bool)
    def on_serial_command_session_changed(self, is_running):
        """(保持不变)"""
        method = self.comm_method_combo.currentText()
        if method != "Serial": return 
        self.connect_btn.setEnabled(True); self.comm_method_combo.setEnabled(not is_running) 
        if is_running: self.connect_btn.setText("断开"); self.connect_btn.setChecked(True)
        else: self.connect_btn.setText("连接"); self.connect_btn.setChecked(False)
        self.update_widgets_communication_manager(); self.update_connection_bar_status()

    @pyqtSlot(bool)
    def on_udp_command_session_changed(self, is_running):
        """(保持不变)"""
        method = self.comm_method_combo.currentText()
        if method != "UDP": return 
        self.connect_btn.setEnabled(True); self.comm_method_combo.setEnabled(not is_running) 
        if is_running: self.connect_btn.setText("断开 (逻辑)"); self.connect_btn.setChecked(True)
        else: self.connect_btn.setText("连接"); self.connect_btn.setChecked(False)
        self.update_widgets_communication_manager(); self.update_connection_bar_status()

    @pyqtSlot(bool)
    def on_network_session_changed(self, is_running):
        """(保持不变)"""
        self.udp_listen_btn.setEnabled(True)
        if is_running: self.udp_listen_btn.setText("停止监听"); self.udp_listen_btn.setChecked(True)
        else: self.udp_listen_btn.setText("开始监听"); self.udp_listen_btn.setChecked(False)
        method = self.comm_method_combo.currentText()
        if method == "UDP": self.on_udp_command_session_changed(is_running) 
        self.update_connection_bar_status(); self.update_connect_button_state() 

    def dispatch_data(self, data, source_id):
        """(保持不变)"""
        source_desc = f"{source_id[0]}:{source_id[1]}" if isinstance(source_id, tuple) else source_id
        if not data: return
        header = data[0]; payload = data[1:]
        try:
            packet_type = PacketType(header)
            self.log_message(f"📥 收到 {packet_type.name} (0x{header:02X}) 来自 {source_desc} ({len(data)}B)")
            target_module = None 
            if packet_type == PacketType.OSC_DATA: target_module = self.oscilloscope
            elif packet_type == PacketType.LOGIC_ANALYZER_DATA: target_module = self.logic_analyzer_controller 
            elif packet_type == PacketType.DEBUG_DIGITAL_FREQ_RESULT: target_module = self.logic_analyzer_controller 
            elif packet_type in [PacketType.DEBUG_UART_RECV, PacketType.DEBUG_SPI_RECV,
                               PacketType.DEBUG_I2C_RECV, PacketType.DEBUG_CAN_RECV]:
                target_module = self.fpga_debugger
            if target_module and hasattr(target_module, 'handle_data'):
                 target_module.handle_data(packet_type, payload, source_id)
            elif target_module: self.log_message(f"⚠️ 控件 {type(target_module).__name__} 没有 handle_data 方法处理 {packet_type.name}")
            else: self.log_message(f"⚠️ 收到未处理的包: {packet_type.name} (0x{header:02X})")
        except ValueError: self.log_message(f"❌ 收到未知包头: 0x{header:02X}")
        except Exception as e:
            packet_name = packet_type.name if 'packet_type' in locals() else f'0x{header:02X}'
            self.log_message(f"❌ 分发数据时出错 ({packet_name}): {e}")

    def log_message(self, message: str):
        """(保持不变)"""
        timestamp = QDateTime.currentDateTime().toString("hh:mm:ss.zzz")
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.ensureCursorVisible()

    def load_settings(self):
        """(保持不变)"""
        geom = self.settings.value("main_window_geometry"); 
        if geom: self.restoreGeometry(geom)
        self.comm_method_combo.setCurrentText(self.settings.value("comm_method", "UDP"))
        self.settings_widget.load_settings() 
        i2c_slave_addr = int(self.settings.value("i2c_slave_address", 0x3C)) 
        if self.fpga_debugger and hasattr(self.fpga_debugger, 'i2c_widget') and hasattr(self.fpga_debugger.i2c_widget, 'slave_addr_spin'):
            self.fpga_debugger.i2c_widget.slave_addr_spin.setValue(i2c_slave_addr)
        self.log_message("加载窗口设置。")

    def save_settings(self):
        """(保持不变)"""
        self.settings.setValue("main_window_geometry", self.saveGeometry())
        self.settings.setValue("comm_method", self.comm_method_combo.currentText())
        if self.settings_widget: self.settings_widget.save_settings() 
        if self.fpga_debugger and hasattr(self.fpga_debugger, 'i2c_widget') and hasattr(self.fpga_debugger.i2c_widget, 'slave_addr_spin'):
            self.settings.setValue("i2c_slave_address", self.fpga_debugger.i2c_widget.slave_addr_spin.value())
        self.log_message("窗口设置已保存。")

    def closeEvent(self, event):
        """(保持不变)"""
        self.save_settings() 
        if self.serial_command_manager and self.serial_command_manager.is_running():
            self.serial_command_manager.stop_session()
        if self.data_listener and self.data_listener.is_running():
            self.data_listener.stop_session()
        if self.oscilloscope and hasattr(self.oscilloscope, 'close'): self.oscilloscope.close()
        if self.signal_gen and hasattr(self.signal_gen, 'close'): self.signal_gen.close()
        if self.logic_analyzer_controller and hasattr(self.logic_analyzer_controller, 'close'): self.logic_analyzer_controller.close()
        event.accept()

# --- 程序入口 ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setOrganizationName("MyCompany")
    app.setApplicationName("FPGADebugSystem")
    
    main_win = MainWindow()
    
    # [!! 修改 !!] 从 styles.py 应用浅色主题
    apply_modern_theme(main_win, theme="light")
    
    main_win.show()
    sys.exit(app.exec_())