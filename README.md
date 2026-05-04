# FPGA Debug System

<p align="center">
  <strong>A PyQt5 desktop toolkit for FPGA bring-up, signal observation, protocol debugging, and communication testing.</strong>
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

## Overview

FPGA Debug System is a desktop application for FPGA development and debugging workflows. It brings waveform acquisition, signal generation, logic analysis, protocol-level debugging, and UDP/serial communication into one PyQt5 interface.

The project is designed for hardware bring-up, board-level verification, and quick communication tests between a PC and an FPGA target.

## Highlights

| Area | Description |
| --- | --- |
| Oscilloscope | Configure sampling, receive waveform data, and inspect signal behavior. |
| Signal Generator | Control DDS-style output and custom waveform generation workflows. |
| Logic Analyzer | Capture and inspect digital channels for timing and state analysis. |
| FPGA Debugger | Work with UART, SPI, I2C, CAN, PWM, DO, and frequency measurement tools. |
| Communication | Switch between UDP and serial communication managers from the main UI. |
| Protocol Config | Keep packet headers centralized in `protocol.py`, with settings-based overrides. |

## Project Structure

```text
.
|-- main.py                       # Application entry point and main window
|-- protocol.py                   # Packet headers, packet types, and payload helpers
|-- communication_manager.py      # Shared communication abstraction
|-- network_manager.py            # UDP communication manager
|-- serial_manager.py             # Serial communication manager
|-- oscilloscope_widget.py        # Oscilloscope UI/controller
|-- signal_generator_widget.py    # Signal generator UI/controller
|-- logic_analyzer_widget.py      # Logic analyzer UI/controller
|-- fpga_debugger_widget.py       # FPGA protocol debugger UI
|-- settings_widget.py            # Application settings UI
|-- styles.py                     # PyQt5 theme and styling helpers
|-- utils.py                      # Utility helpers
`-- icons/                        # Application icons and image assets
```

## Requirements

- Windows
- Python 3.9 or newer
- PyQt5
- pyserial

Some widgets may need additional plotting or runtime packages depending on which features are enabled in your local environment.

## Quick Start

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the core dependencies:

```powershell
pip install PyQt5 pyserial
```

Run the application:

```powershell
python main.py
```

## Basic Workflow

1. Start the application from the project root.
2. Select UDP or serial communication from the connection bar.
3. Configure the target IP/port or serial port parameters.
4. Open the required tool from the left navigation panel.
5. Send configuration commands, receive data, and inspect the results in the corresponding view.

## Configuration Notes

- User settings are stored through `QSettings` under `MyCompany/FPGADebugSystem`.
- Default packet headers are defined in `protocol.py`.
- Packet header overrides can be loaded from application settings.
- If source comments appear garbled in an editor, reopen the files as UTF-8 or check the original file encoding.

## Repository

- GitHub: https://github.com/Reikamo/fpga_debug_system
- Main branch: `main`

## License

No license file is currently included. Add a license before distributing this project publicly or accepting external contributions.
