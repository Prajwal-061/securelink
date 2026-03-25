# SecureLink Initial Checklist

## 1. Project Foundation
- [x] Create project structure (`src/`, `tests/`)
- [x] Add dependency list (`requirements.txt`)
- [x] Add basic run instructions (`README.md`)

## 2. Protocol Layer
- [x] Implement fixed-size header packet format (32 bytes)
- [x] Implement packet build/parse helpers
- [x] Implement `recv_exact` for precise socket reads
- [x] Implement checksum validation (`crc32`)

## 3. Security Layer
- [x] Implement key generation/loading
- [x] Implement payload encryption/decryption (Fernet)
- [x] Support encrypted packet payload flow

## 4. Network Layer
- [x] Implement TCP server skeleton
- [x] Implement TCP client connect helper
- [x] Implement per-peer sender queue thread
- [x] Implement UDP discovery broadcaster/listener (port 5556)
- [x] Add heartbeat (`PING`/`PONG`) life-checks
- [x] Add reconnect backoff policy

## 5. Data Layer
- [x] Implement sqlite chat history storage
- [x] Add message save/load helpers
- [x] Add delete/update helpers for self-destruct persistence

## 6. Logic Layer
- [x] Define queue contracts (`logic_in_queue`, `recv_queue`, etc.)
- [x] Implement text send/receive flow
- [x] Implement file chunk send flow (4 KB chunks)
- [x] Add basic ACK handling for file chunks
- [x] Add robust retry strategy for missing ACKs

## 7. UI Layer (CustomTkinter)
- [x] Build dashboard layout (sidebar, chat area, input area)
- [x] Display active peers from discovery events
- [x] Implement send text and send file actions
- [x] Add transfer progress bar and status bar
- [x] Add self-destruct visual countdown
- [ ] Add full chat bubble styling parity (mine/others themes)

## 8. QA & Packaging
- [x] Add protocol unit tests
- [x] Add encryption and file reassembly integration tests
- [x] Add PyInstaller spec/build scripts
- [x] Add firewall guidance docs/scripts

## 9. Immediate Next Execution Steps
- [x] Start coding the full baseline implementation
- [x] Run end-to-end multi-instance LAN verification
- [x] Harden error paths and reconnection behavior
