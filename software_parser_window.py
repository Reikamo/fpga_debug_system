# software_parser_window.py
import sys
import numpy as np
import math
from typing import List, Dict, Tuple, Any
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout,
                             QHBoxLayout, QLabel, QDialog, QFormLayout,
                             QComboBox, QDialogButtonBox, QGroupBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
                             QMessageBox, QGridLayout)
from PyQt5.QtGui import (QFont, QFontMetrics, QPainter, QColor, QPen, 
                         QPainterPath, QBrush)
from PyQt5.QtCore import pyqtSignal, Qt, QRectF,QRect


#==================================================================
# 软件解析器逻辑
#==================================================================

class BaseParser:
    """协议解析器的基类"""
    def __init__(self, sample_rate_hz: float):
        if sample_rate_hz <= 0:
            raise ValueError("采样率必须大于 0")
        self.sample_rate_hz = sample_rate_hz
        self.period_s = 1.0 / sample_rate_hz
        self.results = [] 
        
        self.START_COLOR = QColor(0, 255, 0, 80) 
        self.STOP_COLOR = QColor(255, 0, 0, 80) 
        self.ADDR_COLOR = QColor(255, 165, 0, 80) # 截图中的棕色
        self.DATA_COLOR = QColor(0, 150, 255, 80) # 截图中的蓝色
        self.MOSI_COLOR = QColor(0, 150, 255, 80) # 蓝色 (MOSI)
        self.MISO_COLOR = QColor(0, 200, 150, 80) # 深绿色 (MISO)
        self.ACK_COLOR = QColor(0, 200, 0, 80) # 截图中的绿色
        self.NACK_COLOR = QColor(255, 0, 0, 80) # 红色
        self.ERROR_COLOR = QColor(255, 0, 255, 80) # 紫色 (用于错误/部分)
        self.IDLE_COLOR = QColor(100, 100, 100, 80) 

    def parse(self, channels: Dict[str, List[int]], **kwargs) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def format_time(self, sample_index: int) -> str:
        time_s = sample_index * self.period_s
        if time_s < 1e-6: return f"{time_s * 1e9:.2f} ns"
        elif time_s < 1e-3: return f"{time_s * 1e6:.2f} us"
        elif time_s < 1: return f"{time_s * 1e3:.2f} ms"
        else: return f"{time_s:.2f} s"

class I2CParser(BaseParser):
    """I2C 软件解析器"""
    
    def parse(self, channels: Dict[str, List[int]], 
                scl_ch_idx: int, sda_ch_idx: int) -> List[Dict[str, Any]]:
        
        self.results.clear()
        pending_block = None # [新] 存储块直到找到结束点
        is_write = False     # [新] 存储R/W状态
        
        scl_data = channels.get("SCL")
        sda_data = channels.get("SDA")

        if not scl_data or not sda_data or len(scl_data) != len(sda_data):
            self.results.append({"start_sample": 0, "end_sample": 100, 'channel_idx': sda_ch_idx,
                                 "text": "错误: SCL/SDA 数据缺失或长度不匹配", "color": self.ERROR_COLOR})
            return self.results

        state = "IDLE"
        bit_count = 0
        current_byte = 0
        current_start_sample = 0 # 记录每个字节/ACK的起始采样点
        data_len = len(scl_data)
        
        for i in range(1, data_len):
            scl, prev_scl = scl_data[i], scl_data[i-1]
            sda, prev_sda = sda_data[i], sda_data[i-1]

            # 1. Universal STOP condition (highest priority)
            if scl == 1 and (prev_sda == 0 and sda == 1):
                if pending_block: # [新] 刷新停止前的任何挂起块
                    self.results.append({
                        'end_sample': i, 'channel_idx': sda_ch_idx, **pending_block
                    })
                    pending_block = None
                
                if state != "IDLE":
                    self.results.append({
                        'start_sample': i - 2, 'end_sample': i + 2, 'channel_idx': sda_ch_idx,
                        'text': 'STOP', 'color': self.STOP_COLOR
                    })
                state = "IDLE"
                continue # Event handled

            # 2. Universal START condition
            if scl == 1 and (prev_sda == 1 and sda == 0):
                if pending_block: # [新] 刷新 RE-START 前的任何挂起块
                    self.results.append({
                        'end_sample': i, 'channel_idx': sda_ch_idx, **pending_block
                    })
                    pending_block = None

                state = "ADDRESS"
                bit_count = 0
                current_byte = 0
                self.results.append({
                    'start_sample': i - 2, 'end_sample': i + 2, 'channel_idx': sda_ch_idx,
                    'text': 'START', 'color': self.START_COLOR
                })
                continue # Event handled
                
            # 3. SCL falling edge (1 -> 0) - [修改点] 标记块的结束和下一个块的开始
            if scl == 0 and prev_scl == 1:
                if pending_block: # 如果一个块(DATA/ACK)正在挂起，这个下降沿就是它的结束点
                    self.results.append({
                        'end_sample': i, 'channel_idx': sda_ch_idx, **pending_block
                    })
                    pending_block = None
                
                # 这个下降沿也是下一个块的开始
                if state == "ADDRESS" and bit_count == 0:
                    current_start_sample = i # 地址字节从第一个SCL下降沿开始
                elif state == "DATA" and bit_count == 0:
                    current_start_sample = i # 数据字节从ACK后的SCL下降沿开始
                elif state == "ACK_ADDR" or state == "ACK_DATA":
                    current_start_sample = i # ACK位从第8个bit后的SCL下降沿开始

            # 4. SCL rising edge (0 -> 1) - [修改点] 仅采样和更新状态
            elif scl == 1 and prev_scl == 0:
                if state == "ADDRESS":
                    current_byte = (current_byte << 1) | sda
                    bit_count += 1
                    if bit_count == 8:
                        is_write = (current_byte & 1) == 0
                        addr = current_byte >> 1
                        text = f"A: 0x{addr:02X} ({'W' if is_write else 'R'})"
                        # [修改] 不立即
                        pending_block = {
                            'start_sample': current_start_sample,
                            'text': text, 'color': self.ADDR_COLOR
                        }
                        state = "ACK_ADDR"
                        bit_count = 0 # 为 ACK 重置
                
                elif state == "DATA":
                    current_byte = (current_byte << 1) | sda
                    bit_count += 1
                    if bit_count == 8:
                        text = f"D: 0x{current_byte:02X}"
                        # [修改] 不立即
                        pending_block = {
                            'start_sample': current_start_sample,
                            'text': text, 'color': self.DATA_COLOR
                        }
                        state = "ACK_DATA"
                        bit_count = 0 # 为 ACK 重置
                
                elif state == "ACK_ADDR" or state == "ACK_DATA":
                    ack_bit = sda
                    text = "ACK" if ack_bit == 0 else "NACK"
                    color = self.ACK_COLOR if ack_bit == 0 else self.NACK_COLOR
                    
                    # [修改] 不立即
                    pending_block = {
                        'start_sample': current_start_sample,
                        'text': text, 'color': color
                    }
                    
                    if ack_bit == 0: # If ACK
                        # 确定下一个状态是 DATA
                        state = "DATA"
                    else: # If NACK
                        state = "IDLE" # NACK -> STOP or RE-START
                        
                    current_byte = 0
                    bit_count = 0
        
        return self.results

