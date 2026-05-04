# serial_manager.py
import serial
import serial.tools.list_ports
import time
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
from communication_manager import CommunicationManager 
from protocol import PacketType

class SerialManager(QThread, CommunicationManager):
    session_changed = pyqtSignal(bool)
    # [修改点 1: 移除 data_received 信号，因为不再接收]
    # data_received = pyqtSignal(bytes, object) 
    log_message = pyqtSignal(str)

    _send_data_request = pyqtSignal(bytes)

    def __init__(self, parent=None):
        QThread.__init__(self, parent)
        CommunicationManager.__init__(self) 
        self.serial_port = None
        self.port_name = ""
        self.baud_rate = 115200
        
        self._send_data_request.connect(self._do_send_packet)

    @staticmethod
    def get_available_ports() -> list:
        ports = serial.tools.list_ports.comports()
        valid_ports = [port.device for port in ports if hasattr(port, 'device')] 
        return sorted(valid_ports) 

    def start_session(self, port_name: str, baud_rate: int = 115200, **kwargs) -> bool:
        if self.isRunning():
            self.log_message.emit("尝试启动新会话，正在停止旧会话...")
            self.stop_session() 
        self.port_name = port_name
        self.baud_rate = baud_rate
        self._is_running = True
        if not self.isRunning():
            self.start() 
            return True 
        else:
            self.log_message.emit("❌ 无法启动新串口会话：旧会话未能完全停止。")
            self._is_running = False
            return False

    def stop_session(self):
        if not self._is_running and not self.isRunning():
            return
        self._is_running = False 
        if self.isRunning():
            self.wait(2000) 
            if self.isRunning():
                self.log_message.emit("⚠️ 停止串口会话：线程未能正常结束。")

    def send_packet(self, packet_data: bytes) -> bool:
        """
        (GUI 线程) 
        请求一个数据包通过串口线程发送。
        """
        if not self._is_running:
            self.log_message.emit("❌ 串口发送失败: 会话未运行")
            return False
            
        self._send_data_request.emit(packet_data)
        return True

    @pyqtSlot(bytes)
    def _do_send_packet(self, packet_data: bytes):
        """
        (Serial QThread)
        实际将数据写入串口。
        这是执行阻塞 IO (write/flush/sleep) 的地方。
        """
        if not (self._is_running and self.serial_port and self.serial_port.is_open):
            if not self.serial_port or not self.serial_port.is_open:
                self.log_message.emit(f"❌ 串口发送失败: 串口 {self.port_name} 未打开")
            return

        try:
            # 1. (阻塞) 写入数据
            bytes_sent = self.serial_port.write(packet_data)
            
            # 2. 流控逻辑 (为I2C保留10ms延时)
            #    这个 sleep 会阻塞 Serial 线程，这正是我们想要的
            if packet_data and packet_data.startswith(bytes([PacketType.DEBUG_I2C_TRANSFER])):
                 self.serial_port.flush() 
                 time.sleep(0.010) # 延时 10ms

            # 3. 日志
            hex_data = ' '.join(f'{b:02X}' for b in packet_data)
            self.log_message.emit(f"📤 串口发送数据 ({bytes_sent}B 到 {self.port_name}): {hex_data}")

        except serial.SerialTimeoutException as e: 
            self.log_message.emit(f"❌ 串口发送超时: {e}")
        except serial.SerialException as e:
            self.log_message.emit(f"❌ 串口发送错误: {e}")
        except Exception as e:
            self.log_message.emit(f"❌ 未知串口发送错误: {e}")

    # --- [!! 关键修改: 彻底关闭接收 !!] ---
    def run(self):
        temp_serial_port = None
        port_name_for_log = self.port_name 
        port_was_open = False 
        try:
            # 打开串口 (不变)
            temp_serial_port = serial.Serial(
                port=self.port_name,
                baudrate=self.baud_rate,
                timeout=0.1 
            )
            if not temp_serial_port.is_open:
                 temp_serial_port.open()
            if not temp_serial_port.is_open:
                raise serial.SerialException(f"未能打开串口 {self.port_name}")
            self.serial_port = temp_serial_port 
            port_was_open = True 
            self.session_changed.emit(True) 
            self.log_message.emit(f"✅ 串口 {self.port_name} 已打开 (波特率: {self.baud_rate})")
        except serial.SerialException as e:
            # 错误处理 (不变)
            self.log_message.emit(f"❌ 打开串口 {self.port_name} 失败: {e}")
            self._is_running = False
            self.session_changed.emit(False) 
            self.serial_port = None
            if temp_serial_port:
                try: temp_serial_port.close()
                except: pass
            return 
        except Exception as e:
            # 错误处理 (不变)
            self.log_message.emit(f"❌ 初始化串口时发生未知错误: {e}")
            self._is_running = False
            self.session_changed.emit(False)
            self.serial_port = None
            return
            
        # [!! 关键修改 !!]
        # 这个线程现在是一个纯粹的 "发送任务处理器"。
        # 它不再尝试读取任何数据。
        while self._is_running:
            if not self.serial_port or not self.serial_port.is_open:
                if self._is_running: 
                     self.log_message.emit(f"❌ 串口 {port_name_for_log} 意外关闭。")
                break 
            
            try:
                # 线程唯一的任务就是休眠 (0.001s 或 1ms)，
                # 以便让Qt事件循环处理排队的 _send_data_request 信号。
                # 当 _do_send_packet 被调用时，它会接管这个线程，
                # (包括它自己的 10ms I2C 延时)，完成后返回到这里继续休眠。
                time.sleep(0.001)
            
            except Exception as e:
                 # 捕获可能的意外错误 (例如 time.sleep 被中断)
                 if self._is_running: 
                      self.log_message.emit(f"❌ 串口线程 'run' 循环出错: {e}")
                 break
        
        # 清理 (不变)
        if self.serial_port:
            try:
                 if self.serial_port.is_open:
                      self.serial_port.close()
            except Exception as e:
                 self.log_message.emit(f"关闭串口 {port_name_for_log} 时出错: {e}")
            self.serial_port = None
        if port_was_open:
            self._is_running = False 
            self.session_changed.emit(False)
        if port_was_open or 'temp_serial_port' in locals():
            self.log_message.emit(f"🔌 串口 {port_name_for_log} 已关闭。")