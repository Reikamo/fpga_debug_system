# fpga_debug_system/utils.py

import struct
import time
import re
import socket # <--- 新增导入
from typing import List, Union, Optional
from PyQt5.QtCore import QDateTime
from PyQt5.QtGui import QColor

# --- [新] 从 main.py 移入此文件以解决循环导入 ---
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
# --- 结束 ---

def bytes_to_hex_string(data: bytes, separator: str = " ") -> str:
    """将字节数据转换为十六进制字符串"""
    return separator.join([f"{b:02X}" for b in data])

def hex_string_to_bytes(hex_str: str) -> bytes:
    """将十六进制字符串转换为字节数据"""
    # 移除空格和常见分隔符
    hex_str = re.sub(r'[\s,:-]', '', hex_str)
    
    # 移除0x前缀
    hex_str = re.sub(r'0[xX]', '', hex_str)
    
    # 确保偶数长度
    if len(hex_str) % 2:
        hex_str = '0' + hex_str # <--- [修复] 此处已添加正确缩进
        
    try:
        return bytes.fromhex(hex_str)
    except ValueError as e:
        raise ValueError(f"无效的十六进制字符串: {hex_str}")

def format_byte_size(size: int) -> str:
    """格式化字节大小"""
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
        
    if unit_index == 0:
        return f"{size} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"

def format_frequency(freq: float) -> str:
    """格式化频率显示"""
    if freq >= 1e9:
        return f"{freq/1e9:.2f} GHz"
    elif freq >= 1e6:
        return f"{freq/1e6:.2f} MHz"
    elif freq >= 1e3:
        return f"{freq/1e3:.2f} kHz"
    else:
        return f"{freq:.1f} Hz"

def format_time_duration(seconds: float) -> str:
    """格式化时间长度"""
    if seconds < 1:
        return f"{seconds*1000:.1f} ms"
    elif seconds < 60:
        return f"{seconds:.1f} s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.0f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"

def get_timestamp(format_type: str = "default") -> str:
    """获取格式化的时间戳"""
    now = QDateTime.currentDateTime()
    
    formats = {
        "default": "yyyy-MM-dd hh:mm:ss",
        "time_only": "hh:mm:ss",
        "date_only": "yyyy-MM-dd",
        "filename": "yyyyMMdd_hhmmss",
        "iso": "yyyy-MM-ddThh:mm:ss"
    }
    
    format_str = formats.get(format_type, formats["default"])
    return now.toString(format_str)

def validate_ip_address(ip: str) -> bool:
    """验证IP地址格式"""
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, ip):
        return False
        
    parts = ip.split('.')
    for part in parts:
        if not (0 <= int(part) <= 255):
            return False
    return True

def validate_port(port: Union[str, int]) -> bool:
    """验证端口号"""
    try:
        port_num = int(port)
        return 1 <= port_num <= 65535
    except (ValueError, TypeError):
        return False

def validate_hex_string(hex_str: str) -> bool:
    """验证十六进制字符串格式"""
    # 移除空格和分隔符
    clean_hex = re.sub(r'[\s,:-]', '', hex_str)
    clean_hex = re.sub(r'0[xX]', '', clean_hex)
    
    # 检查是否为有效的十六进制
    return re.match(r'^[0-9A-Fa-f]+$', clean_hex) is not None

def calculate_checksum(data: bytes, method: str = "sum") -> int:
    """计算校验和"""
    if method == "sum":
        return sum(data) & 0xFFFF
    elif method == "xor":
        checksum = 0
        for byte in data:
            checksum ^= byte
        return checksum
    elif method == "crc16":
        # 简单的CRC16实现
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc
    else:
        raise ValueError(f"不支持的校验方法: {method}")

def parse_value_with_unit(value_str: str) -> tuple:
    """解析带单位的数值"""
    # 匹配数值和单位
    pattern = r'^([\d.]+)\s*([a-zA-Z]*)$'
    match = re.match(pattern, value_str.strip())
    
    if not match:
        raise ValueError(f"无效的数值格式: {value_str}")
        
    value = float(match.group(1))
    unit = match.group(2).upper()
    
    return value, unit

def convert_frequency_to_hz(value: float, unit: str) -> float:
    """将频率转换为Hz"""
    unit = unit.upper()
    multipliers = {
        '': 1,
        'HZ': 1,
        'KHZ': 1e3,
        'MHZ': 1e6,
        'GHZ': 1e9
    }
    
    if unit not in multipliers:
        raise ValueError(f"不支持的频率单位: {unit}")
        
    return value * multipliers[unit]

