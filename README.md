# FPGA Debug System

FPGA Debug System is a PyQt5 desktop application for FPGA bring-up and debugging. It provides a unified UI for oscilloscope-style sampling, signal generation, logic analysis, protocol debugging, and communication over UDP or serial links.

## Features

- Oscilloscope controller for waveform acquisition and display
- Signal generator controller for DDS and custom waveform output
- Logic analyzer controller for digital signal capture
- FPGA debugger tools for UART, SPI, I2C, CAN, PWM, DO, and frequency measurement workflows
- UDP and serial communication managers
- Configurable packet headers through application settings
- Modern PyQt5 UI with sidebar navigation and theme styling

## Project Structure

```text
.
|-- main.py                       # Application entry point
|-- protocol.py                   # Packet type definitions and payload helpers
|-- communication_manager.py      # Shared communication abstraction
|-- network_manager.py            # UDP communication
|-- serial_manager.py             # Serial communication
|-- oscilloscope_widget.py        # Oscilloscope UI/controller
|-- signal_generator_widget.py    # Signal generator UI/controller
|-- logic_analyzer_widget.py      # Logic analyzer UI/controller
|-- fpga_debugger_widget.py       # FPGA protocol debugger UI
|-- settings_widget.py            # Application settings UI
|-- styles.py                     # UI theme styles
|-- utils.py                      # Utility helpers
`-- icons/                        # Application icons and images
```

## Requirements

- Python 3.9 or newer
- PyQt5
- pyserial

Optional packages may be required depending on the enabled widgets and plotting features.

## Installation

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the required packages:

```powershell
pip install PyQt5 pyserial
```

## Usage

Run the application from the project root:

```powershell
python main.py
```

After startup, choose the communication method in the connection bar, configure the target IP/port or serial port, and open the required tool from the left navigation panel.

## Notes

- The application stores user settings with `QSettings` under `MyCompany/FPGADebugSystem`.
- Packet header defaults are defined in `protocol.py` and can be overridden from settings.
- Some source comments may appear garbled if opened with the wrong encoding. Use UTF-8 where possible.

## Repository

GitHub: https://github.com/Reikamo/fpga_debug_system
