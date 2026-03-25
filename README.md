# SecureLink

SecureLink is a LAN-first secure messenger prototype with:
- TCP transport for chat and file transfer
- UDP broadcast peer discovery
- Packetized binary protocol with fixed 32-byte header
- Payload encryption using Fernet
- SQLite local chat history
- CustomTkinter desktop UI

## Local Device / No Internet

SecureLink runs fully offline on a local device or LAN. It does not require internet access.

To run two local instances on the same machine:

```bash
python -m src.app --username alpha --port 5000
python -m src.app --username bravo --port 5001
```

By default, both instances now use a shared local key file at `data/seclink.key`, so encrypted chat works across local profiles.
If you need a different key, pass `--key-path <path>` on both instances.

## Quick Start

1. Create/activate a Python 3.10+ virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
python -m src.app --username alpha --port 5000 --log-level DEBUG --log-file logs/alpha.log
```

Alternative launcher:

```bash
python seclink_main.py --username alpha --port 5000 --log-level DEBUG --log-file logs/alpha.log
```

4. Start a second instance (same machine or LAN peer) and connect using discovered peers.

## Queue Contracts

- `logic_in_queue`: UI -> Logic commands
- `recv_queue`: Network -> Logic incoming packets
- `ui_queue`: Logic -> UI render/update events
- `file_progress_queue`: Network/Logic -> UI file progress updates

## Notes

- The protocol header is defined in `src/protocol.py`.
- Discovery uses UDP broadcast on port `5556`.
- Default TCP listen port is `5000` (configurable in `src/app.py`).

## Build (PyInstaller)

Linux:

```bash
chmod +x scripts/build_linux.sh
./scripts/build_linux.sh
```

Windows (Developer Command Prompt):

```bat
scripts\build_windows.bat
```

## Live Demo Readiness

- End-to-end LAN runbook: `docs/LAN_RUNBOOK.md`
- Firewall guidance: `docs/FIREWALL.md`

