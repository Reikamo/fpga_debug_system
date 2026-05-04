# oled_widget.py
import struct
import time
import os
import io 
from typing import Callable, Optional, List, Tuple, TYPE_CHECKING
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QSpinBox, QMessageBox,
    QPlainTextEdit, QGridLayout, QFileDialog, QFontDialog,
    QInputDialog # <--- 新增导入
)
from PyQt5.QtGui import QFont, QIntValidator, QRegExpValidator, QFontDatabase, QFontInfo
from PyQt5.QtCore import QRegExp, Qt
from protocol import PacketType  # 确保 protocol.py 在路径中

# --- [新增导入：Pillow 滤镜和增强工具] ---
try:
    from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps, ImageFilter
    _PILLOW_AVAILABLE = True
except ImportError:
    print("警告：Pillow 库未安装或找不到。文本和图像显示功能将不可用。")
    print("请运行 'pip install Pillow' 来安装。")
    # 定义占位符
    Image = None
    ImageDraw = None
    ImageFont = None
    ImageEnhance = None # <--- 新增
    ImageOps = None     # <--- 新增
    ImageFilter = None  # <--- 新增
    _PILLOW_AVAILABLE = False

if TYPE_CHECKING:
    from PIL import Image as PILImage
    from PIL import ImageDraw, ImageFont

# --- [导入 CairoSVG] ---
try:
    import cairosvg
    _CAIROSVG_AVAILABLE = True
except ImportError:
    print("警告：cairosvg 库未安装。SVG 图像支持将不可用。")
    print("请运行 'pip install cairosvg' 来安装。")
    cairosvg = None
    _CAIROSVG_AVAILABLE = False

