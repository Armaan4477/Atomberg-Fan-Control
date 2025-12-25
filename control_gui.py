import json
import socket
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QComboBox, QFrame, QGroupBox,
    QGridLayout, QMessageBox, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor


class FanControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Fan configurations
        self.fans = {
            "Sofa Fan": "192.168.29.14",
            "Table Fan": "192.168.29.15"
        }
        self.target_port = 5600
        self.current_fan = "Sofa Fan"
        self.current_speed = 3
        self.led_on = True
        self.sleep_mode = False
        self.power_on = False
        
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Atomberg Fan Control")
        self.setFixedSize(400, 600)
        self.setStyleSheet(self.get_stylesheet())
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_label = QLabel("🌀 Atomberg Fan Control")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Fan Selection Group
        fan_group = QGroupBox("Select Fan")
        fan_group.setObjectName("fanGroup")
        fan_layout = QHBoxLayout(fan_group)
        
        self.fan_combo = QComboBox()
        self.fan_combo.addItems(self.fans.keys())
        self.fan_combo.currentTextChanged.connect(self.on_fan_changed)
        self.fan_combo.setMinimumHeight(40)
        fan_layout.addWidget(self.fan_combo)
        
        main_layout.addWidget(fan_group)
        
        # Power Control Group
        power_group = QGroupBox("Power")
        power_layout = QHBoxLayout(power_group)
        
        self.power_btn = QPushButton("⏻ OFF")
        self.power_btn.setObjectName("powerBtnOff")
        self.power_btn.setMinimumHeight(60)
        self.power_btn.setCheckable(True)
        self.power_btn.clicked.connect(self.toggle_power)
        power_layout.addWidget(self.power_btn)
        
        main_layout.addWidget(power_group)
        
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
        main_layout.addWidget(speed_group)
        
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
        
        main_layout.addWidget(features_group)
        
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
        main_layout.addWidget(timer_group)
        
        # Status Label
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        # Spacer
        main_layout.addStretch()
        
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
            #titleLabel {
                font-size: 24px;
                font-weight: bold;
                color: #00d4ff;
                padding: 10px;
                margin-bottom: 10px;
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
            QComboBox {
                background-color: #0f3460;
                border: 2px solid #00d4ff;
                border-radius: 8px;
                padding: 8px 15px;
                font-size: 14px;
                color: #eaeaea;
            }
            QComboBox:hover {
                border-color: #00ffff;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #0f3460;
                border: 2px solid #00d4ff;
                selection-background-color: #00d4ff;
                selection-color: #1a1a2e;
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
            #statusLabel {
                font-size: 12px;
                color: #888;
                padding: 10px;
                background-color: #16213e;
                border-radius: 5px;
            }
        """
    
    def on_fan_changed(self, fan_name):
        self.current_fan = fan_name
        self.status_label.setText(f"Selected: {fan_name}")
        
    def toggle_power(self):
        self.power_on = not self.power_on
        if self.power_on:
            self.power_btn.setText("⏻ ON")
            self.power_btn.setObjectName("powerBtnOn")
        else:
            self.power_btn.setText("⏻ OFF")
            self.power_btn.setObjectName("powerBtnOff")
        
        # Refresh style
        self.power_btn.setStyle(self.power_btn.style())
        
        self.send_command({"power": self.power_on})
        
    def on_speed_changed(self, value):
        self.current_speed = value
        self.speed_label.setText(f"Speed: {value}")
        self.send_command({"speed": value})
        
    def change_speed_delta(self, delta):
        new_speed = max(0, min(6, self.current_speed + delta))
        self.speed_slider.setValue(new_speed)
        
    def toggle_led(self):
        self.led_on = self.led_btn.isChecked()
        self.send_command({"led": self.led_on})
        
    def toggle_sleep(self):
        self.sleep_mode = self.sleep_btn.isChecked()
        self.send_command({"sleep": self.sleep_mode})
        
    def set_timer(self, value):
        # Uncheck all timer buttons except the clicked one
        for i, btn in enumerate(self.timer_btns):
            btn.setChecked(i == value)
        self.send_command({"timer": value})
        
    def send_command(self, command):
        target_ip = self.fans[self.current_fan]
        message = json.dumps(command).encode('utf-8')
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(message, (target_ip, self.target_port))
            sock.close()
            
            self.status_label.setText(f"✓ Sent to {self.current_fan}: {json.dumps(command)}")
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


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = FanControlApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
