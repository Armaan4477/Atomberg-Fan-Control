from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)


def load_env(env_path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not env_path.exists():
        raise FileNotFoundError(f"Missing .env file at {env_path}")

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


class AtombergClient:
    def __init__(self, api_key: str, refresh_token: str, base_url: str) -> None:
        self.api_key = api_key
        self.refresh_token = refresh_token
        self.base_url = base_url.rstrip("/")
        self._access_token: Optional[str] = None
        self._beacon_map: Dict[str, Dict[str, Any]] = {}
        self._beacon_lock = threading.Lock()
        self._listener_started = False
        self._listener_port = 5625
        self._command_port = 5600
        self._beacon_ttl_secs = 5

    @staticmethod
    def _normalize_device_id(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    def start_udp_listener(self) -> None:
        if self._listener_started:
            return
        self._listener_started = True
        thread = threading.Thread(target=self._udp_listener_loop, daemon=True)
        thread.start()

    def _udp_listener_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", self._listener_port))
        sock.settimeout(1.0)

        while True:
            try:
                data, addr = sock.recvfrom(4096)
                payload = data.decode(errors="ignore").strip()
                # Atomberg beacons start with the 12-char device MAC (device_id).
                if len(payload) >= 12:
                    mac = self._normalize_device_id(payload[:12])
                    if mac:
                        with self._beacon_lock:
                            self._beacon_map[mac] = {
                                "ip": addr[0],
                                "last_seen": time.time(),
                            }
            except socket.timeout:
                pass
            except OSError:
                return

            now = time.time()
            with self._beacon_lock:
                stale = [
                    key
                    for key, info in self._beacon_map.items()
                    if now - float(info.get("last_seen", 0)) > self._beacon_ttl_secs
                ]
                for key in stale:
                    del self._beacon_map[key]

    def get_local_ip(self, device_id: str) -> Optional[str]:
        normalized = self._normalize_device_id(device_id)
        with self._beacon_lock:
            info = self._beacon_map.get(normalized)
            if not info:
                return None
            return str(info.get("ip"))

    def send_local_command(self, device_id: str, command: Dict[str, Any]) -> Dict[str, Any]:
        self.start_udp_listener()
        target_ip = self.get_local_ip(device_id)

        # Give beacon discovery a short window on first attempt.
        if target_ip is None:
            deadline = time.time() + 2.0
            while time.time() < deadline:
                time.sleep(0.1)
                target_ip = self.get_local_ip(device_id)
                if target_ip:
                    break

        if target_ip is None:
            raise RuntimeError(
                "Local fan IP not discovered yet. Ensure phone/laptop and fan are on the same LAN "
                "and wait a few seconds for UDP beacons."
            )

        payload = json.dumps(command).encode("utf-8")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(payload, (target_ip, self._command_port))
        finally:
            sock.close()

        return {
            "status": "Success",
            "message": "Command sent locally over UDP",
            "device_id": device_id,
            "target_ip": target_ip,
            "command": command,
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: Optional[str] = None,
        query: Optional[Dict[str, str]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"

        headers = {
            "x-api-key": self.api_key,
            "Accept": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=query,
                json=payload,
                timeout=20,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Network error: {exc}") from exc

        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text}")

        try:
            return response.json()
        except ValueError:
            raise RuntimeError(f"Non-JSON response: {response.text}")

    def get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        result = self._request(
            "GET",
            "/v1/get_access_token",
            token=self.refresh_token,
        )
        token = (
            result.get("message", {}).get("access_token")
            if isinstance(result.get("message"), dict)
            else None
        )
        if not token:
            raise RuntimeError(f"Could not extract access token from response: {result}")
        self._access_token = token
        return token

    def list_devices(self) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/v1/get_list_of_devices",
            token=self.get_access_token(),
        )

    def get_device_state(self, device_id: str) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/v1/get_device_state",
            token=self.get_access_token(),
            query={"device_id": device_id},
        )

    def send_command(self, device_id: str, command: Dict[str, Any]) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/v1/send_command",
            token=self.get_access_token(),
            payload={"device_id": device_id, "command": command},
        )


class AtombergWindow(QMainWindow):
    def __init__(self, client: AtombergClient) -> None:
        super().__init__()
        self.client = client
        self.devices: list[Dict[str, Any]] = []
        self.selected_device: Optional[Dict[str, Any]] = None
        self.current_state: Dict[str, Any] = {}

        self.setWindowTitle("Atomberg Home Controller")
        self.resize(1000, 680)

        self._apply_styles()

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.selection_page = self._build_selection_page()
        self.control_page = self._build_control_page()
        self.stack.addWidget(self.selection_page)
        self.stack.addWidget(self.control_page)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Loading your fans...")
        self.client.start_udp_listener()

        self.load_devices()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #0b1220;
            }
            QWidget {
                color: #d6e1ff;
                font-family: "Avenir Next", "Helvetica Neue", "Segoe UI";
                font-size: 14px;
            }
            QLabel#title {
                font-size: 34px;
                font-weight: 700;
                color: #f1f5ff;
            }
            QLabel#subtitle {
                font-size: 15px;
                color: #98acd8;
            }
            QFrame#card {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #121b31, stop:1 #1b2846);
                border: 1px solid #2f4676;
                border-radius: 14px;
            }
            QListWidget {
                background: #111a2e;
                border: 1px solid #2f4676;
                border-radius: 10px;
                padding: 6px;
            }
            QListWidget::item {
                border-radius: 8px;
                padding: 10px;
                margin: 4px;
                background: #16213b;
            }
            QListWidget::item:selected {
                background: #2c4f94;
                color: #f5f8ff;
            }
            QPushButton {
                background: #28467f;
                color: #f5f8ff;
                border: 1px solid #3f63a8;
                border-radius: 10px;
                padding: 8px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #365da7;
            }
            QPushButton:disabled {
                background: #1b2a48;
                color: #89a1d1;
                border-color: #314a79;
            }
            QPushButton#primary {
                background: #21a07a;
                border: 1px solid #35bb93;
            }
            QPushButton#primary:hover {
                background: #28bc90;
            }
            QPushButton#danger {
                background: #a73c52;
                border: 1px solid #c4576e;
            }
            QPushButton#danger:hover {
                background: #bd4f67;
            }
            QPushButton#ghost {
                background: #17233e;
                border: 1px solid #2f4676;
            }
            QGroupBox {
                border: 1px solid #2f4676;
                border-radius: 12px;
                margin-top: 12px;
                padding-top: 16px;
                background: #111a2f;
                font-weight: 600;
            }
            QGroupBox::title {
                left: 12px;
                padding: 0 6px;
                color: #9db3e0;
            }
            QComboBox, QSpinBox {
                background: #16213b;
                border: 1px solid #35558f;
                border-radius: 8px;
                padding: 6px;
                min-height: 20px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #35558f;
                background: #182645;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #2ec59a;
                border: 1px solid #63d9b7;
                width: 20px;
                margin: -8px 0;
                border-radius: 10px;
            }
            QStatusBar {
                background: #0e1629;
                border-top: 1px solid #243657;
                color: #9eb2dc;
            }
            """
        )

    def _build_selection_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Choose A Fan")
        title.setObjectName("title")
        subtitle = QLabel("Your devices are loaded on launch. Pick one to open live controls.")
        subtitle.setObjectName("subtitle")

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(12)

        self.device_list = QListWidget()
        self.device_list.itemDoubleClicked.connect(self.open_selected_fan)

        actions = QHBoxLayout()
        self.refresh_devices_btn = QPushButton("Refresh Devices")
        self.open_controls_btn = QPushButton("Open Controls")
        self.open_controls_btn.setObjectName("primary")
        self.open_controls_btn.setEnabled(False)

        actions.addWidget(self.refresh_devices_btn)
        actions.addStretch(1)
        actions.addWidget(self.open_controls_btn)

        card_layout.addWidget(self.device_list)
        card_layout.addLayout(actions)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(card, 1)

        self.device_list.itemSelectionChanged.connect(self._on_device_selection_changed)
        self.refresh_devices_btn.clicked.connect(self.load_devices)
        self.open_controls_btn.clicked.connect(self.open_selected_fan)

        return page

    def _build_control_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        head = QFrame()
        head.setObjectName("card")
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(16, 14, 16, 14)

        self.selected_fan_label = QLabel("No fan selected")
        self.selected_fan_label.setObjectName("title")
        self.selected_fan_label.setStyleSheet("font-size: 28px;")
        self.selected_fan_state = QLabel("State unknown")
        self.selected_fan_state.setObjectName("subtitle")

        head_left = QVBoxLayout()
        head_left.addWidget(self.selected_fan_label)
        head_left.addWidget(self.selected_fan_state)

        self.back_btn = QPushButton("Back To Fans")
        self.back_btn.setObjectName("ghost")
        self.refresh_state_btn = QPushButton("Refresh State")

        right_buttons = QVBoxLayout()
        right_buttons.addWidget(self.refresh_state_btn)
        right_buttons.addWidget(self.back_btn)

        head_layout.addLayout(head_left, 1)
        head_layout.addLayout(right_buttons)

        quick = QGroupBox("Quick Actions")
        quick_layout = QHBoxLayout(quick)
        self.power_btn = QPushButton("Turn Power ON")
        self.power_btn.setObjectName("primary")
        quick_layout.addWidget(self.power_btn)

        speed_box = QGroupBox("Speed")
        speed_layout = QHBoxLayout(speed_box)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(1)
        self.speed_slider.setMaximum(6)
        self.speed_slider.setValue(1)
        self.speed_value = QLabel("1")
        self.speed_apply_btn = QPushButton("Set Speed To 1")
        speed_layout.addWidget(self.speed_slider, 1)
        speed_layout.addWidget(self.speed_value)
        speed_layout.addWidget(self.speed_apply_btn)

        mode_box = QGroupBox("Modes")
        mode_layout = QHBoxLayout(mode_box)
        self.sleep_btn = QPushButton("Turn Sleep ON")
        self.led_btn = QPushButton("Turn LED ON")
        self.timer_combo = QComboBox()
        self.timer_combo.addItems(["0", "1", "2", "3", "4"])
        self.timer_apply_btn = QPushButton("Set Timer (Current: 0h)")
        mode_layout.addWidget(self.sleep_btn)
        mode_layout.addWidget(self.led_btn)
        mode_layout.addWidget(self.timer_combo)
        mode_layout.addWidget(self.timer_apply_btn)

        layout.addWidget(head)
        layout.addWidget(quick)
        layout.addWidget(speed_box)
        layout.addWidget(mode_box)
        layout.addStretch(1)

        self.back_btn.clicked.connect(self.go_to_selection)
        self.refresh_state_btn.clicked.connect(self.refresh_selected_state)
        self.power_btn.clicked.connect(self.toggle_power)
        self.speed_slider.valueChanged.connect(self._on_speed_slider_changed)
        self.speed_apply_btn.clicked.connect(
            lambda: self.send_command({"speed": int(self.speed_slider.value())})
        )
        self.sleep_btn.clicked.connect(self.toggle_sleep)
        self.led_btn.clicked.connect(self.toggle_led)
        self.timer_apply_btn.clicked.connect(
            lambda: self.send_command({"timer": int(self.timer_combo.currentText())})
        )

        return page

    def _on_speed_slider_changed(self, value: int) -> None:
        self.speed_value.setText(str(value))
        self.speed_apply_btn.setText(f"Set Speed To {value}")

    def _set_button_variant(self, button: QPushButton, variant: str) -> None:
        button.setObjectName(variant)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _on_device_selection_changed(self) -> None:
        self.open_controls_btn.setEnabled(bool(self.device_list.selectedItems()))

    def _extract_device_state(self, response: Dict[str, Any], device_id: str) -> Dict[str, Any]:
        message = response.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Unexpected state response format")
        device_state = message.get("device_state")
        if isinstance(device_state, list):
            for item in device_state:
                if isinstance(item, dict) and item.get("device_id") == device_id:
                    return item
            if device_state and isinstance(device_state[0], dict):
                return device_state[0]
        if isinstance(device_state, dict):
            return device_state
        raise RuntimeError("Device state not found")

    def _apply_state_to_controls(self, state: Dict[str, Any]) -> None:
        self.current_state = dict(state)
        is_online = bool(state.get("is_online", False))
        power = bool(state.get("power", False))
        speed = int(state.get("last_recorded_speed", 1) or 1)
        sleep = bool(state.get("sleep_mode", False))
        led = bool(state.get("led", False))
        timer_hours = int(state.get("timer_hours", 0) or 0)

        self.selected_fan_state.setText(
            f"Online: {'Yes' if is_online else 'No'}  |  "
            f"Power: {'On' if power else 'Off'}  |  "
            f"Speed: {speed}"
        )
        self.speed_slider.setValue(max(1, min(6, speed)))
        self.power_btn.setText("Turn Power OFF" if power else "Turn Power ON")
        self._set_button_variant(self.power_btn, "danger" if power else "primary")
        self.sleep_btn.setText("Turn Sleep OFF" if sleep else "Turn Sleep ON")
        self.led_btn.setText("Turn LED OFF" if led else "Turn LED ON")
        self.timer_combo.setCurrentText(str(timer_hours if timer_hours in [0, 1, 2, 3, 4] else 0))
        self.timer_apply_btn.setText(f"Set Timer (Current: {timer_hours}h)")

    def _selected_device_id(self) -> str:
        if not self.selected_device or not self.selected_device.get("device_id"):
            raise RuntimeError("No fan selected")
        return str(self.selected_device["device_id"])

    def _run_action(self, message: str, fn: Callable[[], Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        self.status.showMessage(message)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = fn()
            self.status.showMessage("Done", 3000)
            return result
        except Exception as exc:  # pylint: disable=broad-except
            self.status.showMessage("Request failed", 5000)
            QMessageBox.critical(self, "Request Failed", str(exc))
            return None
        finally:
            QApplication.restoreOverrideCursor()

    def load_devices(self) -> None:
        result = self._run_action("Loading fans...", self.client.list_devices)
        if result is None:
            return

        message = result.get("message", {})
        devices = message.get("devices_list", []) if isinstance(message, dict) else []
        if not isinstance(devices, list):
            devices = []

        self.devices = [item for item in devices if isinstance(item, dict)]

        online_by_id: Dict[str, bool] = {}
        try:
            state_response = self.client.get_device_state("all")
            state_message = state_response.get("message", {})
            raw_state = state_message.get("device_state", []) if isinstance(state_message, dict) else []
            state_entries = raw_state if isinstance(raw_state, list) else [raw_state]
            for entry in state_entries:
                if isinstance(entry, dict):
                    device_id = entry.get("device_id")
                    if isinstance(device_id, str):
                        online_by_id[device_id] = bool(entry.get("is_online", False))
        except Exception:
            online_by_id = {}

        self.device_list.clear()

        for fan in self.devices:
            name = fan.get("name", "Unnamed Fan")
            room = fan.get("room", "Unknown Room")
            device_id = fan.get("device_id", "")
            is_online = online_by_id.get(device_id)
            if is_online is True:
                status_label = "ONLINE"
            elif is_online is False:
                status_label = "OFFLINE"
            else:
                status_label = "UNKNOWN"
            text = f"{name}  |  {room}  |  {status_label}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, fan)
            if is_online is True:
                item.setForeground(QColor("#93ffd9"))
            elif is_online is False:
                item.setForeground(QColor("#ff9cb0"))
            self.device_list.addItem(item)

        self.open_controls_btn.setEnabled(self.device_list.count() > 0)
        if self.device_list.count() > 0:
            self.device_list.setCurrentRow(0)
        self.status.showMessage(f"Loaded {len(self.devices)} fan(s)", 4000)

    def open_selected_fan(self) -> None:
        item = self.device_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Select Fan", "Choose a fan to continue.")
            return

        fan = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(fan, dict):
            QMessageBox.warning(self, "Selection Error", "Invalid fan selection.")
            return

        self.selected_device = fan
        fan_name = fan.get("name", "Unnamed Fan")
        room = fan.get("room", "Unknown Room")
        self.selected_fan_label.setText(f"{fan_name}")
        self.selected_fan_state.setText(f"{room} | Loading latest state...")

        self.refresh_selected_state(switch_page=True)

    def refresh_selected_state(self, switch_page: bool = False) -> None:
        if not self.selected_device:
            return
        device_id = self._selected_device_id()
        result = self._run_action(
            "Fetching latest state...",
            lambda: self.client.get_device_state(device_id),
        )
        if result is None:
            return

        state = self._extract_device_state(result, device_id)
        self._apply_state_to_controls(state)
        local_ip = self.client.get_local_ip(device_id)
        if local_ip:
            self.status.showMessage(f"Local control ready: {local_ip}:{self.client._command_port}", 4000)
        if switch_page:
            self.stack.setCurrentWidget(self.control_page)

    def send_command(self, command: Dict[str, Any]) -> None:
        if not self.selected_device:
            return
        device_id = self._selected_device_id()
        result = self._run_action(
            "Sending local UDP command...",
            lambda: self.client.send_local_command(device_id, command),
        )
        if result is None:
            return

        # Avoid extra API quota usage: update UI state optimistically.
        updated_state = dict(self.current_state)
        for key, value in command.items():
            if key == "power":
                updated_state["power"] = bool(value)
            elif key == "speed":
                updated_state["last_recorded_speed"] = int(value)
            elif key == "sleep":
                updated_state["sleep_mode"] = bool(value)
            elif key == "led":
                updated_state["led"] = bool(value)
            elif key == "timer":
                updated_state["timer_hours"] = int(value)
        if updated_state:
            self._apply_state_to_controls(updated_state)
        target_ip = result.get("target_ip")
        if isinstance(target_ip, str):
            self.status.showMessage(f"Command sent locally to {target_ip}:{self.client._command_port}", 3500)

    def toggle_sleep(self) -> None:
        enabled = not bool(self.current_state.get("sleep_mode", False))
        self.send_command({"sleep": enabled})

    def toggle_led(self) -> None:
        enabled = not bool(self.current_state.get("led", False))
        self.send_command({"led": enabled})

    def toggle_power(self) -> None:
        enabled = not bool(self.current_state.get("power", False))
        self.send_command({"power": enabled})

    def go_to_selection(self) -> None:
        self.stack.setCurrentWidget(self.selection_page)
        self.status.showMessage("Choose another fan", 2000)


def build_client() -> AtombergClient:
    env = load_env(Path(__file__).with_name(".env"))
    api_key = env.get("ATOMBERG_API_KEY", "")
    refresh_token = env.get("ATOMBERG_REFRESH_TOKEN", "")
    base_url = env.get("ATOMBERG_BASE_URL", "https://api.developer.atomberg-iot.com")

    if not api_key or not refresh_token:
        raise RuntimeError("ATOMBERG_API_KEY and ATOMBERG_REFRESH_TOKEN must be set in .env")

    return AtombergClient(api_key=api_key, refresh_token=refresh_token, base_url=base_url)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Atomberg fan controller (GUI + CLI)")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("gui", help="Launch the desktop GUI")
    sub.add_parser("devices", help="List devices in your account")

    state = sub.add_parser("state", help="Get state for one device or all")
    state.add_argument("device_id", help="Device ID or 'all'")

    on = sub.add_parser("on", help="Turn fan on")
    on.add_argument("device_id", help="Device ID")

    off = sub.add_parser("off", help="Turn fan off")
    off.add_argument("device_id", help="Device ID")

    speed = sub.add_parser("speed", help="Set speed (1-6)")
    speed.add_argument("device_id", help="Device ID")
    speed.add_argument("value", type=int, choices=[1, 2, 3, 4, 5, 6], help="Speed")

    sleep = sub.add_parser("sleep", help="Enable/disable sleep mode")
    sleep.add_argument("device_id", help="Device ID")
    sleep.add_argument("mode", choices=["on", "off"], help="Sleep mode")

    timer = sub.add_parser("timer", help="Set timer: 0(off),1,2,3,4(=6hrs)")
    timer.add_argument("device_id", help="Device ID")
    timer.add_argument("value", type=int, choices=[0, 1, 2, 3, 4], help="Timer slot")

    led = sub.add_parser("led", help="Set LED on/off")
    led.add_argument("device_id", help="Device ID")
    led.add_argument("mode", choices=["on", "off"], help="LED mode")

    raw = sub.add_parser("raw", help="Send raw command JSON")
    raw.add_argument("device_id", help="Device ID")
    raw.add_argument(
        "command_json",
        help="JSON object like '{\"speed\":5}' or '{\"power\":true}'",
    )

    return parser


def run_cli(args: argparse.Namespace, client: AtombergClient) -> int:
    client.start_udp_listener()
    if args.cmd == "devices":
        out = client.list_devices()
    elif args.cmd == "state":
        out = client.get_device_state(args.device_id)
    elif args.cmd == "on":
        out = client.send_local_command(args.device_id, {"power": True})
    elif args.cmd == "off":
        out = client.send_local_command(args.device_id, {"power": False})
    elif args.cmd == "speed":
        out = client.send_local_command(args.device_id, {"speed": args.value})
    elif args.cmd == "sleep":
        out = client.send_local_command(args.device_id, {"sleep": args.mode == "on"})
    elif args.cmd == "timer":
        out = client.send_local_command(args.device_id, {"timer": args.value})
    elif args.cmd == "led":
        out = client.send_local_command(args.device_id, {"led": args.mode == "on"})
    elif args.cmd == "raw":
        try:
            command_payload = json.loads(args.command_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON for raw command: {exc}") from exc
        if not isinstance(command_payload, dict):
            raise RuntimeError("Raw command JSON must be an object")
        out = client.send_local_command(args.device_id, command_payload)
    else:
        raise RuntimeError(f"Unknown command: {args.cmd}")

    print(json.dumps(out, indent=2))
    return 0


def run_gui(client: AtombergClient) -> int:
    app = QApplication(sys.argv)
    window = AtombergWindow(client)
    window.show()
    return app.exec()


def main() -> int:
    parser = build_cli_parser()
    args = parser.parse_args()
    client = build_client()

    if args.cmd is None or args.cmd == "gui":
        return run_gui(client)

    return run_cli(args, client)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)