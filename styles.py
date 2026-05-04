"""
优化的界面样式定义文件
现代化浅色/深色主题设计
"""

def get_dark_theme() -> str:
    """获取现代化深色主题样式 (字体也调整为 25px)"""
    return """
    /* 主窗口样式 */
    QMainWindow {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                   stop:0 #1e1e2e, stop:1 #2a2a3e);
        color: #ffffff;
        font-family: 'Microsoft YaHei UI', 'Segoe UI', Arial, sans-serif;
        font-size: 25px; /* <--- 修改 */
    }
    
    /* 通用控件样式 */
    QWidget {
        background-color: #f0f2f5; /* [!! 修改 !!] 修复弹窗深色背景 */
        color: #ffffff;
        font-family: 'Microsoft YaHei UI', 'Segoe UI', Arial, sans-serif;
        font-size: 25px; /* <--- 修改 */
    }

    /* --- [!! 关键布局 (深色) !!] --- */
    QWidget#connection_bar {
        background-color: #2a2a3e;
        border-bottom: 1px solid #3c3c54;
    }
    QStackedWidget#main_stack {
        background-color: #1e1e2e;
    }
    #main_stack > QWidget {
        background-color: #1e1e2e;
    }
    QStackedWidget#settings_stack {
        background-color: #2a2a3e;
        border-left: 1px solid #3c3c54;
    }
    #settings_stack > QWidget {
        background-color: #2a2a3e;
    }
    QGroupBox#log_widget {
        background-color: #2a2a3e;
        border-top: 1px solid #3c3c54;
        border-radius: 0px; margin: 0px; padding-top: 20px;
    }
    
    /* [!! 修改 !!] 可伸缩侧边栏 (深色) */
    QWidget#navigation_list {
        background-color: #2a2a3e; /* 深色背景 */
        border-right: 1px solid #3c3c54;
    }
    QWidget#nav_toggle_container {
        border-bottom: 1px solid #3c3c54;
    }
    QPushButton#nav_toggle_button {
        background-color: transparent;
        color: #ffffff;
        border: none;
        font-size: 26px; /* <--- 修改 */
        font-weight: 600;
        text-align: left;
        padding: 0px 15px; /* <--- 修改 */
    }
    QPushButton#nav_toggle_button:hover {
        background-color: #3c3c54;
    }
    QListWidget#nav_list_widget {
        background-color: #2a2a3e;
        border: none;
        font-size: 26px; /* <--- 修改 */
        font-weight: 600;
        padding-top: 10px;
    }
    QListWidget#nav_list_widget::item {
        padding: 18px 20px; /* <--- 修改 (增大垂直内边距以居中) */
        border-radius: 6px;
        margin: 2px 8px;
        color: #b8b8d4; 
    }
    QListWidget#nav_list_widget::item:hover {
        background-color: #3c3c54; 
    }
    QListWidget#nav_list_widget::item:selected {
        background-color: #4a9eff; 
        color: #ffffff; 
    }
    
    /* ... (其他所有深色主题样式保持不变) ... */
    
    QTabBar::tab { font-size: 25px; }
    QGroupBox::title { font-size: 26px; }
    QPushButton { font-size: 25px; }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { font-size: 25px; }
    QCheckBox, QRadioButton { font-size: 25px; }
    QTextEdit { font-size: 25px; }
    QTableWidget { font-size: 25px; }
    QHeaderView::section { font-size: 25px; }
    QStatusBar { font-size: 25px; }
    QLabel { font-size: 25px; }
    QMenuBar { font-size: 25px; }

    .PlotWidget {
        background-color: #1e1e2e;
        border: 1px solid #3c3c54;
        border-radius: 8px;
    }
    """

