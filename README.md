# Atomberg Fan Control

A desktop application for controlling Atomberg smart fans over a local network using UDP communication. Built with Python and PyQt6, this application provides a modern graphical interface for managing fan settings including power, speed, LED, sleep mode, and timer functions.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Technical Details](#technical-details)
- [Protocol Specification](#protocol-specification)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Overview

Atomberg Fan Control is a local network control solution for Atomberg smart ceiling fans. The application communicates directly with fans on your local network via UDP packets, eliminating the need for cloud connectivity. This provides faster response times and allows control even when internet connectivity is unavailable.

## Features

- **Multi-Fan Support**: Configure and switch between multiple fans in your home
- **Power Control**: Turn fans on and off with visual feedback
- **Speed Adjustment**: Control fan speed from 0 to 6 using a slider or quick buttons
- **LED Control**: Toggle the fan's LED indicator on/off
- **Sleep Mode**: Enable or disable sleep mode for gradual speed reduction
- **Timer Function**: Set auto-off timers for 1, 2, 3, or 4 hours
- **Real-Time State Sync**: Automatically receives and displays current fan state via UDP broadcasts
- **Modern Dark UI**: Clean, intuitive interface optimized for ease of use

## Requirements

### System Requirements

- Python 3.8 or higher
- macOS, Windows, or Linux operating system
- Network connectivity to the same local network as the Atomberg fans

### Python Dependencies

- PyQt6

## Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/Atomberg_Control.git
cd Atomberg_Control
```

2. Create and activate a virtual environment (recommended):

```bash
python -m venv .venv
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate     # On Windows
```

3. Install the required dependencies:

```bash
pip install PyQt6
```

## Configuration

Before running the application, you need to configure the IP addresses of your Atomberg fans. Open `control_gui.py` and locate the `FanSelectionWindow` class:

```python
class FanSelectionWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.fans = {
            "Sofa Fan": "192.168.29.14",
            "Table Fan": "192.168.29.15"
        }
```

Update the dictionary with your fan names and their corresponding IP addresses. You can add or remove entries as needed.

### Finding Fan IP Addresses

To discover the IP addresses of your Atomberg fans:

1. Check your router's DHCP client list for devices manufactured by Atomberg
2. Use the `find.py` utility script included in this repository
3. Use network scanning tools such as `nmap` or `arp-scan`

## Usage

### Starting the Application

Run the application using Python:

```bash
python control_gui.py
```

### Navigating the Interface

1. **Fan Selection Screen**: Upon launch, select the fan you wish to control from the list
2. **Control Screen**: Use the various controls to adjust fan settings:
   - **Power Button**: Toggle fan power on/off
   - **Speed Slider**: Drag to set speed (0-6) or use +/- buttons
   - **LED Button**: Toggle LED indicator
   - **Sleep Button**: Enable/disable sleep mode
   - **Timer Buttons**: Select auto-off timer duration
3. **Back Button**: Return to fan selection to switch fans
4. **Refresh Button**: Request state update from the fan

### State Synchronization

The application listens for UDP broadcast messages from fans on port 5625. When a fan broadcasts its state, the interface automatically updates to reflect the current settings. If the state appears outdated, interact with any control to trigger a state broadcast from the fan.

## Technical Details

### Architecture

The application consists of three main components:

1. **FanSelectionWindow**: Initial screen for selecting which fan to control
2. **FanControlWindow**: Main control interface with all fan controls
3. **FanStateListener**: Background thread that listens for UDP state broadcasts

### Network Communication

| Direction | Port | Protocol | Purpose |
|-----------|------|----------|---------|
| Outbound  | 5600 | UDP      | Send control commands to fan |
| Inbound   | 5625 | UDP      | Receive state broadcasts from fan |

### Threading Model

The application uses a daemon thread for the state listener to ensure non-blocking UI operation. Thread-safe communication between the listener and UI is achieved through PyQt signals.

## Protocol Specification

### Command Format

Commands are sent as JSON objects via UDP:

```json
{"power": true}
{"speed": 4}
{"led": false}
{"sleep": true}
{"timer": 2}
```

### State Broadcast Format

Fans broadcast their state as JSON with a `state_string` field. The state is encoded as a numeric value with the following bit structure:

| Bits | Field | Description |
|------|-------|-------------|
| 0-2  | Speed | Fan speed (0-6) |
| 4    | Power | Power state |
| 5    | LED   | LED state |
| 7    | Sleep | Sleep mode state |
| 16-19| Timer | Timer hours (0-4) |
| 24-31| Timer Elapsed | Minutes elapsed in timer |

## Troubleshooting

### Application Cannot Connect to Fan

1. Verify the fan IP address is correct in the configuration
2. Ensure your computer is on the same local network as the fan
3. Check that no firewall is blocking UDP ports 5600 and 5625
4. Confirm the fan is powered on and connected to WiFi

### State Not Updating

1. The state listener requires port 5625 to be available
2. Some network configurations may block UDP broadcasts
3. Try interacting with a control to trigger a state broadcast
4. Check if another instance of the application is already running

### Permission Errors on Port Binding

On some systems, binding to UDP ports may require elevated privileges. If you encounter permission errors:

- On Linux/macOS: Run with `sudo` or configure capabilities
- Ensure no other application is using port 5625

### UI Not Responding

If the interface becomes unresponsive:

1. Close and restart the application
2. Check system resources (CPU, memory usage)
3. Verify network connectivity

## License

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.

---

Developed for use with Atomberg smart ceiling fans. This is an unofficial third-party application and is not affiliated with or endorsed by Atomberg Technologies.
