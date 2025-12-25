import json
import socket
import sys
import threading
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QComboBox, QFrame, QGroupBox,
    QGridLayout, QMessageBox, QSpacerItem, QSizePolicy, QStackedWidget
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor


class StateSignals(QObject):
    """Signals for thread-safe UI updates"""
    state_received = pyqtSignal(dict)


class FanStateListener(threading.Thread):
    """Background thread to listen for fan state broadcasts"""
    def __init__(self, signals, target_device_id=None):
        super().__init__(daemon=True)
        self.signals = signals
        self.target_device_id = target_device_id
        self.running = True
        self.processed_messages = set()
        
    def stop(self):
        self.running = False
        
    def decode_state_value(self, value):
        """Decode the state value from the first field of state_string"""
        try:
            value = int(value)
            state = {
                'power': (0x10 & value) > 0,
                'led': (0x20 & value) > 0,
                'sleep': (0x80 & value) > 0,
                'speed': 0x07 & value,
                'timer': round((0x0F0000 & value) / 65536),
                'timer_elapsed_mins': round((0xFF000000 & value) * 4 / 16777216),
                'brightness': round((0x7F00 & value) / 256),
                'cool': (0x08 & value) > 0,
                'warm': (0x8000 & value) > 0,
            }
            # Determine color mode
            if state['cool'] and state['warm']:
                state['color_mode'] = 'Daylight'
            elif state['cool']:
                state['color_mode'] = 'Cool'
            elif state['warm']:
                state['color_mode'] = 'Warm'
            else:
                state['color_mode'] = 'Off'
            return state
        except Exception as e:
            print(f"Error decoding state: {e}")
            return None
    
    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1.0)  # 1 second timeout for checking running flag
        
        try:
            sock.bind(('', 5625))
            print("Listening for fan state on port 5625...")
            
            while self.running:
                try:
                    data, addr = sock.recvfrom(4096)
                    # Try to parse the message - could be hex-encoded or plain JSON
                    try:
                        raw_data = data.decode('utf-8').strip()
                        
                        # Try hex decoding first, fall back to plain JSON
                        try:
                            # Check if it looks like hex (only hex chars)
                            if all(c in '0123456789abcdefABCDEF' for c in raw_data):
                                ascii_data = bytes.fromhex(raw_data).decode('utf-8')
                            else:
                                ascii_data = raw_data
                        except ValueError:
                            # Not valid hex, treat as plain JSON
                            ascii_data = raw_data
                        
                        state_json = json.loads(ascii_data)
                        
                        # Must have required fields
                        if 'state_string' not in state_json:
                            continue
                        
                        # Check for duplicate messages
                        message_id = state_json.get('message_id', '')
                        if message_id and message_id in self.processed_messages:
                            continue
                        if message_id:
                            self.processed_messages.add(message_id)
                        
                        # Keep only last 100 message IDs
                        if len(self.processed_messages) > 100:
                            self.processed_messages = set(list(self.processed_messages)[-50:])
                        
                        # Parse state_string
                        state_string = state_json.get('state_string', '')
                        fields = state_string.split(',')
                        if fields:
                            decoded_state = self.decode_state_value(fields[0])
                            if decoded_state:
                                decoded_state['device_id'] = state_json.get('device_id', '')
                                decoded_state['raw_state'] = state_string
                                self.signals.state_received.emit(decoded_state)
                                
                    except json.JSONDecodeError:
                        # Not a valid JSON message, ignore
                        pass
                    except Exception as e:
                        print(f"Error parsing state message: {e}")
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Listener error: {e}")
                    
        finally:
            sock.close()


class FanSelectionWindow(QWidget):
    """Initial window for fan selection"""
    fan_selected = pyqtSignal(str, str)  # fan_name, ip
    
    def __init__(self):
        super().__init__()
        self.fans = {
            "Sofa Fan": "192.168.29.14",
            "Table Fan": "192.168.29.15"
        }
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(30)
        layout.setContentsMargins(40, 60, 40, 60)
        
        # Title
        title_label = QLabel("🌀 Atomberg Fan Control")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Subtitle
        subtitle = QLabel("Select a fan to control")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        
        layout.addSpacing(20)
        
        # Fan buttons
        for fan_name, ip in self.fans.items():
            btn = QPushButton(f"🌬️  {fan_name}\n{ip}")
            btn.setObjectName("fanSelectBtn")
            btn.setMinimumHeight(100)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, n=fan_name, i=ip: self.select_fan(n, i))
            layout.addWidget(btn)
        
        layout.addStretch()
        
        # Footer
        footer = QLabel("Waiting for fan selection...")
        footer.setObjectName("footerLabel")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)
        
    def select_fan(self, fan_name, ip):
        self.fan_selected.emit(fan_name, ip)