# ===================================================================
# [!! 重大修改 !!] 浅色主题 (Light Theme v9 - 25px 字体 + 侧边栏修复)
# ===================================================================
def get_light_theme() -> str:
    """获取现代化浅色主题样式 (优化版 v9 - 25px 字体 + 侧边栏修复)"""
    return """
    /* 1. 全局背景为浅灰 */
    QMainWindow, QDialog {
        background-color: #f0f2f5; 
        color: #212529;
        font-family: 'Microsoft YaHei UI', 'Segoe UI', Arial, sans-serif;
        font-size: 25px; /* <--- 修改 */
    }
    
    /* 2. 默认QWidget背景为浅灰 */
    QWidget {
        background-color: #f0f2f5; 
        color: #212529;
        font-family: 'Microsoft YaHei UI', 'Segoe UI', Arial, sans-serif;
        font-size: 25px; /* <--- 修改 */
    }
    
    /* --- [!! 关键布局 !!] --- */

    /* 3. 顶部栏: 灰色背景 */
    QWidget#connection_bar {
        background-color: #f8f9fa;
        border-bottom: 1px solid #dee2e6;
    }
    
    /* 5. 中间主堆栈: 强制为白色背景 */
    QStackedWidget#main_stack {
        background-color: #ffffff;
    }
    #main_stack > QWidget {
        background-color: #ffffff;
    }

    /* 6. 右侧配置堆栈: 灰色背景 */
    QStackedWidget#settings_stack {
        background-color: #f8f9fa;
        border-left: 1px solid #dee2e6;
    }
    #settings_stack > QWidget {
        background-color: #f8f9fa;
    }

    /* 7. 底部日志区域: 灰色背景 */
    QGroupBox#log_widget {
        background-color: #f8f9fa;
        border-top: 1px solid #dee2e6;
        border-radius: 0px;
        margin: 0px;
        padding-top: 20px;
    }
    
    /* --- [!! 修改 !!] 可伸缩侧边栏 (浅色) --- */
    
    /* 7. 左侧导航栏 (主容器) */
    QWidget#navigation_list {
        background-color: #f8f9fa; 
        border-right: 1px solid #dee2e6;
    }
    
    /* 8. 顶部 "菜单" 按钮容器 */
    QWidget#nav_toggle_container {
        background-color: #f8f9fa;
        border-bottom: 1px solid #dee2e6;
    }

    /* 9. 顶部 "菜单" 按钮 */
    QPushButton#nav_toggle_button {
        background-color: transparent;
        color: #212529;
        border: none;
        font-size: 26px; /* <--- 修改 */
        font-weight: 600;
        text-align: left;
        padding: 0px 15px; /* <--- 修改 */
    }
    QPushButton#nav_toggle_button:hover {
        background-color: #e9ecef;
    }
    QPushButton#nav_toggle_button:checked {
        background-color: #e0e0e0;
    }

    /* 10. 内部的 QListWidget */
    QListWidget#nav_list_widget {
        background-color: #f8f9fa; 
        border: none; 
        font-size: 26px; /* <--- 修改 */
        font-weight: 600;
        padding-top: 10px;
    }
    
    /* 11. 导航项 */
    QListWidget#nav_list_widget::item {
        padding: 18px 20px; /* <--- 修改 (增大垂直内边距以居中) */
        border-radius: 6px;
        margin: 2px 8px;
        color: #495057; 
    }
    QListWidget#nav_list_widget::item:hover {
        background-color: #e9ecef; 
    }
    QListWidget#nav_list_widget::item:selected {
        background-color: #007bff; 
        color: #ffffff; 
    }
    
    /* --- [!! 控件样式 (字体增大) !!] --- */
    
    /* 标签页 (用于 FPGA 调试器 - 在白色背景上) */
    QTabWidget::pane {
        border: none; 
        background: #ffffff; 
        border-top: 1px solid #dee2e6;
        padding: 8px;
    }
    QTabBar {
        background-color: #ffffff; 
    }
    QTabBar::tab {
        background: #f8f9fa; 
        color: #495057;
        padding: 10px 20px;
        margin-right: 2px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-weight: 600;
        min-width: 100px;
        border: 1px solid #dee2e6;
        border-bottom: none; 
        font-size: 25px; /* <--- 修改 */
    }
    QTabBar::tab:selected {
        background: #ffffff; 
        color: #007bff; 
        border-bottom: 1px solid #ffffff; 
        margin-bottom: -1px; 
    }
    QTabBar::tab:hover:!selected {
        background: #e9ecef;
    }
    
    /* 分组框 (用于参数配置) */
    QGroupBox {
        font-weight: 600;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        margin: 10px;
        padding: 15px;
        padding-top: 25px;
        background: transparent; 
    }
    
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        top: 8px;
        padding: 2px 8px;
        color: #495057;
        font-size: 26px; /* <--- 修改 */
        font-weight: 700;
        background: transparent; 
        border: none;
    }
    
    /* 按钮样式 (保留蓝色) */
    QPushButton {
        background-color: #007bff;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 25px; /* <--- 修改 */
        min-height: 20px;
        min-width: 80px;
    }
    QPushButton:hover { background-color: #0056b3; }
    QPushButton:pressed { background-color: #004085; }
    QPushButton:disabled { background-color: #ced4da; color: #6c757d; }
    QPushButton:checked {
        background-color: #28a745; 
        border: 1px solid #1e7e34;
    }
    
    /* 输入框样式 (标准浅色) */
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background: #ffffff;
        border: 1px solid #ced4da;
        padding: 8px 12px;
        border-radius: 6px;
        color: #495057;
        font-size: 25px; /* <--- 修改 */
        selection-background-color: #007bff;
        selection-color: #ffffff;
    }
    
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
        border: 1px solid #007bff; 
    }
    
    QLineEdit:read-only {
        background: #e9ecef;
        color: #495057;
        border: 1px solid #ced4da;
    }
    
    /* 下拉框 */
    QComboBox QAbstractItemView {
        background: #ffffff;
        border: 1px solid #007bff;
        border-radius: 6px;
        selection-background-color: #007bff;
        selection-color: #ffffff;
        color: #495057;
    }
    
    /* 复选框/单选按钮 */
    QCheckBox, QRadioButton {
        spacing: 8px;
        font-weight: 500;
        color: #495057;
        font-size: 25px; /* <--- 修改 */
    }
    QCheckBox::indicator:checked {
        background-color: #007bff;
        border: 1px solid #007bff;
    }
    QRadioButton::indicator:checked {
        background-color: #007bff;
        border: 1px solid #007bff;
    }
    
    /* 文本编辑框 (日志) */
    QTextEdit {
        background: #ffffff; 
        border: 1px solid #dee2e6;
        border-radius: 8px;
        color: #212529;
        font-family: 'Courier New', 'Consolas', monospace;
        font-size: 25px; /* <--- 修改 */
    }
    QTextEdit:read-only {
        background: #f8f9fa; 
    }
    
    /* 表格 */
    QTableWidget {
        background: #ffffff;
        alternate-background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        gridline-color: #e9ecef;
        font-size: 25px; /* <--- 修改 */
    }
    QTableWidget::item:selected {
        background: #cfe2ff; 
        color: #212529;
    }
    QHeaderView::section {
        background: #f8f9fa; 
        color: #495057;
        padding: 10px 8px;
        border: none;
        border-bottom: 1px solid #dee2e6;
        font-weight: 600;
        font-size: 25px; /* <--- 修改 */
    }
    
    /* 状态栏 */
    QStatusBar {
        background: #f8f9fa;
        color: #495057;
        border-top: 1px solid #dee2e6;
        font-size: 25px; /* <--- 修改 */
    }
    
    /* 标签 (确保背景透明) */
    QLabel {
        color: #212529;
        font-weight: 500;
        font-size: 25px; /* <--- 修改 */
        background-color: transparent; 
    }
    
    /* 滚动条 */
    QScrollBar:vertical { background: #f1f1f1; }
    QScrollBar::handle:vertical { background: #adb5bd; }
    QScrollBar::handle:vertical:hover { background: #6c757d; }
    QScrollBar:horizontal { background: #f1f1f1; }
    QScrollBar::handle:horizontal { background: #adb5bd; }
    QScrollBar::handle:horizontal:hover { background: #6c757d; }
    
    /* 分割线 */
    QSplitter::handle {
        background: #dee2e6; 
    }
    QSplitter::handle:hover { background: #adb5bd; }
    QSplitter::handle:pressed { background: #007bff; } 

    /* 顶部栏的 QFrame 分隔线 */
    QFrame[Shape="VLine"] {
        border: none;
        background: #dee2e6;
        width: 1px;
    }
    
    /* [!! 关键 !!] PyQtGraph 适配 (浅色) */
    .PlotWidget {
        background-color: #ffffff;
        border: 1px solid #dee2e6;
        border-radius: 8px;
    }
    """

