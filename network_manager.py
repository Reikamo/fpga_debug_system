# network_manager.py
import socket
import struct
import time
from PyQt5.QtCore import QThread, pyqtSignal # 保留导入
from protocol import PacketType
from communication_manager import CommunicationManager # 导入修改后的基类

# 继承 QThread 和 CommunicationManager (现在是 ABC)
class NetworkManager(QThread, CommunicationManager):
    """
    中央网络管理器, 使用UDP协议，在专用QThread中处理所有网络通信。
    采用独立的接收和发送Socket以确保线程安全。
    """
    # 在这里重新定义信号！
    session_changed = pyqtSignal(bool)
    data_received = pyqtSignal(bytes, object) # 使用 object 适应不同来源标识
    log_message = pyqtSignal(str)

    def __init__(self, parent=None):
        # 初始化 QThread (它包含 QObject)
        QThread.__init__(self, parent)
        # 初始化 CommunicationManager (现在是普通类)
        CommunicationManager.__init__(self) # 不再传递 parent

        self.recv_socket = None
        try:
             self.send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except OSError as e:
             # 现在 log_message 是 QThread 的一部分，应该可用
             self.log_message.emit(f"❌ 创建发送 Socket 失败: {e}")
             self.send_socket = None
             self._is_running = False # 确保初始状态正确

        self.target_address = None
        self.local_address = None

    # is_running 方法可以继续使用 CommunicationManager 的实现
    # def is_running(self):
    #      return self._is_running

    # 实现抽象方法 start_session
    def start_session(self, local_ip: str, local_port: int, target_ip: str, target_port: int, **kwargs) -> bool: # 添加返回类型注解
        if self.isRunning():
            # 增加日志提示
            self.log_message.emit("尝试启动新会话，正在停止旧会话...")
            self.stop_session() # 先停止旧会话并等待其结束
            # 增加短暂延时，确保旧线程资源完全释放 (可选，但有时有帮助)
            # self.msleep(100)

        self.local_address = (local_ip, local_port)
        self.target_address = (target_ip, target_port)
        self._is_running = True # 设置运行标志
        # 确保旧线程已结束后再启动新线程
        if not self.isRunning():
            self.start() # 启动 QThread 的 run 方法
            # 注意：成功启动不代表监听一定成功，run方法内会发 session_changed 信号
            return True # 表示尝试启动
        else:
            self.log_message.emit("❌ 无法启动新会话：旧会话未能完全停止。")
            self._is_running = False
            return False

    # 实现抽象方法 stop_session
    def stop_session(self):
        if not self._is_running and not self.isRunning(): # 如果本来就没运行，直接返回
            return

        self._is_running = False # 清除运行标志，run 循环会检测到
        # run 循环结束时会关闭 socket

        if self.isRunning():
            self.wait(2000) # 等待线程结束
            if self.isRunning(): # 如果等待后仍在运行
                 self.log_message.emit("⚠️ 停止会话：线程未能正常结束。")
                 # 强制退出线程 (如果 wait 超时) - 谨慎使用
                 # self.terminate()

    # 实现抽象方法 send_packet
    def send_packet(self, packet_data: bytes) -> bool:
        """
        发送一个已经构建好的完整数据包 (包头+载荷)。
        这个方法是线程安全的，可以在主线程中直接调用。
        """
        if not self._is_running or not self.target_address or not self.send_socket:
             # 如果未运行或目标地址/socket无效，也记录日志
             if not self._is_running:
                 self.log_message.emit("❌ UDP 发送失败: 会话未运行")
             elif not self.target_address:
                 self.log_message.emit("❌ UDP 发送失败: 目标地址未设置")
             elif not self.send_socket:
                 self.log_message.emit("❌ UDP 发送失败: 发送 Socket 无效")
             return False # 发送失败

        try:
            bytes_sent = self.send_socket.sendto(packet_data, self.target_address)
            # --- 添加发送成功日志 ---
            if bytes_sent > 0:
                 hex_data = ' '.join(f'{b:02X}' for b in packet_data)
                 # 可以在日志中包含目标地址
                 target_str = f"{self.target_address[0]}:{self.target_address[1]}"
                 self.log_message.emit(f"📤 UDP 发送 ({bytes_sent}B) 到 {target_str}: {hex_data}")
                 return True
            else:
                 # sendto 返回 0 通常不太可能，但也处理一下
                 self.log_message.emit("⚠️ UDP sendto 返回 0，可能未发送任何数据")
                 return False
            # ----------------------
        except socket.error as e:
            self.log_message.emit(f"❌ UDP 发送错误: {e}")
            return False
        except Exception as e:
             self.log_message.emit(f"❌ 未知 UDP 发送错误: {e}")
             return False

    # run 方法 (注意在成功监听后和线程结束前发出 session_changed 信号)
    def run(self):
        """后台线程，只负责接收数据"""
        temp_recv_socket = None
        session_started_successfully = False # <--- 标志位

        try:
            temp_recv_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            temp_recv_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            temp_recv_socket.settimeout(0.1)
            temp_recv_socket.bind(self.local_address)
            self.recv_socket = temp_recv_socket # 赋值给成员变量
            # 在成功绑定并准备开始循环之前发出 session_changed(True)
            self.session_changed.emit(True)
            session_started_successfully = True # <--- 标记成功
            self.log_message.emit(f"✅ UDP 监听已启动于 {self.local_address[0]}:{self.local_address[1]}")

        except Exception as e:
            self.log_message.emit(f"❌ 绑定本地 UDP 地址 {self.local_address[0]}:{self.local_address[1]} 失败: {e}")
            self._is_running = False
            self.session_changed.emit(False) # 明确发出失败信号
            if temp_recv_socket:
                 try: temp_recv_socket.close()
                 except OSError: pass
            self.recv_socket = None # 清理成员变量
            return # 线程结束

        while self._is_running: # run 循环条件
            if not self.recv_socket: # 双重检查
                break
            try:
                data, addr = self.recv_socket.recvfrom(65535)
                # 确保 target_address 存在再比较
                if data and self.target_address and addr[0] == self.target_address[0]:
                    self.data_received.emit(data, addr) # 发出数据信号
                # 可以选择性地记录来自非目标IP的数据
                # elif data and self.target_address:
                #     self.log_message.emit(f"⚠️ 收到来自非目标IP {addr[0]}:{addr[1]} 的UDP数据")

            except socket.timeout:
                continue # 超时正常
            except OSError as e: # 捕捉 socket 关闭等错误
                 if self._is_running: # 仅在预期运行时记录错误
                     self.log_message.emit(f"UDP 接收 OS 错误: {e}")
                 break # 退出循环
            except Exception as e:
                 if self._is_running: # 仅在预期运行时记录错误
                      self.log_message.emit(f"未知 UDP 接收错误: {e}")
                 break # 退出循环

        # 循环结束后清理资源
        if self.recv_socket:
             try:
                  self.recv_socket.close()
             except OSError: pass
             self.recv_socket = None

        # --- 修改点 ---
        # 确保线程结束时发出 session_changed(False)
        # 只有当会话之前成功启动过，才发送 False 信号
        if session_started_successfully:
            self._is_running = False # 确保内部状态同步
            self.session_changed.emit(False)
        # ----------------

        self.log_message.emit("🔌 UDP 监听已停止。")