# protocol.py
from enum import IntEnum
import struct
# [新] 导入 QSettings 来读取重写配置
try:
    from PyQt5.QtCore import QSettings
except ImportError:
    # 备用方案，以防在没有 PyQt 的环境（如 FPGA 端）导入此文件
    print("警告：无法导入 PyQt5.QtCore.QSettings。将仅使用默认包头。")
    QSettings = None

# 1. [修改] 将所有包头定义为标准的 Python 字典
DEFAULT_PACKET_HEADERS = {
    # 示波器
    "OSC_CONFIG_NEW": 0xF0,
    "OSC_ENABLE": 0xF1,
    "OSC_DATA": 0xAA,
    
    # 信号发生器
    "DDS_CONFIG": 0xE0,
    "DDS_OUTPUT_ENABLE": 0xE1,
    "DDS_HAND_DRAWN_CONFIG": 0xE2,
    "DDS_HAND_DRAWN_WAVEFORM": 0xE3,
    
    # 逻辑分析仪
    "LOGIC_ANALYZER_CONFIG": 0xF2,  
    "LOGIC_ANALYZER_CONTROL": 0xF3, 
    "LOGIC_ANALYZER_DATA": 0xAB,   
    "DEBUG_DIGITAL_FREQ_CONFIG": 0xDB, 
    "DEBUG_DIGITAL_FREQ_RESULT": 0xFF, 
    
    # FPGA调试器
    "DEBUG_SPI_CONFIG": 0xB0,
    "DEBUG_SPI_TRANSFER": 0xB1,
    "DEBUG_I2C_CONFIG": 0xA2,
    "DEBUG_I2C_TRANSFER": 0xA3,
    "DEBUG_UART_CONFIG": 0xA0,
    "DEBUG_UART_TRANSFER": 0xA1,
    "DEBUG_PWM_CONFIG": 0xC0,         
    "DEBUG_PWM_ENABLE": 0xC1,         
    "DEBUG_DO_CONFIG": 0xB2,       
    "DEBUG_DO_DATA": 0xB3,   
    "DEBUG_CAN_CONFIG": 0xA4,
    "DEBUG_CAN_TRANSFER": 0xA5,
    "DEBUG_CAN_RECV": 0xBC,      
    
    # FPGA -> PC
    "DEBUG_UART_RECV": 0xDD,
    "DEBUG_SPI_RECV": 0xCC,
    "DEBUG_I2C_RECV": 0xDF,
}

def load_packet_headers() -> dict:
    """
    加载包头定义。
    首先加载默认值，然后尝试从 QSettings 中加载用户重写的(overrides)值。
    """
    headers = DEFAULT_PACKET_HEADERS.copy()
    
    if QSettings: # 仅当 PyQt5 导入成功时
        try:
            settings = QSettings("MyCompany", "FPGADebugSystem")
            # 从设置中读取 "protocol_overrides" 字典
            overrides = settings.value("protocol_overrides", {})
            
            if isinstance(overrides, dict):
                for name, value_str in overrides.items():
                    if name in headers:
                        try:
                            # QSettings 保存的是字符串 "0xAB"，需要转回整数
                            headers[name] = int(str(value_str), 16) 
                        except ValueError:
                            print(f"警告: 无法解析 {name} 的重写值 '{value_str}'，使用默认值。")
            
        except Exception as e:
            print(f"警告: 加载协议包头重写失败: {e}")
            
    return headers

# 2. [修改] 动态创建 IntEnum
#    程序启动时，会调用 load_packet_headers() 来创建 PacketType
PacketType = IntEnum('PacketType', load_packet_headers())


# --- 用于构建有效载荷的辅助类 (保持不变) ---

class OscConfig:
    """旧的配置类，为保持兼容性暂时保留，但新逻辑不再使用"""
    FORMAT = '>IIHBHB'
    def __init__(self, sample_rate=100000000, buffer_size=1024, channel_mask=0x03, 
                 trigger_channel=0, trigger_level=0, trigger_edge=0):
        self.sample_rate=sample_rate; self.buffer_size=buffer_size; self.channel_mask=channel_mask
        self.trigger_channel=trigger_channel; self.trigger_level=trigger_level; self.trigger_edge=trigger_edge
    def pack(self):
        return struct.pack(self.FORMAT, self.sample_rate, self.buffer_size, self.channel_mask,
                          self.trigger_channel, self.trigger_level, self.trigger_edge)

class DDSConfig:
    """用于创建 DDS_CONFIG 有效载荷的辅助类"""
    FORMAT = '>BIIIB'
    def __init__(self, channel=0, frequency=1000, amplitude=1000, phase=0, waveform=0, enable=True):
        self.channel=channel; self.frequency=frequency; self.amplitude=amplitude
        self.phase=phase; self.waveform=waveform; self.enable=enable
    def pack(self):
        flags = (self.enable << 7) | (self.waveform & 0x0F)
        return struct.pack(self.FORMAT, self.channel, self.frequency, self.amplitude, self.phase, flags)