# --- (后续的辅助函数保持不变) ---
# (ThemeManager, apply_modern_theme, create_modern_button_style 等...)

# 现代化按钮样式生成器
def create_modern_button_style(color_scheme: str) -> str:
    """创建现代化按钮样式"""
    color_schemes = {
        "primary": {
            "normal": "#4a9eff",
            "hover": "#5fadff", 
            "pressed": "#357abd",
            "text": "#ffffff"
        },
        "success": {
            "normal": "#28a745",
            "hover": "#32cd32",
            "pressed": "#1e7e34", 
            "text": "#ffffff"
        },
        "danger": {
            "normal": "#dc3545",
            "hover": "#ff4757",
            "pressed": "#bd2130",
            "text": "#ffffff"
        },
        "warning": {
            "normal": "#ffc107",
            "hover": "#ffdd57",
            "pressed": "#d39e00",
            "text": "#212529"
        },
        "info": {
            "normal": "#17a2b8",
            "hover": "#3dd5f3",
            "pressed": "#138496",
            "text": "#ffffff"
        }
    }
    
    colors = color_schemes.get(color_scheme, color_schemes["primary"])
    
    return f"""
    QPushButton[buttonStyle="{color_scheme}"] {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                   stop:0 {colors["normal"]}, stop:1 {colors["pressed"]});
        color: {colors["text"]};
        border: none;
        padding: 10px 20px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 25px; /* <--- 修改 */
        min-height: 20px;
        min-width: 80px;
        border: 1px solid transparent;
    }}
    
    QPushButton[buttonStyle="{color_scheme}"]:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                   stop:0 {colors["hover"]}, stop:1 {colors["normal"]});
        border: 1px solid rgba(255, 255, 255, 0.3);
    }}
    
    QPushButton[buttonStyle="{color_scheme}"]:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                   stop:0 {colors["pressed"]}, stop:1 {colors["normal"]});
    }}
    """

