# SecureLink End-to-End LAN Runbook

## Objective

Verify discovery, peer connection, encrypted text, file transfer, self-destruct, and recovery behavior before live demo.

## Prerequisites

- Same LAN for all demo devices.
- Python env or built executable available on each device.
- Firewall ports open (`TCP 5000`, `UDP 5556`) or equivalent configured.

## Suggested Topology

- Device A: `--username alpha --port 5000`
- Device B: `--username bravo --port 5001`
- Device C: `--username charlie --port 5002`

## Start Commands (Python mode)

On each device:

```bash
source venv/bin/activate
python -m src.app --username <name> --port <port> --log-level DEBUG --log-file logs/<name>.log
```

## Test Sequence

1. Discovery
- Expected: peers appear in sidebar in <= 3 seconds.

2. Connect
- Select peer in sidebar.
- Expected: status shows connected peer.

3. Encrypted text
- Keep encryption ON.
- Send text both directions.
- Expected: message appears with timestamp and persists after restart.

4. Self-destruct message
- Enable self-destruct toggle.
- Send message.
- Expected: countdown visible; bubble disappears at 10s; DB delete command issued.

5. File transfer
- Send a binary file (~10 MB).
- Expected: progress updates; receive status confirms final file path; file checksum matches sender.

6. Drop/recovery
- Stop one receiver process mid-session.
- Expected: timeout/retry logs; reconnect attempts after process resumes.

## Log Review Checklist

- `Starting SecureLink ...`
- `UDP broadcaster started ...`
- `UDP discovery listener bound ...`
- `Connected to peer ...`
- `PING sent ...` and `PONG sent ...`
- `File transfer completed ...`
- No repeating decrypt/checksum errors

## Fast Troubleshooting

- No peers discovered:
  - Check same subnet and AP isolation off.
  - Verify UDP 5556 inbound allowed.

- Connect fails:
  - Verify target TCP port and local firewall rule.
  - Confirm process listens on that port.

- File transfer stalls:
  - Check ACK retry logs.
  - Verify both sides use same encryption key file if encryption is enabled.

- UI feels frozen:
  - Inspect logs for blocking exceptions.
  - Confirm no long operation is on main thread.