class OLEDWidget(QWidget):
    """用于控制 0.96 英寸 I2C OLED (SSD1306) 的控件，支持文本和图像显示（作为独立窗口）"""

    # --- SSD1306 Command Constants ---
    SETCONTRAST = 0x81
    DISPLAYALLON_RESUME = 0xA4
    DISPLAYALLON = 0xA5
    NORMALDISPLAY = 0xA6
    INVERTDISPLAY = 0xA7
    DISPLAYOFF = 0xAE
    DISPLAYON = 0xAF
    SETDISPLAYOFFSET = 0xD3
    SETCOMPINS = 0xDA
    SETVCOMDETECT = 0xDB
    SETDISPLAYCLOCKDIV = 0xD5
    SETPRECHARGE = 0xD9
    SETMULTIPLEX = 0xA8
    SETLOWCOLUMN = 0x00
    SETHIGHCOLUMN = 0x10
    SETSTARTLINE = 0x40
    MEMORYMODE = 0x20
    COLUMNADDR = 0x21
    PAGEADDR = 0x22
    COMSCANINC = 0xC0
    COMSCANDEC = 0xC8
    SEGREMAP = 0xA0
    CHARGEPUMP = 0x8D
    EXTERNALVCC = 0x1
    SWITCHCAPVCC = 0x2
    ACTIVATE_SCROLL = 0x2F
    DEACTIVATE_SCROLL = 0x2E
    SET_VERTICAL_SCROLL_AREA = 0xA3
    RIGHT_HORIZONTAL_SCROLL = 0x26
    LEFT_HORIZONTAL_SCROLL = 0x27
    VERTICAL_AND_RIGHT_HORIZONTAL_SCROLL = 0x29
    VERTICAL_AND_LEFT_HORIZONTAL_SCROLL = 0x2A

    COMMAND_CONTROL_BYTE = 0x00
    DATA_CONTROL_BYTE = 0x40

    INIT_SEQUENCE = bytes([
        DISPLAYOFF,              # 0xAE
        SETDISPLAYCLOCKDIV, 0x80, # 0xD5, 0x80
        SETMULTIPLEX, 0x3F,      # 0xA8, 0x3F (for 64 rows)
        SETDISPLAYOFFSET, 0x00,  # 0xD3, 0x00
        SETSTARTLINE | 0x00,     # 0x40
        CHARGEPUMP, 0x14,        # 0x8D, 0x14 (using internal VCC)
        MEMORYMODE, 0x00,        # 0x20, 0x00 (Horizontal addressing mode)
        SEGREMAP | 0x01,         # 0xA1 (remap columns, 127->0)
        COMSCANDEC,              # 0xC8 (remap rows, N-1 -> 0)
        SETCOMPINS, 0x12,        # 0xDA, 0x12 (sequential COM pins, disable remap for 128x64)
        SETCONTRAST, 0xCF,       # 0x81, 0xCF
        SETPRECHARGE, 0xF1,      # 0xD9, 0xF1 (for internal VCC)
        SETVCOMDETECT, 0x40,     # 0xDB, 0x40
        DISPLAYALLON_RESUME,     # 0xA4
        NORMALDISPLAY,           # 0xA6
        DISPLAYON                # 0xAF
    ])

    def __init__(self, packet_sender: Callable, parent=None):
        super().__init__(parent, Qt.Window)
        self.packet_sender = packet_sender
        self.slave_address = 0x3C
        self.current_font_path = None
        self.current_font_size = 10
        self.setWindowTitle("OLED 控制面板")
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        self.resize(500, 450) 

        # --- 地址和基本控制 ---
        control_group = QGroupBox("基本控制")
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("从机地址 (7-bit, Hex):"))
        self.addr_edit = QLineEdit(f"{self.slave_address:02X}")
        self.addr_edit.setValidator(QRegExpValidator(QRegExp("[0-9A-Fa-f]{1,2}")))
        self.addr_edit.setMaximumWidth(50)
        self.addr_edit.editingFinished.connect(self._update_slave_address)
        control_layout.addWidget(self.addr_edit)
        control_layout.addStretch()
        self.init_button = QPushButton("初始化屏幕")
        self.init_button.clicked.connect(self.initialize_oled)
        control_layout.addWidget(self.init_button)
        self.clear_button = QPushButton("清空屏幕")
        self.clear_button.clicked.connect(self.clear_oled)
        control_layout.addWidget(self.clear_button)
        self.on_button = QPushButton("打开显示")
        self.on_button.clicked.connect(lambda: self.send_oled_command(self.DISPLAYON))
        control_layout.addWidget(self.on_button)
        self.off_button = QPushButton("关闭显示")
        self.off_button.clicked.connect(lambda: self.send_oled_command(self.DISPLAYOFF))
        control_layout.addWidget(self.off_button)
        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)

        # --- 发送命令/数据 ---
        send_group = QGroupBox("手动发送")
        send_layout = QGridLayout()
        send_layout.addWidget(QLabel("命令 (HEX):"), 0, 0)
        self.cmd_edit = QLineEdit()
        self.cmd_edit.setPlaceholderText("例如: AE")
        self.cmd_edit.setValidator(QRegExpValidator(QRegExp("[0-9A-Fa-f ]*")))
        send_layout.addWidget(self.cmd_edit, 0, 1)
        send_cmd_button = QPushButton("发送命令")
        send_cmd_button.clicked.connect(self.send_manual_command)
        send_layout.addWidget(send_cmd_button, 0, 2)
        send_layout.addWidget(QLabel("数据 (HEX):"), 1, 0)
        self.data_edit = QLineEdit()
        self.data_edit.setPlaceholderText("例如: FF 00 FF")
        self.data_edit.setValidator(QRegExpValidator(QRegExp("[0-9A-Fa-f ]*")))
        send_layout.addWidget(self.data_edit, 1, 1)
        send_data_button = QPushButton("发送数据")
        send_data_button.clicked.connect(self.send_manual_data)
        send_layout.addWidget(send_data_button, 1, 2)
        send_group.setLayout(send_layout)
        main_layout.addWidget(send_group)

        # --- 填充测试 ---
        fill_group = QGroupBox("填充测试")
        fill_layout = QHBoxLayout()
        fill_layout.addWidget(QLabel("填充值 (HEX):"))
        self.fill_value_edit = QLineEdit("FF")
        self.fill_value_edit.setValidator(QRegExpValidator(QRegExp("[0-9A-Fa-f]{1,2}")))
        self.fill_value_edit.setMaximumWidth(50)
        fill_layout.addWidget(self.fill_value_edit)
        fill_button = QPushButton("填充全屏")
        fill_button.clicked.connect(self.fill_oled)
        fill_layout.addWidget(fill_button)
        fill_layout.addStretch()
        fill_group.setLayout(fill_layout)
        main_layout.addWidget(fill_group)

        # --- 显示文本 ---
        text_group = QGroupBox("显示文本")
        text_layout = QGridLayout()
        text_layout.addWidget(QLabel("文本:"), 0, 0)
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("输入要显示的文本")
        text_layout.addWidget(self.text_input, 0, 1, 1, 3)
        self.font_button = QPushButton("选择字体")
        self.font_button.clicked.connect(self.select_font)
        text_layout.addWidget(self.font_button, 1, 0)
        self.font_label = QLabel(f"字体: 默认, 大小: {self.current_font_size}")
        text_layout.addWidget(self.font_label, 1, 1, 1, 2)
        display_text_button = QPushButton("显示文本")
        display_text_button.clicked.connect(self.display_text_on_oled)
        text_layout.addWidget(display_text_button, 1, 3)
        text_group.setLayout(text_layout)
        if _PILLOW_AVAILABLE:
             main_layout.addWidget(text_group)
        else:
             disabled_text_group = QGroupBox("显示文本 (Pillow未安装)")
             disabled_layout = QVBoxLayout()
             disabled_layout.addWidget(QLabel("请先安装 Pillow 库 (`pip install Pillow`) 以启用此功能。"))
             disabled_text_group.setLayout(disabled_layout)
             main_layout.addWidget(disabled_text_group)


        # --- 显示图片 ---
        image_group = QGroupBox("显示图片")
        image_layout = QHBoxLayout()
        self.load_image_button = QPushButton("加载图片")
        self.load_image_button.clicked.connect(self.load_image_to_oled)
        image_layout.addWidget(self.load_image_button)
        image_layout.addStretch()
        image_group.setLayout(image_layout)
        if _PILLOW_AVAILABLE:
            main_layout.addWidget(image_group)
        else:
            disabled_image_group = QGroupBox("显示图片 (Pillow未安装)")
            disabled_layout = QVBoxLayout()
            disabled_layout.addWidget(QLabel("请先安装 Pillow 库 (`pip install Pillow`) 以启用此功能。"))
            disabled_image_group.setLayout(disabled_layout)
            main_layout.addWidget(disabled_image_group)

        main_layout.addStretch()

    def _update_slave_address(self):
        try:
            addr_str = self.addr_edit.text().strip()
            if addr_str:
                new_addr = int(addr_str, 16)
                if 0 <= new_addr <= 0x7F:
                    self.slave_address = new_addr
                    print(f"OLED 从机地址更新为: 0x{self.slave_address:02X}")
                else:
                    QMessageBox.warning(self, "地址错误", "从机地址必须在 0x00 到 0x7F 之间。")
                    self.addr_edit.setText(f"{self.slave_address:02X}")
            else:
                self.addr_edit.setText(f"{self.slave_address:02X}")
        except ValueError:
            QMessageBox.warning(self, "格式错误", "无效的十六进制地址。")
            self.addr_edit.setText(f"{self.slave_address:02X}")

    def _send_i2c_packet(self, i2c_payload: bytes) -> bool:
        address_byte = (self.slave_address << 1) | 0x00 # Write
        data_len = len(i2c_payload)
        if data_len == 0:
            QMessageBox.warning(self, "警告", "尝试发送空的 I2C 载荷")
            return False
        protocol_payload_header = struct.pack('!BB', address_byte, data_len)
        full_protocol_payload = protocol_payload_header + i2c_payload
        packet = struct.pack('!B', PacketType.DEBUG_I2C_TRANSFER) + full_protocol_payload
        return self.packet_sender(packet)

    def send_oled_command(self, command_byte: int) -> bool:
        i2c_payload = bytes([self.COMMAND_CONTROL_BYTE, command_byte])
        return self._send_i2c_packet(i2c_payload)

    def send_oled_commands(self, command_bytes: bytes) -> bool:
        success = True
        for cmd in command_bytes:
            if not self.send_oled_command(cmd):
                success = False
                QMessageBox.warning(self, "发送失败", f"发送命令 0x{cmd:02X} 失败")
                break
        return success

    def send_oled_data(self, data_bytes: bytes) -> bool:
        if not data_bytes: return True
        MAX_I2C_DATA_PER_TRANSFER = 64
        offset = 0
        success = True
        while offset < len(data_bytes):
            chunk_data = data_bytes[offset : offset + MAX_I2C_DATA_PER_TRANSFER]
            i2c_payload = bytes([self.DATA_CONTROL_BYTE]) + chunk_data
            if not self._send_i2c_packet(i2c_payload):
                 success = False
                 QMessageBox.warning(self, "发送失败", f"发送数据块失败 (offset={offset})")
                 break
            offset += len(chunk_data)
            time.sleep(0.001) 
            
        return success

    def initialize_oled(self):
        QMessageBox.information(self, "操作", "正在发送初始化序列...")
        self._update_slave_address()
        if self.send_oled_commands(self.INIT_SEQUENCE):
            QMessageBox.information(self, "成功", "OLED 初始化命令发送完成。")

    def clear_oled(self):
        QMessageBox.information(self, "操作", "正在发送清屏命令...")
        self._update_slave_address()
        set_addr_commands = bytes([
            self.COLUMNADDR, 0x00, 0x7F, # Column 0-127
            self.PAGEADDR, 0x00, 0x07  # Page 0-7
        ])
        if not self.send_oled_commands(set_addr_commands):
            return
        clear_data = bytes([0x00] * (128 * 64 // 8))
        if self.send_oled_data(clear_data):
            QMessageBox.information(self, "成功", "OLED 清屏完成。")

    def send_manual_command(self):
        self._update_slave_address()
        cmd_str = self.cmd_edit.text().strip()
        if not cmd_str:
            QMessageBox.warning(self, "输入错误", "请输入要发送的命令 (HEX)。")
            return
        try:
            cmd_bytes_list = [int(b, 16) for b in cmd_str.split()]
            if not cmd_bytes_list: raise ValueError("无有效命令")
            QMessageBox.information(self, "操作", f"正在发送命令: {cmd_str}")
            self.send_oled_commands(bytes(cmd_bytes_list))
        except ValueError:
            QMessageBox.warning(self, "格式错误", "无效的十六进制命令格式。请用空格分隔字节，例如: AE D5 80")

    def send_manual_data(self):
        self._update_slave_address()
        data_str = self.data_edit.text().strip()
        if not data_str:
            QMessageBox.warning(self, "输入错误", "请输入要发送的数据 (HEX)。")
            return
        try:
            hex_str = "".join(data_str.split())
            if len(hex_str) % 2 != 0: hex_str = '0' + hex_str
            data_bytes = bytes.fromhex(hex_str)
            QMessageBox.information(self, "操作", f"正在发送数据: {data_str}")
            self.send_oled_data(data_bytes)
        except ValueError:
            QMessageBox.warning(self, "格式错误", "无效的十六进制数据格式。")

    def fill_oled(self):
        self._update_slave_address()
        fill_str = self.fill_value_edit.text().strip()
        try:
            if not fill_str: raise ValueError("填充值不能为空")
            if len(fill_str) > 2: raise ValueError("填充值必须是1字节")
            fill_byte = int(fill_str, 16)
            QMessageBox.information(self, "操作", f"正在使用 0x{fill_byte:02X} 填充屏幕...")
            set_addr_commands = bytes([self.COLUMNADDR, 0x00, 0x7F, self.PAGEADDR, 0x00, 0x07])
            if not self.send_oled_commands(set_addr_commands):
                return
            fill_data = bytes([fill_byte] * (128 * 64 // 8))
            self.send_oled_data(fill_data)
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", f"无效的填充值: {e}")

    # --- 文本和图像处理辅助函数 ---
    def _find_font(self, font_name: str = "Arial") -> Optional[str]:
        """尝试查找常用系统字体路径 (改进版 v2 - 修复中文名匹配)"""
        font_name_map = {
            "宋体": "simsun",
            "新宋体": "nsimsun",
            "微软雅黑": "msyh",
            "黑体": "simhei",
            "楷体": "simkai",
        }
        
        original_font_name = font_name 
        for chinese_name, file_prefix in font_name_map.items():
            if font_name.startswith(chinese_name):
                font_name = file_prefix 
                print(f"字体名称映射: '{original_font_name}' -> '{font_name}'")
                break

        if os.name == 'nt':
             font_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
             common_extensions = ['.ttf', '.otf', '.ttc'] 
             font_name_lower = font_name.lower()
             font_name_no_space_lower = font_name.lower().replace(' ', '')
             base_font_name_lower = font_name.split(' ')[0].lower()
             original_font_name_lower = original_font_name.lower()
             original_font_name_no_space_lower = original_font_name_lower.replace(' ', '')
             common_styles = ['', 'bd', 'i', 'bi', ' BOLD', ' ITALIC', ' BOLD ITALIC', '_BOLD', '_ITALIC', '_BOLD_ITALIC']
             for style in [''] + common_styles:
                 for ext in common_extensions: 
                     potential_name = f"{font_name.split(' ')[0]}{style.replace(' ','')}{ext}"
                     potential_path = os.path.join(font_dir, potential_name)
                     if os.path.exists(potential_path): return potential_path
                     potential_path_lower = os.path.join(font_dir, potential_name.lower())
                     if os.path.exists(potential_path_lower): return potential_path_lower
                     potential_name_orig = f"{original_font_name}{ext}" 
                     potential_path_orig = os.path.join(font_dir, potential_name_orig)
                     if os.path.exists(potential_path_orig): return potential_path_orig
             try:
                 for filename in os.listdir(font_dir):
                     if not filename.lower().endswith(tuple(common_extensions)):
                         continue
                     name_part = os.path.splitext(filename)[0]
                     name_part_lower = name_part.lower()
                     if name_part_lower == font_name_lower or name_part_lower == font_name_no_space_lower:
                         return os.path.join(font_dir, filename)
                     if name_part_lower == original_font_name_lower or name_part_lower == original_font_name_no_space_lower:
                         return os.path.join(font_dir, filename)
                     if base_font_name_lower in name_part_lower:
                         return os.path.join(font_dir, filename)
                     if name_part_lower in font_name_no_space_lower:
                         return os.path.join(font_dir, filename)
             except OSError:
                 pass 
        elif os.name == 'posix':
             font_dirs = ['/usr/share/fonts', '/usr/local/share/fonts', os.path.expanduser('~/.fonts'), '/Library/Fonts', '/System/Library/Fonts']
             common_extensions = ['.ttf', '.otf', '.ttc'] 
             for directory in font_dirs:
                 if not os.path.isdir(directory): continue
                 try:
                     for root, _, files in os.walk(directory):
                          for filename in files:
                               name, ext = os.path.splitext(filename)
                               if font_name.lower() in name.lower() and ext.lower() in common_extensions:
                                    return os.path.join(root, filename)
                 except OSError:
                     continue
        return None

    def _convert_image_to_oled_bytes(self, image: "PILImage.Image", oled_width=128, oled_height=64) -> Optional[bytes]:
        """将 Pillow '1' 模式图像转换为 SSD1306 字节 (Page Mode)"""
        if not _PILLOW_AVAILABLE:
             print("错误：尝试使用图像转换功能，但 Pillow 未加载。")
             return None
        try:
            buffer = bytearray(oled_width * oled_height // 8)
            pixels = image.load() 
            for page in range(oled_height // 8):
                for x in range(oled_width):
                    byte_index = page * oled_width + x
                    byte_value = 0
                    for bit in range(8):
                        pixel_y = page * 8 + bit
                        if pixels[x, pixel_y] != 0:
                            byte_value |= (1 << bit)
                    if byte_index < len(buffer):
                        buffer[byte_index] = byte_value
                    else:
                        print(f"警告：索引 {byte_index} 超出范围")
                        break
                else:
                    continue
                break
            return bytes(buffer)
        except Exception as e:
            print(f"图像到字节转换失败: {e}")
            return None

    def text_to_oled_bytes(self, text: str, oled_width=128, oled_height=64, font_path: Optional[str] = None, font_size: int = 10) -> Optional[bytes]:
        """将文本渲染为 SSD1306 的字节格式"""
        if not _PILLOW_AVAILABLE:
            print("错误：尝试使用文本渲染功能，但 Pillow 未加载。")
            return None
        try:
            image = Image.new('1', (oled_width, oled_height))
            draw = ImageDraw.Draw(image)
            font = None
            actual_font_path = font_path or self.current_font_path

            if actual_font_path and os.path.exists(actual_font_path):
                try:
                    font = ImageFont.truetype(actual_font_path, font_size)
                except IOError:
                    print(f"警告：无法加载字体文件 {actual_font_path}，尝试默认字体。")

            if font is None:
                try:
                    fallback_font_path = self._find_font("Arial") or self._find_font("DejaVuSans") 
                    if fallback_font_path:
                        font = ImageFont.truetype(fallback_font_path, font_size)
                        print(f"信息：使用找到的回退字体: {fallback_font_path}")
                    else:
                        font = ImageFont.load_default() 
                        print("警告：未找到指定字体或 Arial/DejaVuSans，使用 Pillow 默认字体。")
                except IOError:
                    print("错误：无法加载默认字体或回退字体。")
                    draw.text((0, 0), "Font Error", fill=255)
                    return self._convert_image_to_oled_bytes(image)

            draw.rectangle((0, 0, oled_width, oled_height), outline=0, fill=0)
            draw.text((0, 0), text, font=font, fill=255) # 白色文本
            return self._convert_image_to_oled_bytes(image)
        except Exception as e:
            print(f"渲染文本时出错: {e}")
            QMessageBox.critical(self, "文本渲染错误", f"渲染文本时出错:\n{e}")
            return None

    # [--- 核心修改函数 V3 (添加 QInputDialog 和多策略) ---]
    def image_to_oled_bytes(self, image_path: str, oled_width=128, oled_height=64, method: str = "Dither") -> Optional[bytes]:
        """将图像文件转换为 SSD1306 的字节格式 (按页模式)，支持 SVG 和多种处理方法。"""
        if not _PILLOW_AVAILABLE:
            print("错误：尝试使用图像处理功能，但 Pillow 未加载。")
            return None
        try:
            
            img_to_process = None # 用于存储 Pillow Image 对象

            # --- 1. SVG 处理逻辑 ---
            if image_path.lower().endswith('.svg'):
                if not _CAIROSVG_AVAILABLE:
                    QMessageBox.critical(self, "依赖缺失", "无法加载 SVG 文件。\n请安装 'cairosvg' 库 (pip install cairosvg)。")
                    return None
                try:
                    png_data = cairosvg.svg2png(
                        url=image_path, 
                        output_width=oled_width, 
                        output_height=oled_height
                    )
                    img_to_process = Image.open(io.BytesIO(png_data))
                except Exception as e:
                    QMessageBox.critical(self, "SVG 处理错误", f"处理 SVG 文件时出错:\n{e}")
                    return None
            else:
                # 3. 如果不是 SVG，正常用 Pillow 打开
                img_to_process = Image.open(image_path)
            # --- SVG 处理逻辑结束 ---

            if img_to_process is None:
                raise ValueError("未能加载图像。")

            # --- 2. 获取算法常量 (兼容新旧 Pillow) ---
            if hasattr(Image, 'Resampling'):
                resample_algorithm = Image.Resampling.LANCZOS
            else:
                resample_algorithm = Image.LANCZOS

            if hasattr(Image, 'DITHER'): 
                dither_algorithm = Image.DITHER.FLOYDSTEINBERG
            elif hasattr(Image, 'FLOYDSTEINBERG'):
                dither_algorithm = Image.FLOYDSTEINBERG
            else:
                dither_algorithm = Image.NONE 

            # --- 3. 图像处理多策略 ---
            
            img_final = None # 最终的 1-bit 图像

            # 3.1 缩放 (如果需要)
            # (如果是 SVG，cairosvg 在第1步已经 resize 过了)
            if not image_path.lower().endswith('.svg'):
                img = img_to_process.resize((oled_width, oled_height), resample_algorithm)
            else:
                img = img_to_process # SVG 已经是正确尺寸

            # 3.2 应用选择的策略
            if method == "Dither (High Contrast)":
                # 策略一：高对比度 + 抖动
                img_gray = img.convert('L') # 转灰度
                img_enhanced = ImageOps.autocontrast(img_gray, cutoff=1) # 自动对比度 (cutoff=1% 效果更温和)
                img_final = img_enhanced.convert('1', dither=dither_algorithm) # 抖动
            
            elif method == "Edge Detect":
                # 策略二：边缘检测
                img_gray = img.convert('L') # 转灰度
                # 增强边缘，使其更粗
                img_edges = img_gray.filter(ImageFilter.FIND_EDGES)
                # img_edges = img_edges.filter(ImageFilter.MaxFilter(3)) # 可选：使边缘变粗
                # 直接将边缘图（白线黑底）转换为 1-bit
                img_final = img_edges.convert('1') 
            
            else: # 默认 "Dither"
                # 策略三：标准抖动
                # (img 可能是 RGBA 或 L，convert('1') 会自动处理)
                img_final = img.convert('1', dither=dither_algorithm)
            
            # --- 4. 转换为 OLED 字节 ---
            return self._convert_image_to_oled_bytes(img_final)
        
        except FileNotFoundError:
            QMessageBox.critical(self, "文件错误", f"找不到图像文件:\n{image_path}")
            return None
        except Exception as e:
            QMessageBox.critical(self, "图像处理错误", f"处理图像时出错:\n{e}")
            return None

    def select_font(self):
        font, ok = QFontDialog.getFont()
        if ok:
            font_info = QFontInfo(font)
            font_name = font_info.family()
            self.current_font_size = font_info.pointSize() if font_info.pointSize() > 0 else 10
            found_path = self._find_font(font_name)
            if found_path:
                self.current_font_path = found_path
                font_display_name = os.path.basename(found_path)
                self.font_label.setText(f"字体: {font_display_name}, 大小: {self.current_font_size}")
                print(f"选择字体: {font_name}, 大小: {self.current_font_size}, 路径: {self.current_font_path}")
            else:
                self.current_font_path = None
                self.font_label.setText(f"字体: {font_name} (未找到路径), 大小: {self.current_font_size}")
                QMessageBox.warning(self, "字体未找到", f"无法自动定位字体 '{font_name}' 的文件路径，将尝试使用默认字体。")

    def display_text_on_oled(self):
        if not _PILLOW_AVAILABLE:
            QMessageBox.critical(self, "错误", "Pillow 库未安装，无法显示文本。")
            return
        text_to_display = self.text_input.text()
        if not text_to_display:
            QMessageBox.warning(self, "输入错误", "请输入要显示的文本。")
            return
        text_bytes = self.text_to_oled_bytes(
            text_to_display,
            font_path=self.current_font_path,
            font_size=self.current_font_size
        )
        if text_bytes:
            self._update_slave_address()
            set_addr_commands = bytes([self.COLUMNADDR, 0, 127, self.PAGEADDR, 0, 7])
            if not self.send_oled_commands(set_addr_commands): return
            if self.send_oled_data(text_bytes):
                QMessageBox.information(self, "成功", "文本显示完成。")

    # [--- 核心修改函数 V3 (添加 QInputDialog) ---]
    def load_image_to_oled(self):
        if not _PILLOW_AVAILABLE:
            QMessageBox.critical(self, "错误", "Pillow 库未安装，无法显示图片。")
            return
            
        # 1. 选择文件 (支持 SVG)
        filePath, _ = QFileDialog.getOpenFileName(self, "选择图片文件", "", 
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.svg)")
            
        if not filePath: return
        
        # 2. [新增] 弹出对话框选择处理方法
        methods = ["Dither (标准)", "Dither (High Contrast)", "Edge Detect (线稿)"]
        method_choice, ok = QInputDialog.getItem(
            self, 
            "选择图像处理方法", 
            "请选择一种方法将图像转换为 1-bit：", 
            methods, 
            0, # 默认选中 "Dither (标准)"
            False # 不可编辑
        )
        
        if not ok: return # 用户取消

        # 3. 调用修改后的 image_to_oled_bytes 函数
        image_bytes = self.image_to_oled_bytes(filePath, method=method_choice) 
        
        if image_bytes:
            QMessageBox.information(self, "处理完成", f"图像已转换为 {len(image_bytes)} 字节数据，准备发送...")
            self._update_slave_address()
            set_addr_commands = bytes([self.COLUMNADDR, 0, 127, self.PAGEADDR, 0, 7])
            if not self.send_oled_commands(set_addr_commands): return
            if self.send_oled_data(image_bytes):
                QMessageBox.information(self, "成功", "图像数据显示完成。")

    def closeEvent(self, event):
        """当窗口关闭时，只是隐藏它而不是销毁"""
        self.hide()
        event.ignore()