def get_animated_button_style() -> str:
    return """ """

def get_glass_effect_style() -> str:
    return """ """

def get_neon_glow_style() -> str:
    return """ """

# 主题管理器
class ThemeManager:
    """主题管理器"""
    
    def __init__(self):
        self.current_theme = "dark" 
        self.custom_styles = {}
        
    def get_theme(self, theme_name: str = None) -> str:
        if theme_name is None:
            theme_name = self.current_theme
        if theme_name == "dark":
            return get_dark_theme()
        elif theme_name == "light":
            return get_light_theme() # <--- 调用优化后的浅色主题
        else:
            return get_dark_theme()
            
    def set_theme(self, theme_name: str):
        self.current_theme = theme_name
        
    def add_custom_style(self, name: str, style: str):
        self.custom_styles[name] = style
        
    def get_combined_style(self, include_animations=True, include_glass=False, include_neon=False) -> str:
        base_style = self.get_theme()
        if include_animations: base_style += get_animated_button_style()
        if include_glass: base_style += get_glass_effect_style()
        if include_neon: base_style += get_neon_glow_style()
        for style in self.custom_styles.values():
            base_style += style
        return base_style

# 导出所有可用的样式主题和工具
AVAILABLE_THEMES = {
    "dark": get_dark_theme,
    "light": get_light_theme
}

# 预定义的颜色方案
COLOR_SCHEMES = {
    "blue": "#4a9eff",
    "green": "#28a745", 
    "red": "#dc3545",
    "orange": "#fd7e14",
    "yellow": "#ffc107",
    "purple": "#6f42c1",
    "pink": "#e83e8c",
    "cyan": "#17a2b8"
}

def apply_modern_theme(widget, theme="dark", effects=None):
    """为控件应用现代主题"""
    if effects is None:
        effects = []
        
    theme_manager = ThemeManager()
    theme_manager.set_theme(theme) 
    
    include_animations = "animations" in effects
    include_glass = "glass" in effects  
    include_neon = "neon" in effects
    
    style = theme_manager.get_combined_style(
        include_animations=include_animations,
        include_glass=include_glass, 
        include_neon=include_neon
    )
    
    widget.setStyleSheet(style)

def create_status_indicator_style(status: str) -> str:
    """创建状态指示器样式"""
    status_colors = {
        "success": "#28a745",
        "error": "#dc3545", 
        "warning": "#ffc107",
        "info": "#17a2b8",
        "active": "#28a745",
        "inactive": "#6c757d"
    }
    
    color = status_colors.get(status, "#6c757d")
    
    return f"""
    QLabel[statusIndicator="{status}"] {{
        color: {color};
        /* ... (样式代码) ... */
    }}
    """