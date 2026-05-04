# communication_manager.py
# 移除 QObject, pyqtSignal, abc 的导入
# from PyQt5.QtCore import QObject, pyqtSignal
# from abc import ABC, abstractmethod

class CommunicationManager: # 不再继承 ABC 或 QObject
    """通信管理器的(概念性)基类"""
    # 移除信号定义

    def __init__(self): # 移除 parent
        self._is_running = False

    def is_running(self) -> bool:
        """检查会话是否正在运行"""
        return self._is_running

    # 移除 @abstractmethod, 但保留方法定义作为接口说明
    def start_session(self, **kwargs) -> bool:
        """启动通信会话，参数由子类定义"""
        # 子类必须实现此方法
        print(f"警告: {self.__class__.__name__}.start_session() 未实现")
        return False
        # raise NotImplementedError # 可以选择保留这个，但移除 ABC 后不是强制的

    # 移除 @abstractmethod
    def stop_session(self):
        """停止通信会话"""
        # 子类必须实现此方法
        print(f"警告: {self.__class__.__name__}.stop_session() 未实现")
        # raise NotImplementedError

    # 移除 @abstractmethod
    def send_packet(self, packet_data: bytes) -> bool:
        """发送数据包"""
        # 子类必须实现此方法
        print(f"警告: {self.__class__.__name__}.send_packet() 未实现")
        return False
        # raise NotImplementedError

    # run 方法可以移除，因为它将由 QThread 子类实现