def convert_voltage_to_mv(value: float, unit: str) -> int:
    """将电压转换为毫伏(mV)"""
    unit = unit.upper()
    multipliers = {
        'V': 1000,
        'MV': 1,
        'UV': 0.001
    }
    
    if unit not in multipliers:
        raise ValueError(f"不支持的电压单位: {unit}")
        
    return int(value * multipliers[unit])

def get_protocol_color(protocol: str) -> QColor:
    """获取协议对应的颜色"""
    colors = {
        'SPI': QColor(255, 255, 0),    # 黄色
        'I2C': QColor(0, 255, 0),      # 绿色
        'UART': QColor(0, 255, 255),   # 青色
        'CAN': QColor(255, 165, 0),    # 橙色
        'PWM': QColor(255, 0, 255),    # 紫色
    }
    return colors.get(protocol.upper(), QColor(255, 255, 255))

def generate_waveform_data(waveform_type: str, frequency: float, amplitude: float, 
                          phase: float, samples: int = 1000) -> List[float]:
    """生成波形数据"""
    import math
    
    data = []
    for i in range(samples):
        t = i / samples  # 归一化时间 (0-1)
        angle = 2 * math.pi * t + math.radians(phase)
        
        if waveform_type.lower() == 'sine':
            value = amplitude * math.sin(angle)
        elif waveform_type.lower() == 'square':
            value = amplitude if math.sin(angle) >= 0 else -amplitude
        elif waveform_type.lower() == 'triangle':
            # 三角波
            normalized_angle = (angle / (2 * math.pi)) % 1
            if normalized_angle < 0.5:
                value = amplitude * (4 * normalized_angle - 1)
            else:
                value = amplitude * (3 - 4 * normalized_angle)
        elif waveform_type.lower() == 'sawtooth':
            # 锯齿波
            normalized_angle = (angle / (2 * math.pi)) % 1
            value = amplitude * (2 * normalized_angle - 1)
        else:
            raise ValueError(f"不支持的波形类型: {waveform_type}")
            
        data.append(value)
    
    return data

def save_data_to_file(filename: str, data: Union[str, bytes], encoding: str = 'utf-8'):
    """保存数据到文件"""
    try:
        if isinstance(data, str):
            with open(filename, 'w', encoding=encoding) as f:
                f.write(data)
        else:
            with open(filename, 'wb') as f:
                f.write(data)
        return True
    except Exception as e:
        print(f"保存文件失败: {e}")
        return False

def load_data_from_file(filename: str, as_binary: bool = False) -> Optional[Union[str, bytes]]:
    """从文件加载数据"""
    try:
        if as_binary:
            with open(filename, 'rb') as f:
                return f.read()
        else:
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        print(f"加载文件失败: {e}")
        return None

def clamp_value(value: Union[int, float], min_val: Union[int, float], 
                max_val: Union[int, float]) -> Union[int, float]:
    """限制数值在指定范围内"""
    return max(min_val, min(value, max_val))

def lerp(start: float, end: float, t: float) -> float:
    """线性插值"""
    return start + (end - start) * clamp_value(t, 0.0, 1.0)

def moving_average(data: List[float], window_size: int) -> List[float]:
    """移动平均滤波"""
    if window_size <= 1:
        return data.copy()
        
    result = []
    for i in range(len(data)):
        start = max(0, i - window_size // 2)
        end = min(len(data), i + window_size // 2 + 1)
        window_data = data[start:end]
        result.append(sum(window_data) / len(window_data))
        
    return result

def detect_signal_edges(data: List[float], threshold: float) -> tuple:
    """检测信号边沿"""
    rising_edges = []
    falling_edges = []
    
    if len(data) < 2:
        return rising_edges, falling_edges
        
    prev_state = data[0] > threshold
    
    for i in range(1, len(data)):
        current_state = data[i] > threshold
        
        if current_state and not prev_state:
            rising_edges.append(i)
        elif not current_state and prev_state:
            falling_edges.append(i)
            
        prev_state = current_state
        
    return rising_edges, falling_edges

class DataBuffer:
    """循环数据缓冲区"""
    
    def __init__(self, max_size: int):
        self.max_size = max_size
        self.data = []
        self.write_pos = 0
        
    def append(self, item):
        """添加数据"""
        if len(self.data) < self.max_size:
            self.data.append(item)
        else:
            self.data[self.write_pos] = item
            self.write_pos = (self.write_pos + 1) % self.max_size
            
    def get_all(self) -> List:
        """获取所有数据（按时间顺序）"""
        if len(self.data) < self.max_size:
            return self.data.copy()
        else:
            return self.data[self.write_pos:] + self.data[:self.write_pos]
            
    def clear(self):
        """清空缓冲区"""
        self.data.clear()
        self.write_pos = 0
        
    def __len__(self):
        return len(self.data)