class SPIParser(BaseParser):
    """SPI 软件解析器 (支持 4 种模式, 修复周期覆盖和CS竞争条件)"""
    def parse(self, channels: Dict[str, List[int]], 
                clk_ch_idx: int, mosi_ch_idx: int, miso_ch_idx: int, cs_ch_idx: int,
                cpol: int = 0, cpha: int = 0, # [新] 添加 CPOL/CPHA 参数
                **kwargs) -> List[Dict[str, Any]]:
        
        self.results.clear()

        clk_data = channels.get("CLK")
        mosi_data = channels.get("MOSI", [])
        miso_data = channels.get("MISO", [])
        cs_data = channels.get("CS", []) 

        # 检查关键通道
        if not clk_data: return []
        if not cs_data:
             self.results.append({"start_sample": 0, "end_sample": 100, 'channel_idx': clk_ch_idx,
                                 "text": "错误: SPI解析器需要 CS 通道", "color": self.ERROR_COLOR})
             return self.results
        
        data_len = len(clk_data)
        
        # 确定数据通道是否存在
        has_mosi = mosi_ch_idx != -1 and len(mosi_data) == data_len
        has_miso = miso_ch_idx != -1 and len(miso_data) == data_len
        if not has_mosi and not has_miso: return [] # 必须至少有一个数据通道

        # [新] 根据 CPOL 和 CPHA 确定采样边沿
        # Mode 0 (0,0): L->H (True)
        # Mode 1 (0,1): H->L (False)
        # Mode 2 (1,0): H->L (False)
        # Mode 3 (1,1): L->H (True)
        sample_on_rising_edge = (cpol == cpha)

        state = "IDLE"
        bit_count = 0
        mosi_byte = 0
        miso_byte = 0
        current_start_sample = 0 # 字节块的起始点 (第一个变化边沿)
        
        for i in range(1, data_len):
            cs, prev_cs = cs_data[i], cs_data[i-1]
            clk, prev_clk = clk_data[i], clk_data[i-1]

            # 边沿检测
            rising_edge = (prev_clk == 0 and clk == 1)
            falling_edge = (prev_clk == 1 and clk == 0)

            # [新] 根据模式确定边沿类型
            is_sampling_edge = (sample_on_rising_edge and rising_edge) or \
                               (not sample_on_rising_edge and falling_edge)
            
            is_change_edge = (not sample_on_rising_edge and rising_edge) or \
                               (sample_on_rising_edge and falling_edge)

            # --- [修改 V5: 重新排序逻辑以解决竞争条件] ---

            # 1. 检查时钟边沿 (仅在 DATA 状态下)
            if state == "DATA":
                if is_sampling_edge:
                    if bit_count < 8: # 确保只采8位
                        if has_mosi: mosi_byte = (mosi_byte << 1) | mosi_data[i]
                        if has_miso: miso_byte = (miso_byte << 1) | miso_data[i]
                        bit_count += 1
                
                elif is_change_edge:
                    if bit_count == 0: # 这是 CS 激活后的第一个 "变化" 边沿
                        current_start_sample = i
                    
                    elif bit_count == 8: # 这是第8个时钟的结束边沿
                        end_sample = i # 块在变化边沿结束
                        
                        if has_mosi:
                            self.results.append({
                                'start_sample': current_start_sample, 'end_sample': end_sample, 
                                'channel_idx': mosi_ch_idx, 
                                'text': f"0x{mosi_byte:02X}", 'color': self.MOSI_COLOR
                            })
                        if has_miso:
                            self.results.append({
                                'start_sample': current_start_sample, 'end_sample': end_sample, 
                                'channel_idx': miso_ch_idx, 
                                'text': f"0x{miso_byte:02X}", 'color': self.MISO_COLOR
                            })
                        
                        # 重置下一个字节
                        bit_count = 0
                        mosi_byte = 0
                        miso_byte = 0
                        current_start_sample = i # 下一个块从这个变化边沿开始

            # 2. 检查 CS 边沿 (如果时钟边沿没有被处理)
            # [修改 V5.1] CS 检查必须在时钟检查之外，因为CS可能与时钟同时变化
            
            # 2a. CS 下降沿 (启动)
            if state == "IDLE" and prev_cs == 1 and cs == 0: 
                state = "DATA"
                current_start_sample = i # 临时起始点
                bit_count = 0
                mosi_byte = 0
                miso_byte = 0
                
            # 2b. CS 上升沿 (停止)
            elif state == "DATA" and prev_cs == 0 and cs == 1: 
                # [修复] 如果 CS 提前拉高，正确处理 MOSI 和 MISO
                # [修改 V5.1] 仅在时钟边沿未处理时才执行
                if not is_sampling_edge and not is_change_edge:
                    if bit_count > 0:
                        if has_mosi:
                            self.results.append({
                                'start_sample': current_start_sample, 'end_sample': i, 
                                'channel_idx': mosi_ch_idx, 
                                'text': f"0x{mosi_byte:02X} (P)", 'color': self.ERROR_COLOR
                            })
                        if has_miso:
                             self.results.append({
                                'start_sample': current_start_sample, 'end_sample': i, 
                                'channel_idx': miso_ch_idx, 
                                'text': f"0x{miso_byte:02X} (P)", 'color': self.ERROR_COLOR
                            })
                
                # 无论如何，CS 上升沿都会重置状态
                state = "IDLE"
                bit_count = 0

        return self.results
        
