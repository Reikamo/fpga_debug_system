# collapsible_sidebar.py
import sys
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, 
                             QPushButton, QListWidgetItem, QStyle, QApplication,
                             QSizePolicy)
from PyQt5.QtCore import pyqtSignal, QSize, QPropertyAnimation, QEasingCurve, QEvent, Qt, pyqtSlot
from PyQt5.QtGui import QIcon

class CollapsibleNavWidget(QWidget):
    """
    一个可折叠的导航侧边栏，类似于 Windows 11 任务管理器。
    
    它会发出 currentRowChanged 信号，可以像 QListWidget 一样被连接。
    """
    
    currentRowChanged = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navigation_list") 
        self._is_collapsed = False
        
        # [!! 修改 !!] 宽度增加 60%
        self.expanded_width = 480  # (原为 300)
        self.collapsed_width = 128   # (原为 80)

        self.init_ui()
        self.connect_signals()
        
        self.setFixedWidth(self.expanded_width)
        self._update_item_display()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. 顶部切换按钮
        self.toggle_btn_container = QWidget()
        self.toggle_btn_container.setObjectName("nav_toggle_container")
        self.toggle_btn_container.setFixedHeight(112) # <--- [!! 修改 !!] 增大顶部按钮高度 (原 70)
        
        toggle_layout = QHBoxLayout(self.toggle_btn_container)
        toggle_layout.setContentsMargins(15, 15, 15, 15) # <--- [!! 修改 !!] 增大边距 (原 10)
        
        self.toggle_btn = QPushButton()
        self.toggle_btn.setObjectName("nav_toggle_button")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(self._is_collapsed)
        self.toggle_btn.setIcon(self.style().standardIcon(QStyle.SP_TitleBarMenuButton))
        self.toggle_btn.setText(" 菜单")
        self.toggle_btn.setIconSize(QSize(48, 48)) # <--- [!! 修改 !!] 增大图标 (原 30)
        self.toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.toggle_btn.setLayoutDirection(Qt.LeftToRight) 
        
        toggle_layout.addWidget(self.toggle_btn)
        
        self.main_layout.addWidget(self.toggle_btn_container)

        # 2. 列表控件
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("nav_list_widget") 
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setItemAlignment(Qt.AlignLeft | Qt.AlignVCenter) 
        self.list_widget.setIconSize(QSize(56, 56)) # <--- [!! 修改 !!] 增大列表项图标 (原 35)
        
        self.main_layout.addWidget(self.list_widget, 1)
        
        # 3. 动画 (宽度)
        self.animation = QPropertyAnimation(self, b"minimumWidth")
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        
        self.animation2 = QPropertyAnimation(self, b"maximumWidth")
        self.animation2.setDuration(200)
        self.animation2.setEasingCurve(QEasingCurve.InOutQuad)

    def connect_signals(self):
        self.toggle_btn.clicked.connect(self.toggle_collapse)
        self.list_widget.currentRowChanged.connect(self.currentRowChanged.emit)

    def addItem(self, icon: QIcon, text: str):
        """添加一个导航项"""
        item = QListWidgetItem(self.list_widget)
        item.setIcon(icon)
        item.setText(text)
        item.setSizeHint(QSize(96, 96)) # <--- [!! 修改 !!] 增大列表项高度 (原 60)
        item.setData(Qt.UserRole, text) # 存储完整文本
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def setCurrentRow(self, index: int):
        """设置当前选中的行"""
        self.list_widget.setCurrentRow(index)

    @pyqtSlot(bool)
    def toggle_collapse(self, checked: bool):
        self._is_collapsed = checked
        
        start_width = self.width()
        end_width = self.collapsed_width if self._is_collapsed else self.expanded_width
        
        # 更新按钮图标
        icon = QStyle.SP_TitleBarMenuButton if not self._is_collapsed else QStyle.SP_TitleBarCloseButton # 示例图标
        self.toggle_btn.setIcon(self.style().standardIcon(icon))

        # 启动动画
        self.animation.setStartValue(start_width)
        self.animation.setEndValue(end_width)
        
        self.animation2.setStartValue(start_width)
        self.animation2.setEndValue(end_width)
        
        self.animation.start()
        self.animation2.start()
        
        # 立即更新文本（动画开始时）
        self._update_item_display()

    def _update_item_display(self):
        """根据折叠状态更新列表项的显示"""
        self.toggle_btn.setText(" " if self._is_collapsed else " 菜单")
        
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if self._is_collapsed:
                item.setText("") # 隐藏文本
                item.setToolTip(item.data(Qt.UserRole)) # 鼠标悬停显示完整文本
            else:
                item.setText(item.data(Qt.UserRole)) # 恢复完整文本
                item.setToolTip("") # 移除提示