class FanControlWindow(QWidget):
    """Main control window for the selected fan"""
    back_requested = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.target_port = 5600
        self.current_fan = ""
        self.current_ip = ""
        self.current_speed = 0
        self.led_on = False
        self.sleep_mode = False
        self.power_on = False
        self.current_timer = 0
        self._updating_ui = False  # Flag to prevent sending commands during UI updates
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header with back button
        header_layout = QHBoxLayout()
        
        self.back_btn = QPushButton("← Back")
        self.back_btn.setObjectName("backBtn")
        self.back_btn.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self.back_btn)
        
        self.fan_title = QLabel("Fan Control")
        self.fan_title.setObjectName("fanTitleLabel")
        self.fan_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.fan_title, 1)
        
        # Refresh button
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setObjectName("refreshBtn")
        self.refresh_btn.setToolTip("Refresh state")
        self.refresh_btn.clicked.connect(self.request_state_refresh)
        header_layout.addWidget(self.refresh_btn)
        
        layout.addLayout(header_layout)
        
        # Power Control Group
        power_group = QGroupBox("Power")
        power_layout = QHBoxLayout(power_group)
        
        self.power_btn = QPushButton("⏻ OFF")
        self.power_btn.setObjectName("powerBtnOff")
        self.power_btn.setMinimumHeight(60)
        self.power_btn.setCheckable(True)
        self.power_btn.clicked.connect(self.toggle_power)
        power_layout.addWidget(self.power_btn)
        
        layout.addWidget(power_group)
        
        # Speed Control Group
        speed_group = QGroupBox("Speed Control")
        speed_layout = QVBoxLayout(speed_group)
        
        # Speed display
        self.speed_label = QLabel(f"Speed: {self.current_speed}")
        self.speed_label.setObjectName("speedLabel")
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        speed_layout.addWidget(self.speed_label)
        
        # Speed slider
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(0)
        self.speed_slider.setMaximum(6)
        self.speed_slider.setValue(self.current_speed)
        self.speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.speed_slider.setTickInterval(1)
        self.speed_slider.valueChanged.connect(self.on_speed_changed)
        speed_layout.addWidget(self.speed_slider)
        
        # Speed labels
        speed_labels_layout = QHBoxLayout()
        for i in range(7):
            lbl = QLabel(str(i))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #888; font-size: 11px;")
            speed_labels_layout.addWidget(lbl)
        speed_layout.addLayout(speed_labels_layout)
        
        # Quick speed buttons
        quick_speed_layout = QHBoxLayout()
        self.speed_down_btn = QPushButton("➖")
        self.speed_down_btn.setObjectName("quickBtn")
        self.speed_down_btn.clicked.connect(lambda: self.change_speed_delta(-1))
        quick_speed_layout.addWidget(self.speed_down_btn)
        
        self.speed_up_btn = QPushButton("➕")
        self.speed_up_btn.setObjectName("quickBtn")
        self.speed_up_btn.clicked.connect(lambda: self.change_speed_delta(1))
        quick_speed_layout.addWidget(self.speed_up_btn)
        
        speed_layout.addLayout(quick_speed_layout)
        layout.addWidget(speed_group)
        
        # Features Group
        features_group = QGroupBox("Features")
        features_layout = QGridLayout(features_group)
        features_layout.setSpacing(10)
        
        # LED Toggle
        self.led_btn = QPushButton("💡 LED")
        self.led_btn.setObjectName("featureBtn")
        self.led_btn.setCheckable(True)
        self.led_btn.setChecked(self.led_on)
        self.led_btn.clicked.connect(self.toggle_led)
        self.led_btn.setMinimumHeight(50)
        features_layout.addWidget(self.led_btn, 0, 0)
        
        # Sleep Mode Toggle
        self.sleep_btn = QPushButton("🌙 Sleep")
        self.sleep_btn.setObjectName("featureBtn")
        self.sleep_btn.setCheckable(True)
        self.sleep_btn.setChecked(self.sleep_mode)
        self.sleep_btn.clicked.connect(self.toggle_sleep)
        self.sleep_btn.setMinimumHeight(50)
        features_layout.addWidget(self.sleep_btn, 0, 1)
        
        layout.addWidget(features_group)
        
        # Timer Group
        timer_group = QGroupBox("Timer")
        timer_layout = QHBoxLayout(timer_group)
        
        timer_buttons = [("Off", 0), ("1h", 1), ("2h", 2), ("3h", 3), ("4h", 4)]
        self.timer_btns = []
        for text, value in timer_buttons:
            btn = QPushButton(text)
            btn.setObjectName("timerBtn")
            btn.setMinimumHeight(40)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, v=value: self.set_timer(v))
            timer_layout.addWidget(btn)
            self.timer_btns.append(btn)
        
        self.timer_btns[0].setChecked(True)
        layout.addWidget(timer_group)
        
        # State Info Group
        state_group = QGroupBox("Current State")
        state_layout = QVBoxLayout(state_group)
        
        self.state_info = QLabel("Fetching state...")
        self.state_info.setObjectName("stateInfo")
        self.state_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_info.setWordWrap(True)
        state_layout.addWidget(self.state_info)
        
        layout.addWidget(state_group)
        
        # Status Label
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
    def set_fan(self, fan_name, ip):
        """Set the current fan to control"""
        self.current_fan = fan_name
        self.current_ip = ip
        self.fan_title.setText(f"🌬️ {fan_name}")
        self.state_info.setText("Waiting for state broadcast...\nUse any control to trigger a state update")
        self.status_label.setText(f"Connected to {ip}")
        
    def update_from_state(self, state):
        """Update UI from received state"""
        self._updating_ui = True
        
        try:
            # Update power
            self.power_on = state.get('power', False)
            self.power_btn.setChecked(self.power_on)
            if self.power_on:
                self.power_btn.setText("⏻ ON")
                self.power_btn.setObjectName("powerBtnOn")
            else:
                self.power_btn.setText("⏻ OFF")
                self.power_btn.setObjectName("powerBtnOff")
            self.power_btn.setStyle(self.power_btn.style())
            
            # Update speed
            self.current_speed = state.get('speed', 0)
            self.speed_slider.setValue(self.current_speed)
            self.speed_label.setText(f"Speed: {self.current_speed}")
            
            # Update LED
            self.led_on = state.get('led', False)
            self.led_btn.setChecked(self.led_on)
            
            # Update sleep mode
            self.sleep_mode = state.get('sleep', False)
            self.sleep_btn.setChecked(self.sleep_mode)
            
            # Update timer
            self.current_timer = state.get('timer', 0)
            for i, btn in enumerate(self.timer_btns):
                btn.setChecked(i == self.current_timer)
            
            # Update state info display
            info_text = f"""
Power: {'ON' if self.power_on else 'OFF'} | Speed: {self.current_speed} | LED: {'ON' if self.led_on else 'OFF'}
Sleep: {'ON' if self.sleep_mode else 'OFF'} | Timer: {self.current_timer}h | Color: {state.get('color_mode', 'N/A')}
            """.strip()
            self.state_info.setText(info_text)
            
            self.status_label.setText("✓ State synchronized")
            self.status_label.setStyleSheet("""
                font-size: 12px;
                color: #00bf63;
                padding: 10px;
                background-color: #16213e;
                border-radius: 5px;
            """)
            
        finally:
            self._updating_ui = False
    
    def request_state_refresh(self):
        """Request state by sending an empty query - note: this may not work on all fans"""
        self.status_label.setText("🔄 Waiting for state broadcast...")
        self.state_info.setText("Waiting for state broadcast...\nInteract with any control to see current state")
        
    def toggle_power(self):
        if self._updating_ui:
            return
        self.power_on = not self.power_on
        if self.power_on:
            self.power_btn.setText("⏻ ON")
            self.power_btn.setObjectName("powerBtnOn")
        else:
            self.power_btn.setText("⏻ OFF")
            self.power_btn.setObjectName("powerBtnOff")
        self.power_btn.setStyle(self.power_btn.style())
        self.send_command({"power": self.power_on})
        
    def on_speed_changed(self, value):
        if self._updating_ui:
            return
        self.current_speed = value
        self.speed_label.setText(f"Speed: {value}")
        self.send_command({"speed": value})
        
    def change_speed_delta(self, delta):
        new_speed = max(0, min(6, self.current_speed + delta))
        self.speed_slider.setValue(new_speed)
        
    def toggle_led(self):
        if self._updating_ui:
            return
        self.led_on = self.led_btn.isChecked()
        self.send_command({"led": self.led_on})
        
    def toggle_sleep(self):
        if self._updating_ui:
            return
        self.sleep_mode = self.sleep_btn.isChecked()
        self.send_command({"sleep": self.sleep_mode})
        
    def set_timer(self, value):
        if self._updating_ui:
            return
        for i, btn in enumerate(self.timer_btns):
            btn.setChecked(i == value)
        self.current_timer = value
        self.send_command({"timer": value})
        
    def send_command(self, command):
        message = json.dumps(command).encode('utf-8')
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(message, (self.current_ip, self.target_port))
            sock.close()
            
            self.status_label.setText(f"✓ Sent: {json.dumps(command)}")
            self.status_label.setStyleSheet("""
                font-size: 12px;
                color: #00bf63;
                padding: 10px;
                background-color: #16213e;
                border-radius: 5px;
            """)
        except Exception as e:
            self.status_label.setText(f"✗ Error: {str(e)}")
            self.status_label.setStyleSheet("""
                font-size: 12px;
                color: #e94560;
                padding: 10px;
                background-color: #16213e;
                border-radius: 5px;
            """)


class FanControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.state_signals = StateSignals()
        self.state_listener = None
        self.current_device_id = None
        
        # Device ID mapping (you may need to update these)
        self.device_ids = {
            "192.168.29.14": None,  # Will be populated when state is received
            "192.168.29.15": None,
        }
        
        self.init_ui()
        self.start_state_listener()
        
    def init_ui(self):
        self.setWindowTitle("Atomberg Fan Control")
        self.setFixedSize(400, 650)
        self.setStyleSheet(self.get_stylesheet())
        
        # Stacked widget for switching between screens
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        
        # Selection screen
        self.selection_screen = FanSelectionWindow()
        self.selection_screen.fan_selected.connect(self.on_fan_selected)
        self.stack.addWidget(self.selection_screen)
        
        # Control screen
        self.control_screen = FanControlWindow()
        self.control_screen.back_requested.connect(self.show_selection_screen)
        self.stack.addWidget(self.control_screen)
        
        # Connect state signals
        self.state_signals.state_received.connect(self.on_state_received)
        
        # Show selection screen initially
        self.stack.setCurrentWidget(self.selection_screen)
        
    def start_state_listener(self):
        """Start the background listener for fan state broadcasts"""
        self.state_listener = FanStateListener(self.state_signals)
        self.state_listener.start()
        
    def on_fan_selected(self, fan_name, ip):
        """Handle fan selection"""
        self.control_screen.set_fan(fan_name, ip)
        self.stack.setCurrentWidget(self.control_screen)
        # Don't send any command - wait for user interaction or next broadcast
        
    def on_state_received(self, state):
        """Handle received state from fan"""
        # Update device ID mapping
        device_id = state.get('device_id', '')
        if device_id:
            # Store device ID for future reference
            for ip in self.device_ids:
                if self.device_ids[ip] is None or self.device_ids[ip] == device_id:
                    self.device_ids[ip] = device_id
                    break
        
        # Update control screen if it's visible
        if self.stack.currentWidget() == self.control_screen:
            self.control_screen.update_from_state(state)
        
    def show_selection_screen(self):
        """Go back to fan selection screen"""
        self.stack.setCurrentWidget(self.selection_screen)
        
    def closeEvent(self, event):
        """Clean up when closing"""
        if self.state_listener:
            self.state_listener.stop()
        event.accept()
        
    def get_stylesheet(self):
        return """
            QMainWindow {
                background-color: #1a1a2e;
            }
            QWidget {
                background-color: #1a1a2e;
                color: #eaeaea;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            QStackedWidget {
                background-color: #1a1a2e;
            }
            #titleLabel {
                font-size: 28px;
                font-weight: bold;
                color: #00d4ff;
                padding: 10px;
                margin-bottom: 5px;
            }
            #subtitleLabel {
                font-size: 14px;
                color: #888;
                padding: 5px;
            }
            #fanTitleLabel {
                font-size: 20px;
                font-weight: bold;
                color: #00d4ff;
            }
            #fanSelectBtn {
                background-color: #16213e;
                border: 2px solid #0f3460;
                border-radius: 15px;
                font-size: 16px;
                font-weight: bold;
                color: #eaeaea;
                padding: 20px;
                text-align: left;
            }
            #fanSelectBtn:hover {
                border-color: #00d4ff;
                background-color: #0f3460;
            }
            #fanSelectBtn:pressed {
                background-color: #00d4ff;
                color: #1a1a2e;
            }
            #footerLabel {
                font-size: 12px;
                color: #555;
            }
            #backBtn {
                background-color: transparent;
                border: 2px solid #0f3460;
                border-radius: 8px;
                font-size: 14px;
                color: #888;
                padding: 8px 15px;
            }
            #backBtn:hover {
                border-color: #00d4ff;
                color: #00d4ff;
            }
            #refreshBtn {
                background-color: transparent;
                border: 2px solid #0f3460;
                border-radius: 8px;
                font-size: 16px;
                padding: 8px 12px;
            }
            #refreshBtn:hover {
                border-color: #00d4ff;
                background-color: #0f3460;
            }
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                border: 2px solid #16213e;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #16213e;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 5px;
                color: #00d4ff;
            }
            #powerBtnOff {
                background-color: #e94560;
                border: none;
                border-radius: 10px;
                font-size: 20px;
                font-weight: bold;
                color: white;
            }
            #powerBtnOff:hover {
                background-color: #ff6b6b;
            }
            #powerBtnOn {
                background-color: #00bf63;
                border: none;
                border-radius: 10px;
                font-size: 20px;
                font-weight: bold;
                color: white;
            }
            #powerBtnOn:hover {
                background-color: #00e676;
            }
            #speedLabel {
                font-size: 18px;
                font-weight: bold;
                color: #00d4ff;
                padding: 5px;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 8px;
                background: #0f3460;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #00d4ff;
                border: none;
                width: 24px;
                height: 24px;
                margin: -8px 0;
                border-radius: 12px;
            }
            QSlider::handle:horizontal:hover {
                background: #00ffff;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00d4ff, stop:1 #00bf63);
                border-radius: 4px;
            }
            #quickBtn {
                background-color: #0f3460;
                border: 2px solid #00d4ff;
                border-radius: 8px;
                font-size: 18px;
                padding: 10px;
                min-width: 60px;
            }
            #quickBtn:hover {
                background-color: #00d4ff;
                color: #1a1a2e;
            }
            #quickBtn:pressed {
                background-color: #00bf63;
            }
            #featureBtn {
                background-color: #0f3460;
                border: 2px solid #533483;
                border-radius: 10px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
            }
            #featureBtn:hover {
                border-color: #00d4ff;
            }
            #featureBtn:checked {
                background-color: #533483;
                border-color: #00d4ff;
            }
            #timerBtn {
                background-color: #0f3460;
                border: 2px solid #16213e;
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
                padding: 8px;
            }
            #timerBtn:hover {
                border-color: #00d4ff;
            }
            #timerBtn:checked {
                background-color: #00d4ff;
                color: #1a1a2e;
                border-color: #00d4ff;
            }
            #stateInfo {
                font-size: 12px;
                color: #aaa;
                padding: 10px;
                line-height: 1.5;
            }
            #statusLabel {
                font-size: 12px;
                color: #888;
                padding: 10px;
                background-color: #16213e;
                border-radius: 5px;
            }
        """


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = FanControlApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