class UARTParser(BaseParser):
    """UART 软件解析器 (V3 - 支持 LSB/MSB)"""
    def parse(self, channels: Dict[str, List[int]], 
                rx_ch_idx: int, baud_rate: int, 
                lsb_first: bool = True, # [!!] 新增参数，默认为 True (小端)
                **kwargs) -> List[Dict[str, Any]]:
        self.results.clear()
        rx_data = channels.get("RX")
        if not rx_data: return []

        if baud_rate <= 0:
            self.results.append({"start_sample": 0, "end_sample": 100, 'channel_idx': rx_ch_idx,
                                 "text": "错误: 波特率必须大于0", "color": self.ERROR_COLOR})
            return self.results

        try:
            # [修改 1] 使用浮点数进行精确计算
            samples_per_bit_float = self.sample_rate_hz / baud_rate
            # [修改 2] 使用 round 来计算半个比特的采样数
            half_bit_samples = int(round(samples_per_bit_float / 2))
            
            if samples_per_bit_float < 2: 
                raise ValueError(f"采样率 ({self.sample_rate_hz}Hz) 对于波特率 ({baud_rate}Bd) 过低")
        except Exception as e:
            self.results.append({"start_sample": 0, "end_sample": 100, 'channel_idx': rx_ch_idx,
                                 "text": f"错误: {e}", "color": self.ERROR_COLOR})
            return self.results

        data_len = len(rx_data)
        i = 0
        state = "IDLE" 

        while i < data_len:
            
            if state == "IDLE":
                # [修改 3] 增加 i < (data_len - 1) 边界检查
                if i < (data_len - 1) and rx_data[i] == 1 and rx_data[i+1] == 0:
                    start_bit_start_idx = i + 1 # 1->0 跳变点
                    
                    # 检查起始位的中心点
                    start_bit_center_idx = start_bit_start_idx + half_bit_samples
                    if start_bit_center_idx < data_len and rx_data[start_bit_center_idx] == 0:
                        # 确认是有效的起始位
                        state = "DATA"
                        current_start_sample = start_bit_start_idx # 帧的起始（用于高亮）
                        i = start_bit_center_idx # [!!] 将 i 设置为起始位的中心采样点
                    else:
                        i += 1 # 误报的起始位
                else:
                    i += 1 # 保持 IDLE
            
            # [修改 4] 重写 DATA 和 STOP 状态机
            elif state == "DATA":
                current_byte = 0
                try:
                    # i 是起始位的中心点
                    
                    # 循环读取 8 个数据位
                    for bit_count in range(8): # bit_count = 0..7
                        # 计算 D0, D1, ..., D7 的采样点
                        sample_idx = int(round(i + ((bit_count + 1) * samples_per_bit_float)))
                        
                        if sample_idx >= data_len: raise IndexError("数据不完整")
                        
                        bit_value = rx_data[sample_idx]
                        
                        # [!!] 根据大小端模式组装字节
                        if lsb_first:
                            # 标准 LSB (小端): D0 -> bit 0, D7 -> bit 7
                            current_byte |= (bit_value << bit_count)
                        else:
                            # MSB (大端): D0 (第一个bit) -> bit 7, D7 (第八个bit) -> bit 0
                            current_byte |= (bit_value << (7 - bit_count))
                    
                    # 检查停止位
                    stop_bit_sample_idx = int(round(i + (9 * samples_per_bit_float)))
                    if stop_bit_sample_idx >= data_len: raise IndexError("数据不完整")
                    
                    end_sample = stop_bit_sample_idx + half_bit_samples
                    
                    if rx_data[stop_bit_sample_idx] == 1:
                        # 成功: 停止位为高
                        text = f"0x{current_byte:02X}"
                        try:
                            char = chr(current_byte)
                            if char.isprintable(): text += f" ('{char}')"
                        except: pass
                        
                        self.results.append({'start_sample': current_start_sample, 'end_sample': end_sample, 
                                             'channel_idx': rx_ch_idx, 'text': text, 'color': self.DATA_COLOR})
                    else:
                        # 失败: 停止位为低
                        self.results.append({'start_sample': current_start_sample, 'end_sample': end_sample, 
                                             'channel_idx': rx_ch_idx, 'text': "E:STOP", 'color': self.ERROR_COLOR})
                    
                    i = end_sample 
                    state = "IDLE"

                except IndexError:
                    self.results.append({'start_sample': current_start_sample, 'end_sample': data_len-1, 
                                         'channel_idx': rx_ch_idx, 'text': "E:帧错误", 'color': self.ERROR_COLOR})
                    state = "IDLE"
                    i = data_len # 停止解析
            
            else:
                # 理论上不应该到这里
                i += 1 
                state = "IDLE"
                
        return self.results


#==================================================================
# 内部波形控件 (带叠加层)
#==================================================================

