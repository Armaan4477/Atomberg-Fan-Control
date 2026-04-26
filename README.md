# Atomberg Control

Desktop and CLI controller for Atomberg smart fans, built with Python and PyQt6.

This project uses the Atomberg developer API for account/device discovery and local UDP for low-latency fan commands on your LAN.

## What This Project Does

- Lists fans linked to your Atomberg account
- Launches a desktop GUI to control fan power, speed, LED, sleep mode, and timer
- Sends fan control commands locally over UDP for fast response
- Supports scriptable terminal usage through CLI commands
- Supports encrypted credential packaging for distributable builds

## Project Layout

- `main.py`: GUI, CLI, API client, UDP discovery, and command sender
- `encrypt_credentials.py`: encrypts `credentials.json` into `encrypted_credentials.txt`
- `credentials.json`: local credentials source (do not commit real secrets)
- `requirements.txt`: Python dependencies

## Requirements

- Python 3.8+
- macOS, Linux, or Windows
- Same local network as your Atomberg fans
- Atomberg developer credentials:
    - `ATOMBERG_API_KEY`
    - `ATOMBERG_REFRESH_TOKEN`
    - optional `ATOMBERG_BASE_URL` (defaults to `https://api.developer.atomberg-iot.com`)

Install dependencies:

```bash
pip install -r requirements.txt
```

## Credentials Setup

The app loads credentials in this order:

1. `encrypted_credentials.txt` (preferred, if present)
2. fallback credentials file (`.env` or `credentials.json`)

Accepted file formats:

- JSON object, for example:

```json
{
    "ATOMBERG_API_KEY": "your_api_key",
    "ATOMBERG_REFRESH_TOKEN": "your_refresh_token",
    "ATOMBERG_BASE_URL": "https://api.developer.atomberg-iot.com"
}
```

- `KEY=VALUE` style entries

### Encrypt Credentials (recommended for builds)

```bash
python encrypt_credentials.py
```

This creates `encrypted_credentials.txt`, which is what packaged builds should ship with.

## Run The App

Launch GUI (default):

```bash
python main.py
```

Equivalent explicit command:

```bash
python main.py gui
```

## CLI Usage

General format:

```bash
python main.py <command> [args]
```

Available commands:

- `devices`
- `state <device_id|all>`
- `on <device_id>`
- `off <device_id>`
- `speed <device_id> <1-6>`
- `sleep <device_id> <on|off>`
- `led <device_id> <on|off>`
- `timer <device_id> <0|1|2|3|4>`
- `raw <device_id> '<json_object>'`

Examples:

```bash
python main.py devices
python main.py state all
python main.py speed YOUR_DEVICE_ID 5
python main.py sleep YOUR_DEVICE_ID on
python main.py raw YOUR_DEVICE_ID '{"power": true, "speed": 3}'
```

## GUI Overview

The desktop app has two screens:

- Device selection screen: loads your account devices and shows online/offline status
- Control screen: sends local commands and updates UI state optimistically

Controls available in GUI:

- Power toggle
- Speed slider (1 to 6)
- Sleep toggle
- LED toggle
- Timer set (0 to 4)
- Manual state refresh

## Networking Notes

- Outbound command UDP port: `5600`
- Inbound beacon listener UDP port: `5625`
- Device IPs are discovered from fan beacons on the local network

If local IP discovery fails, commands cannot be sent locally until a beacon is received.

## Build macOS App (PyInstaller)

Install build tools:

```bash
pip install pyinstaller
```

Build:

```bash
pyinstaller --windowed \
    --name="Atomberg Control" \
    --add-data="encrypted_credentials.txt:." \
    main.py
```

Optional DMG creation (macOS):

```bash
brew install create-dmg
cd dist
create-dmg \
    --volname "Atomberg Control" \
    --window-pos 200 120 \
    --window-size 400 400 \
    --icon-size 128 \
    --icon "Atomberg Control.app" 100 150 \
    --app-drop-link 300 150 \
    --no-internet-enable \
    "Atomberg Control.dmg" \
    "Atomberg Control.app"
```

## Troubleshooting

### "Local fan IP not discovered yet"

- Ensure laptop and fan are on the same LAN
- Wait a few seconds for UDP beacons
- Check firewall rules for UDP `5600` and `5625`

### API/Auth Errors

- Verify `ATOMBERG_API_KEY` and `ATOMBERG_REFRESH_TOKEN`
- Confirm credentials file format is valid JSON or `KEY=VALUE`

### GUI Does Not Start

- Confirm PyQt6 is installed: `pip install -r requirements.txt`
- Run from terminal to inspect startup errors: `python main.py`

## Security Notes

- Treat API key and refresh token as secrets
- Do not commit real credentials to source control
- Prefer encrypted credentials in packaged artifacts

## Disclaimer

Unofficial third-party tool for Atomberg-compatible devices. Not affiliated with or endorsed by Atomberg Technologies.

## License

Licensed under the terms in [LICENSE](LICENSE).
