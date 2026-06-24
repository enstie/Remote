# Epson Projector Remote Control

A self-contained, local network remote control application for Epson projectors. No internet required—runs entirely on your local network.

## Features

✨ **Auto-Discovery**: Automatically finds your Epson projector on the local network via UDP broadcast  
🎮 **Full Control**: Power, source switching, navigation (D-pad), and menu controls  
📱 **Mobile-Optimized**: Beautiful glassmorphism UI designed for smartphone screens  
🔒 **Secure**: Works entirely locally—no cloud or external dependencies  
⚡ **Fast**: Responsive async command handling with no page reloads  

## Quick Start

### Prerequisites
- Python 3.7+
- Epson projector on your local network (port 3629 must be accessible)

### Installation & Usage

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application:**
   ```bash
   python epson_remote.py
   ```

3. **Access the interface:**
   - Open your browser and navigate to `http://localhost:5000`
   - Or from your phone/tablet: `http://<your-computer-ip>:5000`
   - Scan network happens automatically on startup

## Technical Details

### Network Discovery
The app broadcasts an Epson ESC/VP.net handshake on UDP port 3629 and listens for a response to determine the projector's IP address.

### Communication Protocol
Uses the **Epson ESC/VP21** protocol over TCP (port 3629):
- Handshake: `ESC/VP.net\x10\x03\x00\x00\x00\x00\x0d`
- Commands: ASCII text followed by `\r` carriage return
  - Power: `PWR ON`, `PWR OFF`
  - Source: `SOURCE 30` (HDMI 1), `SOURCE A0` (HDMI 2), `SOURCE 11` (Computer)
  - Navigation: `KEY <code>` (arrow keys, menu, back)

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/power/on` | POST | Turn projector on |
| `/api/power/off` | POST | Turn projector off |
| `/api/source/<id>` | POST | Switch to input source |
| `/api/key/<keycode>` | POST | Send navigation key |
| `/api/status` | GET | Get connection status |

## UI Layout

- **Power Controls**: Green (On) and Red (Off) buttons
- **D-Pad**: Circular navigation pad (Up, Down, Left, Right, Enter)
- **Navigation**: Back and Menu buttons
- **Sources**: Quick buttons for HDMI 1, HDMI 2, Computer

## Troubleshooting

**Projector not found?**
- Ensure projector is powered on and connected to the same network
- Check that port 3629 is not blocked by firewall
- Try connecting to your projector's IP manually to verify connectivity

**Commands not working?**
- Verify projector supports ESC/VP21 protocol (most Epson models do)
- Check projector logs/display for any error messages
- Try power cycling the projector

## Customization

Edit `epson_remote.py` to:
- Change the port (default 5000)
- Add more source inputs or keycodes
- Modify the UI styling
- Add support for additional Epson commands

## License

MIT