class _ParserWaveformWidget(QWidget):
    # (此部分代码与上一回复完全相同，保持不变)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.channels = 16 
        self.display_depth = 256 
        self.data = [[] for _ in range(self.channels)]
        self.display_names = [f"CH{15-i}" for i in range(self.channels)]
        self.setMinimumSize(800, 300) 
        self.offset = 0.0 
        self.zoom = 12.0 
        self.x_offset = 80.0 
        self._dragging_divider = False 
        self._divider_hit_margin = 5 
        self.cursor_enabled = False 
        self._dragging_waveform = False 
        self._last_mouse_x = 0 
        self.period = 20.0 
        self.unit = 'ns'
        self.overlays: List[Dict[str, Any]] = []

    def set_overlays(self, overlays: List[Dict[str, Any]]):
        self.overlays = overlays
        self.update() 

    def update_channel_names(self, selected_names: list):
        new_names = ["---"] * self.channels
        signals_low_to_high = list(reversed(selected_names))
        num_selected = len(signals_low_to_high)
        for i in range(min(num_selected, self.channels)):
            new_names_index = 15 - i
            new_names[new_names_index] = signals_low_to_high[i]
        self.display_names = new_names
        self.update() 

    def paintEvent(self, event):
        rect = self.rect()
        painter = QPainter(self)
        painter.fillRect(rect, Qt.black) 
        w, h = rect.width(), self.height()
        if self.channels <= 0: return 
        row_h = h / self.channels 
        int_x_offset = int(self.x_offset) 
        plot_area_width = w - int_x_offset 
        y_offset = 10 
        colors = [QColor(0, 255, 0, 127)] 
        painter.setPen(QPen(Qt.white)) 
        font = QFont("Consolas", 8) 
        painter.setFont(font)
        fm = QFontMetrics(font) 
        max_name_width = int_x_offset - 10 
        for row_index in range(self.channels): 
            y_base = int((row_index + 0.5) * row_h) + y_offset 
            painter.setPen(QPen(Qt.white)) 
            name_from_list = self.display_names[row_index] if row_index < len(self.display_names) else "---"
            label_text = f"CH{15-row_index}: {name_from_list}" 
            name_to_draw = fm.elidedText(label_text, Qt.ElideRight, max_name_width)
            painter.drawText(5, y_base + 4, name_to_draw) 
            data_index = 15 - row_index
            painter.setPen(QPen(colors[data_index % len(colors)], 2)) 
            if data_index < 0 or data_index >= len(self.data) or not self.data[data_index]:
                 continue 
            path = QPainterPath() 
            start_idx = max(0, int(self.offset - (int_x_offset / self.zoom if self.zoom > 1e-6 else 0)))
            end_idx = min(self.display_depth, int(self.offset + (plot_area_width / self.zoom if self.zoom > 1e-6 else self.display_depth)) + 2)
            current_channel_data = self.data[data_index]
            if start_idx >= end_idx or start_idx >= len(current_channel_data):
                 continue
            try:
                y_start = y_base - int(current_channel_data[start_idx] * (row_h * 0.4)) 
                x_start = int(int_x_offset + (start_idx - self.offset) * self.zoom)
                path.moveTo(x_start, y_start) 
                for idx in range(start_idx + 1, min(end_idx, len(current_channel_data))):
                    x = int(int_x_offset + (idx - self.offset) * self.zoom) 
                    val = current_channel_data[idx] 
                    prev_val = current_channel_data[idx-1] 
                    y_prev = y_base - int(prev_val * (row_h * 0.4)) 
                    y_curr = y_base - int(val * (row_h * 0.4)) 
                    if val != prev_val:
                        path.lineTo(x, y_prev)
                    path.lineTo(x, y_curr)
                painter.save() 
                clip_rect = QRect(int_x_offset, 0, plot_area_width, h)
                painter.setClipRect(clip_rect)
                painter.drawPath(path) 
                painter.restore() 
            except Exception as e:
                pass
        time_scale_step = 1 
        min_pixels_per_step = 10 
        if self.zoom < min_pixels_per_step:
            time_scale_step = int(np.ceil(min_pixels_per_step / self.zoom))
        grid_pen = QPen(QColor(180, 180, 180, 80)) 
        time_text_pen = QPen(QColor(180, 180, 180, 255)) 
        first_visible_idx = max(0, int(np.floor(self.offset)))
        last_visible_idx = min(self.display_depth, int(np.ceil(self.offset + plot_area_width / self.zoom if self.zoom > 1e-6 else self.display_depth)))
        start_grid_idx = int(np.ceil(first_visible_idx / time_scale_step)) * time_scale_step
        for i in range(start_grid_idx, last_visible_idx + 1, time_scale_step):
            x = int(int_x_offset + (i - self.offset) * self.zoom)
            if int_x_offset <= x <= w: 
                painter.setPen(grid_pen)
                painter.drawLine(x, 0, x, h - 10) 
                if self.zoom >= 3: 
                    painter.setPen(time_text_pen)
                    time_val = i * self.period
                    time_str = f"{time_val:.1f}{self.unit}" 
                    text_width = fm.width(time_str)
                    if self.zoom * time_scale_step > text_width * 1.5: 
                        painter.drawText(x - text_width // 2, h - 2, time_str) 
        painter.save()
        clip_rect = QRect(int_x_offset, 0, plot_area_width, h)
        painter.setClipRect(clip_rect)
        for overlay in self.overlays:
            start_sample = overlay.get('start_sample')
            end_sample = overlay.get('end_sample')
            data_index = overlay.get('channel_idx')
            text = overlay.get('text', '')
            color = overlay.get('color', QColor(255, 255, 0, 80)) 
            if start_sample is None or end_sample is None or data_index is None:
                continue
            row_index = 15 - data_index
            if not (0 <= row_index < self.channels):
                continue
            x_start = int(int_x_offset + (start_sample - self.offset) * self.zoom)
            x_end = int(int_x_offset + (end_sample - self.offset) * self.zoom)
            if x_end < int_x_offset or x_start > w:
                continue

            # --- [修改] 重叠绘制逻辑 ---
            y_base = int((row_index + 0.5) * row_h) + y_offset
            # 信号的高电平 Y 坐标 (波形的顶部)
            y_signal_top = y_base - int(row_h * 0.4)
            # 信号的低电平 Y 坐标 (波形的底部)
            y_signal_bottom = y_base
            # 信号的实际高度
            signal_height = y_signal_bottom - y_signal_top # (row_h * 0.4)
            # 将 y_top 设置为信号的顶部
            y_top = y_signal_top
            # 将 overlay_h 设置为信号的高度
            overlay_h = signal_height
            overlay_rect = QRectF(x_start, y_top, max(1.0, x_end - x_start), overlay_h) 
            # --- [修改结束] ---
            
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen) 
            painter.drawRect(overlay_rect)
            painter.setPen(QPen(Qt.white)) 
            painter.setFont(font) 
            if overlay_rect.width() > fm.width(text) + 4:
                 painter.drawText(overlay_rect, Qt.AlignCenter, text)
        painter.restore()
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.drawLine(int_x_offset, 0, int_x_offset, h)

    def wheelEvent(self, event):
        int_x_offset = int(self.x_offset)
        if event.pos().x() < int_x_offset: return
        delta = event.angleDelta().y() 
        factor = 1.2 if delta > 0 else (1/1.2) 
        old_zoom = self.zoom
        new_zoom = max(0.1, min(200.0, self.zoom * factor)) 
        if abs(new_zoom - old_zoom) < 1e-6: return 
        self.zoom = new_zoom
        mouse_x_in_plot = event.pos().x() - int_x_offset 
        if mouse_x_in_plot >= 0:
            mouse_offset_in_samples_before = mouse_x_in_plot / old_zoom if old_zoom > 1e-6 else 0
            mouse_offset_in_samples_after = mouse_x_in_plot / self.zoom if self.zoom > 1e-6 else 0
            self.offset += mouse_offset_in_samples_before - mouse_offset_in_samples_after
            view_width_samples = (self.width() - int_x_offset) / self.zoom if self.zoom > 1e-6 else self.display_depth
            max_offset = self.display_depth - view_width_samples
            self.offset = max(0, min(max_offset if max_offset > 0 else 0, self.offset))
        self.update() 
    def mousePressEvent(self, event):
        int_x_offset = int(self.x_offset)
        if event.button() == Qt.LeftButton and abs(event.pos().x() - int_x_offset) <= self._divider_hit_margin:
            self._dragging_divider = True
            self._last_mouse_x = event.pos().x()
            self.setCursor(Qt.SplitHCursor) 
        elif event.pos().x() >= int_x_offset:
            self._last_mouse_x = event.pos().x()
            if event.button() == Qt.RightButton:
                self.setCursor(Qt.ClosedHandCursor) 
                self._dragging_waveform = True
        else: 
            self._dragging_divider = False
            self._dragging_waveform = False
    def mouseMoveEvent(self, event):
        int_x_offset = int(self.x_offset)
        effective_zoom = max(1e-6, self.zoom) 
        if self._dragging_divider:
            dx = event.pos().x() - self._last_mouse_x 
            new_offset = self.x_offset + dx 
            self.x_offset = max(50.0, min(300.0, new_offset))
            self._last_mouse_x = event.pos().x()
            self.update()
        elif self._dragging_waveform:
            dx = event.x() - self._last_mouse_x
            self.offset -= dx / effective_zoom 
            view_width_samples = (self.width() - int_x_offset) / effective_zoom
            max_offset = self.display_depth - view_width_samples
            self.offset = max(0, min(max_offset if max_offset > 0 else 0, self.offset))
            self._last_mouse_x = event.x()
            self.update()
    def mouseReleaseEvent(self, event):
        if self._dragging_divider or self._dragging_waveform:
            self._dragging_divider = False
            self._dragging_waveform = False
            self.setCursor(Qt.ArrowCursor) 
    def update_data(self, new_data, new_depth):
        self.display_depth = max(1, new_depth) 
        while len(new_data) < self.channels: new_data.append([])
        self.data = new_data[:self.channels] 
        effective_zoom = max(1e-6, self.zoom)
        view_width_samples = (self.width() - self.x_offset) / effective_zoom
        max_offset = self.display_depth - view_width_samples
        self.offset = max(0, min(self.offset, max_offset if max_offset > 0 else 0))
        self.update()
    def clear_data(self):
        self.data = [[] for _ in range(self.channels)]
        self.update()
    def zoom_in(self):
        center_sample = self.offset + (self.width() - self.x_offset) / (2 * self.zoom) if self.zoom > 1e-6 else self.offset
        new_zoom = min(200.0, self.zoom * 1.2) 
        if abs(new_zoom - self.zoom) > 1e-6:
             self.offset = center_sample - (self.width() - self.x_offset) / (2 * new_zoom)
             self.zoom = new_zoom
             view_width_samples = (self.width() - self.x_offset) / self.zoom
             max_offset = self.display_depth - view_width_samples
             self.offset = max(0, min(self.offset, max_offset if max_offset > 0 else 0))
             self.update()
    def zoom_out(self):
        center_sample = self.offset + (self.width() - self.x_offset) / (2 * self.zoom) if self.zoom > 1e-6 else self.offset
        new_zoom = max(0.1, self.zoom / 1.2) 
        if abs(new_zoom - self.zoom) > 1e-6:
             self.offset = center_sample - (self.width() - self.x_offset) / (2 * new_zoom)
             self.zoom = new_zoom
             view_width_samples = (self.width() - self.x_offset) / self.zoom
             max_offset = self.display_depth - view_width_samples
             self.offset = max(0, min(self.offset, max_offset if max_offset > 0 else 0))
             self.update()
    def reset_offset(self):
        self.offset = 0
        self.zoom = 12 
        self.update()
    def set_period(self, period, unit_str):
        self.period = max(0, period) 
        self.unit = unit_str if unit_str else '?'
        self.update() 


