# FPGA Debug System

<p align="center">
  <strong>面向 FPGA 调试、信号观察、协议验证和通信测试的 PyQt5 桌面工具。</strong>
</p>

<p align="center">
  <a href="https://github.com/Reikamo/fpga_debug_system"><img alt="Repository" src="https://img.shields.io/badge/GitHub-fpga_debug_system-181717?logo=github"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white">
  <img alt="GUI" src="https://img.shields.io/badge/GUI-PyQt5-41CD52">
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Windows-lightgrey">
</p>

<p align="center">
  <a href="./README.md">English</a> | <a href="./README.zh-CN.md">简体中文</a>
</p>

---

## 项目简介

FPGA Debug System 是一个用于 FPGA 开发和调试流程的桌面应用。它把波形采集、信号生成、逻辑分析、协议级调试以及 UDP/串口通信整合到同一个 PyQt5 界面中。

该项目适用于 FPGA 上板调试、板级验证，以及 PC 与 FPGA 目标板之间的快速通信测试。

## 功能亮点

| 模块 | 说明 |
| --- | --- |
| 示波器 | 配置采样参数，接收波形数据，并观察信号行为。 |
| 信号发生器 | 控制 DDS 输出和自定义波形生成流程。 |
| 逻辑分析仪 | 捕获数字通道，辅助分析时序和状态变化。 |
| FPGA 调试器 | 支持 UART、SPI、I2C、CAN、PWM、DO 和频率测量等调试工具。 |
| 通信管理 | 在主界面中切换 UDP 和串口通信管理器。 |
| 协议配置 | 在 `protocol.py` 中集中维护包头定义，并支持通过设置覆盖。 |

## 项目结构

```text
.
|-- main.py                       # 应用入口和主窗口
|-- protocol.py                   # 包头、包类型和载荷辅助类
|-- communication_manager.py      # 通用通信抽象
|-- network_manager.py            # UDP 通信管理器
|-- serial_manager.py             # 串口通信管理器
|-- oscilloscope_widget.py        # 示波器 UI/控制器
|-- signal_generator_widget.py    # 信号发生器 UI/控制器
|-- logic_analyzer_widget.py      # 逻辑分析仪 UI/控制器
|-- fpga_debugger_widget.py       # FPGA 协议调试 UI
|-- settings_widget.py            # 应用设置界面
|-- styles.py                     # PyQt5 主题和样式辅助函数
|-- utils.py                      # 工具函数
`-- icons/                        # 应用图标和图片资源
```

## 环境要求

- Windows
- Python 3.9 或更高版本
- PyQt5
- pyserial

部分控件可能会根据本地启用的功能依赖额外的绘图或运行时库。

## 快速开始

创建并激活虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

安装核心依赖：

```powershell
pip install PyQt5 pyserial
```

运行应用：

```powershell
python main.py
```

## 基本使用流程

1. 在项目根目录启动应用。
2. 在顶部连接栏选择 UDP 或串口通信方式。
3. 配置目标 IP/端口或串口参数。
4. 从左侧导航栏打开需要使用的调试工具。
5. 发送配置命令、接收数据，并在对应界面中观察结果。

## 配置说明

- 用户设置通过 `QSettings` 保存到 `MyCompany/FPGADebugSystem`。
- 默认包头定义位于 `protocol.py`。
- 应用设置中可以覆盖部分包头配置。
- 如果源码注释在编辑器里显示乱码，请尝试使用 UTF-8 或检查原始文件编码。

## 仓库信息

- GitHub: https://github.com/Reikamo/fpga_debug_system
- 主分支：`main`

## 许可证

当前仓库尚未包含 license 文件。公开分发或接受外部贡献前，建议先补充明确的开源许可证。