#==================================================================
# 弹出窗口主类 (包含UI修改)
#==================================================================

class SoftwareParserWindow(QDialog):
    log_message = pyqtSignal(str) 

    def __init__(self, la_data: List[List[int]], 
                 la_channel_names: List[str], 
                 la_sample_freq_str: str, 
                 parent=None):
        super().__init__(parent)
        
        self.la_data = la_data
        self.active_signal_names_high_to_low = la_channel_names
        self.active_signal_names_low_to_high = list(reversed(self.active_signal_names_high_to_low))
        self.sample_freq_str = la_sample_freq_str
        
        if self.la_data and self.la_data[0]:
            self.data_depth = len(self.la_data[0])
        else:
            self.data_depth = 0
            
        self.setWindowFlags(
            self.windowFlags() | 
            Qt.WindowMinimizeButtonHint | 
            Qt.WindowMaximizeButtonHint
        )
            
        self.setWindowTitle("协议软件解析")
        self.setMinimumSize(900, 700) 
        self.init_ui()
        self.connect_signals()
        
        self.on_protocol_changed(self.parser_protocol_select.currentText())
        self.load_data_to_waveform()

    # --- [修改点 3: init_ui 添加新控件] ---
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        control_panel = QGroupBox("解析设置")
        control_layout = QGridLayout(control_panel)
        control_layout.addWidget(QLabel("协议类型:"), 0, 0)
        self.parser_protocol_select = QComboBox()
        self.parser_protocol_select.addItems(["-- 请选择 --", "I2C", "SPI", "UART"])
        control_layout.addWidget(self.parser_protocol_select, 0, 1)
        self.parser_start_btn = QPushButton("开始解析")
        control_layout.addWidget(self.parser_start_btn, 0, 4, Qt.AlignRight) 
        
        # --- I2C 行 (Row 1) ---
        self.parser_i2c_scl_label = QLabel("SCL 通道:")
        self.parser_i2c_scl_combo = QComboBox()
        self.parser_i2c_sda_label = QLabel("SDA 通道:")
        self.parser_i2c_sda_combo = QComboBox()
        control_layout.addWidget(self.parser_i2c_scl_label, 1, 0); control_layout.addWidget(self.parser_i2c_scl_combo, 1, 1)
        control_layout.addWidget(self.parser_i2c_sda_label, 1, 2); control_layout.addWidget(self.parser_i2c_sda_combo, 1, 3)
        
        # --- SPI 行 (Row 2, 3, 4) ---
        self.parser_spi_clk_label = QLabel("CLK 通道:")
        self.parser_spi_clk_combo = QComboBox()
        self.parser_spi_mosi_label = QLabel("MOSI 通道:")
        self.parser_spi_mosi_combo = QComboBox()
        self.parser_spi_miso_label = QLabel("MISO 通道:")
        self.parser_spi_miso_combo = QComboBox()
        self.parser_spi_cs_label = QLabel("CS 通道:")
        self.parser_spi_cs_combo = QComboBox()
        control_layout.addWidget(self.parser_spi_clk_label, 2, 0); control_layout.addWidget(self.parser_spi_clk_combo, 2, 1)
        control_layout.addWidget(self.parser_spi_mosi_label, 2, 2); control_layout.addWidget(self.parser_spi_mosi_combo, 2, 3)
        control_layout.addWidget(self.parser_spi_miso_label, 3, 0); control_layout.addWidget(self.parser_spi_miso_combo, 3, 1)
        control_layout.addWidget(self.parser_spi_cs_label, 3, 2); control_layout.addWidget(self.parser_spi_cs_combo, 3, 3)
        
        # [新] SPI 模式行 (Row 4)
        self.parser_spi_cpol_label = QLabel("CPOL:")
        self.parser_spi_cpol_combo = QComboBox()
        self.parser_spi_cpol_combo.addItems(["0 (Idle Low)", "1 (Idle High)"])
        self.parser_spi_cpha_label = QLabel("CPHA:")
        self.parser_spi_cpha_combo = QComboBox()
        self.parser_spi_cpha_combo.addItems(["0 (Sample 1st Edge)", "1 (Sample 2nd Edge)"])
        control_layout.addWidget(self.parser_spi_cpol_label, 4, 0); control_layout.addWidget(self.parser_spi_cpol_combo, 4, 1)
        control_layout.addWidget(self.parser_spi_cpha_label, 4, 2); control_layout.addWidget(self.parser_spi_cpha_combo, 4, 3)

        # --- UART 行 (Row 5, 6) ---
        self.parser_uart_rx_label = QLabel("RX 通道:")
        self.parser_uart_rx_combo = QComboBox()
        self.parser_uart_baud_label = QLabel("波特率:")
        self.parser_uart_baud_combo = QComboBox()
        self.parser_uart_baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "921600"])
        self.parser_uart_baud_combo.setCurrentText("115200")
        control_layout.addWidget(self.parser_uart_rx_label, 5, 0); control_layout.addWidget(self.parser_uart_rx_combo, 5, 1)
        control_layout.addWidget(self.parser_uart_baud_label, 5, 2); control_layout.addWidget(self.parser_uart_baud_combo, 5, 3)
        
        # [新] UART MOL 行 (Row 6)
        self.parser_uart_mol_label = QLabel("大小端(MOL):")
        self.parser_uart_mol_combo = QComboBox()
        self.parser_uart_mol_combo.addItems(["LSB First (小端)", "MSB First (大端)"])
        control_layout.addWidget(self.parser_uart_mol_label, 6, 0); control_layout.addWidget(self.parser_uart_mol_combo, 6, 1)
        
        control_layout.setColumnStretch(1, 1)
        control_layout.setColumnStretch(3, 1)
        main_layout.addWidget(control_panel)
        self.waveform_widget = _ParserWaveformWidget(self)
        main_layout.addWidget(self.waveform_widget, 1) 
        self.close_button = QDialogButtonBox(QDialogButtonBox.Close)
        main_layout.addWidget(self.close_button)

    def connect_signals(self):
        self.parser_protocol_select.currentTextChanged.connect(self.on_protocol_changed)
        self.parser_start_btn.clicked.connect(self.run_software_parser)
        self.close_button.rejected.connect(self.reject) 

    def update_la_data(self, la_data: List[List[int]], 
                       la_channel_names: List[str], 
                       la_sample_freq_str: str):
        """[新] 公共方法，用于从 LogicAnalyzerWidget 更新数据"""
        self.la_data = la_data
        self.active_signal_names_high_to_low = la_channel_names
        self.active_signal_names_low_to_high = list(reversed(self.active_signal_names_high_to_low))
        self.sample_freq_str = la_sample_freq_str
        
        if self.la_data and self.la_data[0]:
            self.data_depth = len(self.la_data[0])
        else:
            self.data_depth = 0
        
        # 重新加载UI和波形
        self.on_protocol_changed(self.parser_protocol_select.currentText())
        self.load_data_to_waveform()
        # 清除旧的解析结果
        self.waveform_widget.set_overlays([]) 

    def load_data_to_waveform(self):
        self.waveform_widget.update_channel_names(self.active_signal_names_high_to_low)
        self.waveform_widget.update_data(self.la_data, self.data_depth)
        try:
            freq_hz = self.freq_str_to_hz(self.sample_freq_str)
            if freq_hz <= 1e-9: 
                 period_s = 0; p_val, p_unit = 0, '?'
            else:
                period_s = 1.0 / freq_hz
                p_val, p_unit = period_s, 's' 
                if period_s < 1e-6: p_val, p_unit = period_s * 1e9, 'ns'
                elif period_s < 1e-3: p_val, p_unit = period_s * 1e6, 'us'
                elif period_s < 1: p_val, p_unit = period_s * 1e3, 'ms'
            self.waveform_widget.set_period(p_val, p_unit)
        except Exception as e:
            self.log_message.emit(f"解析器窗口设置时间刻度失败: {e}")

    # --- [修改点 4: on_protocol_changed 隐藏/显示新控件] ---
    def on_protocol_changed(self, protocol: str):
        # 隐藏所有
        self.parser_i2c_scl_label.hide(); self.parser_i2c_scl_combo.hide()
        self.parser_i2c_sda_label.hide(); self.parser_i2c_sda_combo.hide()
        self.parser_spi_clk_label.hide(); self.parser_spi_clk_combo.hide()
        self.parser_spi_mosi_label.hide(); self.parser_spi_mosi_combo.hide()
        self.parser_spi_miso_label.hide(); self.parser_spi_miso_combo.hide()
        self.parser_spi_cs_label.hide(); self.parser_spi_cs_combo.hide()
        self.parser_spi_cpol_label.hide(); self.parser_spi_cpol_combo.hide() # [新] 隐藏
        self.parser_spi_cpha_label.hide(); self.parser_spi_cpha_combo.hide() # [新] 隐藏
        self.parser_uart_rx_label.hide(); self.parser_uart_rx_combo.hide()
        self.parser_uart_baud_label.hide(); self.parser_uart_baud_combo.hide()
        self.parser_uart_mol_label.hide(); self.parser_uart_mol_combo.hide() # [新] 隐藏
        self.waveform_widget.set_overlays([]) 

        channel_names = ["-- 未分配 --"] + self.active_signal_names_high_to_low
        
        if protocol == "I2C":
            self.parser_i2c_scl_label.show(); self.parser_i2c_scl_combo.show()
            self.parser_i2c_sda_label.show(); self.parser_i2c_sda_combo.show()
            self.parser_i2c_scl_combo.clear(); self.parser_i2c_scl_combo.addItems(channel_names)
            self.parser_i2c_sda_combo.clear(); self.parser_i2c_sda_combo.addItems(channel_names)
            for i, name in enumerate(self.active_signal_names_high_to_low):
                if "scl" in name.lower(): self.parser_i2c_scl_combo.setCurrentIndex(i + 1)
                if "sda" in name.lower(): self.parser_i2c_sda_combo.setCurrentIndex(i + 1)
        
        elif protocol == "SPI":
            self.parser_spi_clk_label.show(); self.parser_spi_clk_combo.show()
            self.parser_spi_mosi_label.show(); self.parser_spi_mosi_combo.show()
            self.parser_spi_miso_label.show(); self.parser_spi_miso_combo.show()
            self.parser_spi_cs_label.show(); self.parser_spi_cs_combo.show()
            self.parser_spi_cpol_label.show(); self.parser_spi_cpol_combo.show() # [新] 显示
            self.parser_spi_cpha_label.show(); self.parser_spi_cpha_combo.show() # [新] 显示
            
            self.parser_spi_clk_combo.clear(); self.parser_spi_clk_combo.addItems(channel_names)
            self.parser_spi_mosi_combo.clear(); self.parser_spi_mosi_combo.addItems(channel_names)
            self.parser_spi_miso_combo.clear(); self.parser_spi_miso_combo.addItems(channel_names)
            self.parser_spi_cs_combo.clear(); self.parser_spi_cs_combo.addItems(channel_names)
            for i, name in enumerate(self.active_signal_names_high_to_low):
                if "clk" in name.lower() or "sck" in name.lower(): self.parser_spi_clk_combo.setCurrentIndex(i + 1)
                if "mosi" in name.lower() or "sdi" in name.lower(): self.parser_spi_mosi_combo.setCurrentIndex(i + 1)
                if "miso" in name.lower() or "sdo" in name.lower(): self.parser_spi_miso_combo.setCurrentIndex(i + 1)
                if "cs" in name.lower() or "nss" in name.lower(): self.parser_spi_cs_combo.setCurrentIndex(i + 1)

        elif protocol == "UART":
            self.parser_uart_rx_label.show(); self.parser_uart_rx_combo.show()
            self.parser_uart_baud_label.show(); self.parser_uart_baud_combo.show()
            self.parser_uart_mol_label.show(); self.parser_uart_mol_combo.show() # [新] 显示
            self.parser_uart_rx_combo.clear(); self.parser_uart_rx_combo.addItems(channel_names)
            for i, name in enumerate(self.active_signal_names_high_to_low):
                if "rx" in name.lower() or "uart" in name.lower(): self.parser_uart_rx_combo.setCurrentIndex(i + 1)
            
    def freq_str_to_hz(self, freq_str: str) -> float:
        value_str = ''.join(filter(lambda x: x.isdigit() or x=='.', freq_str))
        unit_str = ''.join(filter(str.isalpha, freq_str)).lower()
        if value_str:
            value = float(value_str)
            if 'k' in unit_str: value *= 1e3
            elif 'm' in unit_str: value *= 1e6
            return value
        return 0

    # --- [修改点 5: run_software_parser 传递新参数] ---
    def run_software_parser(self):
        """执行软件协议解析 (已修复I2C/SPI/UART的data_index查找)"""
        self.waveform_widget.set_overlays([]) 
            
        try:
            freq_hz = self.freq_str_to_hz(self.sample_freq_str)
            if freq_hz <= 0: raise ValueError("频率必须大于0")
        except Exception as e:
            self.log_message.emit(f"⚠️ 协议解析失败：无效的采样率设置。{e}")
            QMessageBox.warning(self, "错误", f"无效的采样率: {self.sample_freq_str}")
            return

        protocol = self.parser_protocol_select.currentText()
        channels_to_parse = {} 
        parser_instance = None
        results = []
        kwargs = {} 
        
        try:
            if protocol == "I2C":
                scl_name = self.parser_i2c_scl_combo.currentText()
                sda_name = self.parser_i2c_sda_combo.currentText()
                if scl_name == "-- 未分配 --" or sda_name == "-- 未分配 --":
                    raise ValueError("I2C SCL 或 SDA 通道未分配")
                
                scl_data_idx = self.active_signal_names_low_to_high.index(scl_name)
                sda_data_idx = self.active_signal_names_low_to_high.index(sda_name)
                
                channels_to_parse["SCL"] = self.la_data[scl_data_idx]
                channels_to_parse["SDA"] = self.la_data[sda_data_idx]
                
                parser_instance = I2CParser(freq_hz)
                kwargs = {'scl_ch_idx': scl_data_idx, 'sda_ch_idx': sda_data_idx}

            elif protocol == "SPI":
                clk_name = self.parser_spi_clk_combo.currentText()
                if clk_name == "-- 未分配 --": raise ValueError("SPI CLK 通道未分配")
                
                clk_data_idx = self.active_signal_names_low_to_high.index(clk_name)
                channels_to_parse["CLK"] = self.la_data[clk_data_idx]
                kwargs['clk_ch_idx'] = clk_data_idx
                kwargs['mosi_ch_idx'] = -1 
                kwargs['miso_ch_idx'] = -1
                kwargs['cs_ch_idx'] = -1
                
                mosi_name = self.parser_spi_mosi_combo.currentText()
                if mosi_name != "-- 未分配 --":
                    mosi_data_idx = self.active_signal_names_low_to_high.index(mosi_name)
                    channels_to_parse["MOSI"] = self.la_data[mosi_data_idx]
                    kwargs['mosi_ch_idx'] = mosi_data_idx
                
                miso_name = self.parser_spi_miso_combo.currentText()
                if miso_name != "-- 未分配 --":
                    miso_data_idx = self.active_signal_names_low_to_high.index(miso_name)
                    channels_to_parse["MISO"] = self.la_data[miso_data_idx]
                    kwargs['miso_ch_idx'] = miso_data_idx

                cs_name = self.parser_spi_cs_combo.currentText()
                if cs_name != "-- 未分配 --":
                    cs_data_idx = self.active_signal_names_low_to_high.index(cs_name)
                    channels_to_parse["CS"] = self.la_data[cs_data_idx]
                    kwargs['cs_ch_idx'] = cs_data_idx

                # [新] 传递 CPOL 和 CPHA
                kwargs['cpol'] = self.parser_spi_cpol_combo.currentIndex()
                kwargs['cpha'] = self.parser_spi_cpha_combo.currentIndex()

                parser_instance = SPIParser(freq_hz)

            elif protocol == "UART":
                rx_name = self.parser_uart_rx_combo.currentText()
                baud_str = self.parser_uart_baud_combo.currentText()
                if rx_name == "-- 未分配 --": raise ValueError("UART RX 通道未分配")
                
                rx_data_idx = self.active_signal_names_low_to_high.index(rx_name)
                channels_to_parse["RX"] = self.la_data[rx_data_idx]
                kwargs['rx_ch_idx'] = rx_data_idx
                
                try:
                    kwargs['baud_rate'] = int(baud_str)
                except:
                    raise ValueError(f"无效的波特率: {baud_str}")

                # [新] 传递 LSB/MSB
                # 0 = LSB First (True), 1 = MSB First (False)
                kwargs['lsb_first'] = (self.parser_uart_mol_combo.currentIndex() == 0)

                parser_instance = UARTParser(freq_hz)
            
            else:
                self.log_message.emit(f"⚠️ 请先选择一个协议类型进行解析。")
                QMessageBox.warning(self, "提示", "请先选择一个协议类型进行解析。")
                return

        except (IndexError, ValueError) as e:
             msg = f"协议解析失败：通道映射错误或参数无效。 {e}"
             self.log_message.emit(f"⚠️ {msg}")
             QMessageBox.warning(self, "错误", msg)
             return
        except Exception as e:
            msg = f"解析器设置错误: {e}"
            self.log_message.emit(f"⚠️ {msg}")
            QMessageBox.warning(self, "错误", msg)
            return
            
        try:
            self.log_message.emit(f"▶️ 开始使用 {protocol} (软件) 解析器...")
            results = parser_instance.parse(channels_to_parse, **kwargs)
            
            self.waveform_widget.set_overlays(results)
            self.log_message.emit(f"✅ {protocol} 解析完成，共 {len(results)} 条结果。")

        except Exception as e:
            self.log_message.emit(f"❌ {protocol} 解析失败: {e}")
            QMessageBox.critical(self, "解析运行时错误", f"{protocol} 解析器运行时发生错误:\n{e}")