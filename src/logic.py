import json
import logging
import os
import threading
import time
from pathlib import Path
from queue import Queue

from .crypto_vault import decrypt, encrypt, get_or_create_key
from .database import ChatDatabase
from .network import TcpEngine, UdpDiscovery
from .protocol import CHUNK_SIZE, Flags, PacketType

logger = logging.getLogger(__name__)


class LogicController:
    def __init__(
        self,
        username: str,
        listen_host: str = "0.0.0.0",
        listen_port: int = 5000,
        profile_dir: str = "data/profiles/default",
        key_path: str | None = None,
    ):
        self.username = username
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.received_dir = self.profile_dir / "received"
        self.received_dir.mkdir(parents=True, exist_ok=True)

        self.logic_in_queue: Queue = Queue()
        self.recv_queue: Queue = Queue()
        self.ui_queue: Queue = Queue()
        self.file_progress_queue: Queue = Queue()

        self.db = ChatDatabase(str(self.profile_dir / "chat.db"))
        self.key = get_or_create_key(key_path or str(self.profile_dir / "seclink.key"))
        self.net = TcpEngine(self.recv_queue)
        self.discovery = UdpDiscovery(username, listen_port, self.logic_in_queue)

        self.peers: dict[str, dict] = {}
        self.peer_last_seen: dict[str, float] = {}
        self.outbound_targets: dict[str, tuple[str, int]] = {}
        self.peer_aliases: dict[str, str] = {}
        self.ack_events: dict[tuple[str, int], threading.Event] = {}
        self._ack_lock = threading.Lock()
        self._msg_counter = 0

    def start(self) -> None:
        logger.info("Logic start username=%s host=%s port=%s", self.username, self.listen_host, self.listen_port)
        self.net.start_server(self.listen_host, self.listen_port)
        self.discovery.start_broadcaster()
        self.discovery.start_listener()

        threading.Thread(target=self._process_logic_commands, daemon=True).start()
        threading.Thread(target=self._process_incoming_packets, daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        threading.Thread(target=self._peer_prune_loop, daemon=True).start()

    def _process_logic_commands(self) -> None:
        while True:
            cmd = self.logic_in_queue.get()
            command = cmd.get("cmd")
            logger.debug("Logic command received: %s", command)

            if command == "peer_seen":
                peer = cmd["peer"]
                if int(peer.get("port", 0)) == self.listen_port and peer.get("user") == self.username:
                    continue
                peer_id = f"{peer['ip']}:{peer['port']}"
                self.peers[peer_id] = peer
                self.peer_last_seen[peer_id] = time.time()
                logger.debug("Peer seen %s", peer_id)
                self.ui_queue.put({"event": "peer_update", "peers": list(self.peers.values())})

            elif command == "connect_peer":
                ip = cmd["ip"]
                port = int(cmd["port"])
                self._connect_with_backoff(ip, port)

            elif command == "send_text":
                logger.debug("Sending text cmd peer=%s", cmd.get("peer_id"))
                self._send_text(
                    peer_id=cmd["peer_id"],
                    message=cmd["message"],
                    encrypted=bool(cmd.get("encrypted", True)),
                    self_destruct_seconds=int(cmd.get("self_destruct_seconds", 0)),
                )

            elif command == "send_file":
                logger.debug("Sending file cmd peer=%s file=%s", cmd.get("peer_id"), cmd.get("file_path"))
                self._send_file(
                    peer_id=cmd["peer_id"],
                    file_path=cmd["file_path"],
                    encrypted=bool(cmd.get("encrypted", True)),
                )

            elif command == "delete_msg":
                msg_id = int(cmd["id"])
                self.db.delete_message(msg_id)
                logger.debug("Deleted message from DB message_id=%s", msg_id)

    def _process_incoming_packets(self) -> None:
        while True:
            peer_id, header, payload = self.recv_queue.get()

            if header == "error":
                self.ui_queue.put({"event": "status", "text": f"Network error from {peer_id}: {payload.decode('utf-8', errors='ignore')}"})
                logger.warning("Incoming network error peer=%s payload=%s", peer_id, payload)
                if peer_id in self.outbound_targets:
                    ip, port = self.outbound_targets[peer_id]
                    threading.Thread(target=self._reconnect_with_backoff, args=(ip, port), daemon=True).start()
                continue

            peer_id = self._canonical_peer_id(peer_id)
            self.peer_last_seen[peer_id] = time.time()
            logger.debug("Packet received peer=%s type=%s", peer_id, header.packet_type.name)

            if header.packet_type == PacketType.TXT:
                msg_bytes = payload
                if header.flags & Flags.ENCRYPTED:
                    try:
                        msg_bytes = decrypt(payload, self.key)
                    except Exception as exc:
                        self.ui_queue.put({"event": "status", "text": f"Decrypt failed: {exc}"})
                        logger.warning("Text decrypt failed peer=%s error=%s", peer_id, exc)
                        continue
                msg_obj = json.loads(msg_bytes.decode("utf-8"))
                text = msg_obj.get("message", "")
                self.db.save_message(
                    message_id=header.message_id,
                    peer_id=peer_id,
                    sender=msg_obj.get("sender", "peer"),
                    message=text,
                    timestamp_ms=header.timestamp_ms,
                    self_destruct_seconds=int(msg_obj.get("self_destruct_seconds", 0)),
                )
                self.ui_queue.put(
                    {
                        "event": "message",
                        "peer_id": peer_id,
                        "message_id": header.message_id,
                        "sender": msg_obj.get("sender", "peer"),
                        "message": text,
                        "timestamp_ms": header.timestamp_ms,
                        "self_destruct_seconds": int(msg_obj.get("self_destruct_seconds", 0)),
                    }
                )
                logger.debug("Text message queued for UI peer=%s message_id=%s", peer_id, header.message_id)

            elif header.packet_type == PacketType.FIL:
                fil_payload = payload
                if header.flags & Flags.ENCRYPTED:
                    try:
                        fil_payload = decrypt(payload, self.key)
                    except Exception as exc:
                        self.ui_queue.put({"event": "status", "text": f"File decrypt failed: {exc}"})
                        logger.warning("File decrypt failed peer=%s error=%s", peer_id, exc)
                        continue
                try:
                    file_meta_raw, chunk = fil_payload.split(b"\n", 1)
                    meta = json.loads(file_meta_raw.decode("utf-8"))
                except Exception:
                    continue

                file_name = meta["name"]
                seq = int(meta["seq"])
                done = bool(meta.get("last", False))
                tmp_path = str(self.received_dir / f"{file_name}.tmp")
                with open(tmp_path, "ab") as f:
                    f.write(chunk)

                ack_payload = f"SEQ:{seq}".encode("utf-8")
                self.net.send_packet(peer_id, PacketType.ACK, ack_payload, flags=Flags.IS_ACK)
                logger.debug("ACK sent peer=%s seq=%s", peer_id, seq)

                if done:
                    final_path = str(self.received_dir / file_name)
                    os.replace(tmp_path, final_path)
                    self.ui_queue.put({"event": "status", "text": f"Received file: {final_path}"})
                    self._record_file_event(peer_id, sender="peer", file_name=file_name, direction="received")
                    logger.info("File received peer=%s path=%s", peer_id, final_path)

            elif header.packet_type == PacketType.ACK:
                text = payload.decode("utf-8", errors="ignore")
                self.ui_queue.put({"event": "ack", "peer_id": peer_id, "payload": text})
                if text.startswith("SEQ:"):
                    try:
                        seq = int(text.split(":", 1)[1])
                        self._signal_ack(peer_id, seq)
                        logger.debug("ACK signaled peer=%s seq=%s", peer_id, seq)
                    except ValueError:
                        pass

            elif header.packet_type == PacketType.META:
                meta_text = payload.decode("utf-8", errors="ignore")
                if meta_text == "PING":
                    self.net.send_packet(peer_id, PacketType.META, b"PONG")
                    logger.debug("PONG sent to %s", peer_id)
                elif meta_text == "PONG":
                    logger.debug("PONG received from %s", peer_id)
                elif meta_text.startswith("HELLO:"):
                    peer_id = self._handle_hello(peer_id, meta_text)

    def _send_text(
        self,
        peer_id: str,
        message: str,
        encrypted: bool,
        self_destruct_seconds: int,
    ) -> None:
        resolved_peer_id = self._ensure_peer_connection(peer_id)
        if not resolved_peer_id:
            self.ui_queue.put(
                {
                    "event": "status",
                    "text": f"Message not sent. Could not connect to {peer_id}.",
                }
            )
            logger.warning("Text send aborted; no active connection peer=%s", peer_id)
            return

        message_id = int(time.time() * 1000000)
        body = {
            "sender": self.username,
            "message": message,
            "self_destruct_seconds": self_destruct_seconds,
        }
        payload = json.dumps(body).encode("utf-8")
        flags = 0
        if encrypted:
            payload = encrypt(payload, self.key)
            flags |= Flags.ENCRYPTED
        if self_destruct_seconds > 0:
            flags |= Flags.SELF_DESTRUCT

        if not self.net.send_packet(resolved_peer_id, PacketType.TXT, payload, flags=flags, message_id=message_id):
            self.ui_queue.put(
                {
                    "event": "status",
                    "text": f"Message not sent. Peer offline: {resolved_peer_id}",
                }
            )
            logger.warning("Text send failed at socket layer peer=%s message_id=%s", resolved_peer_id, message_id)
            return

        logger.info("Text sent peer=%s message_id=%s encrypted=%s", resolved_peer_id, message_id, encrypted)
        self.db.save_message(
            message_id=message_id,
            peer_id=peer_id,
            sender=self.username,
            message=message,
            timestamp_ms=int(time.time() * 1000),
            self_destruct_seconds=self_destruct_seconds,
        )
        self.ui_queue.put(
            {
                "event": "message",
                "peer_id": peer_id,
                "message_id": message_id,
                "sender": self.username,
                "message": message,
                "timestamp_ms": int(time.time() * 1000),
                "self_destruct_seconds": self_destruct_seconds,
            }
        )

    def _send_file(self, peer_id: str, file_path: str, encrypted: bool) -> None:
        total = os.path.getsize(file_path)
        sent = 0
        seq = 0
        file_name = os.path.basename(file_path)

        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break

                seq += 1
                sent += len(chunk)
                is_last = sent >= total

                meta = {"name": file_name, "seq": seq, "last": is_last}
                payload = json.dumps(meta).encode("utf-8") + b"\n" + chunk
                flags = Flags.IS_LAST_CHUNK if is_last else 0
                if encrypted:
                    payload = encrypt(payload, self.key)
                    flags |= Flags.ENCRYPTED

                if not self._send_chunk_with_ack(
                    peer_id=peer_id,
                    seq=seq,
                    payload=payload,
                    flags=flags,
                ):
                    self.ui_queue.put(
                        {
                            "event": "status",
                            "text": f"File transfer warning: missing ACK for chunk {seq} to {peer_id}",
                        }
                    )
                    return

                self.file_progress_queue.put(
                    {
                        "peer_id": peer_id,
                        "file_name": file_name,
                        "sent": sent,
                        "total": total,
                        "percent": (sent / total * 100) if total else 100,
                    }
                )
                logger.debug("File chunk sent peer=%s file=%s seq=%s sent=%s/%s", peer_id, file_name, seq, sent, total)

            logger.info("File transfer completed peer=%s file=%s", peer_id, file_name)
            self._record_file_event(peer_id, sender=self.username, file_name=file_name, direction="sent")

    def _send_chunk_with_ack(self, peer_id: str, seq: int, payload: bytes, flags: int) -> bool:
        resolved_peer_id = self._ensure_peer_connection(peer_id)
        if not resolved_peer_id:
            logger.warning("Chunk send aborted; no active connection peer=%s seq=%s", peer_id, seq)
            return False

        attempts = 3
        for _ in range(attempts):
            if not self.net.send_packet(resolved_peer_id, PacketType.FIL, payload, flags=flags):
                continue
            if self._wait_for_ack(resolved_peer_id, seq, timeout_sec=2.0, retries=1):
                return True
            logger.debug("Chunk ACK retry peer=%s seq=%s", resolved_peer_id, seq)
        return False

    def _wait_for_ack(
        self,
        peer_id: str,
        seq: int,
        timeout_sec: float = 2.0,
        retries: int = 3,
    ) -> bool:
        for _ in range(retries):
            event = self._prepare_ack_event(peer_id, seq)
            if event.wait(timeout=timeout_sec):
                self._clear_ack_event(peer_id, seq)
                return True
        self._clear_ack_event(peer_id, seq)
        return False

    def _prepare_ack_event(self, peer_id: str, seq: int) -> threading.Event:
        with self._ack_lock:
            key = (peer_id, seq)
            event = self.ack_events.get(key)
            if event is None:
                event = threading.Event()
                self.ack_events[key] = event
            return event

    def _signal_ack(self, peer_id: str, seq: int) -> None:
        with self._ack_lock:
            event = self.ack_events.get((peer_id, seq))
        if event is not None:
            event.set()

    def _clear_ack_event(self, peer_id: str, seq: int) -> None:
        with self._ack_lock:
            self.ack_events.pop((peer_id, seq), None)

    def _connect_with_backoff(self, ip: str, port: int) -> None:
        threading.Thread(target=self._reconnect_with_backoff, args=(ip, port), daemon=True).start()

    def _reconnect_with_backoff(self, ip: str, port: int) -> None:
        delays = [0.0, 1.0, 2.0, 4.0, 8.0]
        for delay in delays:
            if delay > 0:
                time.sleep(delay)
            try:
                peer_id = self.net.connect_to(ip, port)
                self._send_hello(peer_id)
                self.outbound_targets[peer_id] = (ip, port)
                self.peer_last_seen[peer_id] = time.time()
                self.ui_queue.put({"event": "status", "text": f"Connected to {peer_id}"})
                logger.info("Connect success peer=%s", peer_id)
                return
            except Exception as exc:
                self.ui_queue.put(
                    {
                        "event": "status",
                        "text": f"Connect retry failed to {ip}:{port}: {exc}",
                    }
                )
                logger.warning("Connect retry failed ip=%s port=%s error=%s", ip, port, exc)

    def _heartbeat_loop(self) -> None:
        while True:
            for peer_id in self.net.get_connected_peers():
                try:
                    self.net.send_packet(peer_id, PacketType.META, b"PING")
                    logger.debug("PING sent to %s", peer_id)
                except Exception:
                    continue
            time.sleep(10)

    def _peer_prune_loop(self) -> None:
        timeout_sec = 30
        while True:
            now = time.time()
            stale = [p for p, ts in self.peer_last_seen.items() if (now - ts) > timeout_sec]
            for peer_id in stale:
                self.peer_last_seen.pop(peer_id, None)
                self.peers.pop(peer_id, None)
                self.ui_queue.put({"event": "status", "text": f"Peer timeout: {peer_id}"})
                self.ui_queue.put({"event": "peer_update", "peers": list(self.peers.values())})
                logger.warning("Peer timed out %s", peer_id)
            time.sleep(3)

    def _send_hello(self, peer_id: str) -> None:
        hello = json.dumps({"user": self.username, "port": self.listen_port})
        self.net.send_packet(peer_id, PacketType.META, f"HELLO:{hello}".encode("utf-8"))
        logger.debug("HELLO sent to %s", peer_id)

    def _handle_hello(self, peer_id: str, meta_text: str) -> str:
        try:
            payload = json.loads(meta_text.split(":", 1)[1])
            host = peer_id.rsplit(":", 1)[0]
            canonical_peer_id = f"{host}:{int(payload['port'])}"
        except Exception as exc:
            logger.warning("HELLO parse failed peer=%s error=%s", peer_id, exc)
            return peer_id

        self._register_canonical_peer(
            old_peer_id=peer_id,
            canonical_peer_id=canonical_peer_id,
            username=payload.get("user", "peer"),
        )
        logger.debug("HELLO received peer=%s canonical=%s", peer_id, canonical_peer_id)
        return canonical_peer_id

    def _register_canonical_peer(self, old_peer_id: str, canonical_peer_id: str, username: str) -> None:
        if old_peer_id != canonical_peer_id:
            self.net.remap_peer(old_peer_id, canonical_peer_id)
            self._move_peer_state(old_peer_id, canonical_peer_id)
            self.peer_aliases[old_peer_id] = canonical_peer_id

        host, port_text = canonical_peer_id.rsplit(":", 1)
        self.peers[canonical_peer_id] = {
            "ip": host,
            "port": int(port_text),
            "user": username,
        }
        self.peer_last_seen[canonical_peer_id] = time.time()
        self.ui_queue.put({"event": "peer_update", "peers": list(self.peers.values())})

    def _move_peer_state(self, old_peer_id: str, new_peer_id: str) -> None:
        if old_peer_id == new_peer_id:
            return

        peer = self.peers.pop(old_peer_id, None)
        if peer is not None:
            self.peers[new_peer_id] = peer

        last_seen = self.peer_last_seen.pop(old_peer_id, None)
        if last_seen is not None:
            self.peer_last_seen[new_peer_id] = last_seen

        target = self.outbound_targets.pop(old_peer_id, None)
        if target is not None:
            self.outbound_targets[new_peer_id] = target

        for alias, canonical in list(self.peer_aliases.items()):
            if canonical == old_peer_id:
                self.peer_aliases[alias] = new_peer_id

        with self._ack_lock:
            moved_events = {
                (new_peer_id, seq): event
                for (pid, seq), event in self.ack_events.items()
                if pid == old_peer_id
            }
            self.ack_events = {
                (pid, seq): event
                for (pid, seq), event in self.ack_events.items()
                if pid != old_peer_id
            }
            self.ack_events.update(moved_events)

    def _canonical_peer_id(self, peer_id: str) -> str:
        return self.peer_aliases.get(peer_id, peer_id)

    def _ensure_peer_connection(self, peer_id: str) -> str | None:
        canonical = self._canonical_peer_id(peer_id)
        connected = set(self.net.get_connected_peers())
        if canonical in connected:
            return canonical

        try:
            host, port_text = canonical.rsplit(":", 1)
            port = int(port_text)
        except ValueError:
            logger.warning("Invalid peer id format: %s", canonical)
            return None

        # Reuse any live socket from the same host when canonical id is not available.
        for connected_peer in connected:
            if connected_peer.startswith(f"{host}:"):
                self.peer_aliases[canonical] = connected_peer
                return connected_peer

        try:
            connected_peer_id = self.net.connect_to(host, port)
            self._send_hello(connected_peer_id)
            self.outbound_targets[connected_peer_id] = (host, port)
            self.peer_last_seen[connected_peer_id] = time.time()
            self.peer_aliases[canonical] = connected_peer_id
            logger.info("Connected on-demand peer=%s via=%s", canonical, connected_peer_id)
            return connected_peer_id
        except Exception as exc:
            logger.warning("On-demand connect failed peer=%s error=%s", canonical, exc)
            return None

    def _record_file_event(self, peer_id: str, sender: str, file_name: str, direction: str) -> None:
        message_id = int(time.time() * 1000000)
        text = f"[File {direction}] {file_name}"
        timestamp_ms = int(time.time() * 1000)
        self.db.save_message(
            message_id=message_id,
            peer_id=peer_id,
            sender=sender,
            message=text,
            timestamp_ms=timestamp_ms,
            self_destruct_seconds=0,
        )
        self.ui_queue.put(
            {
                "event": "message",
                "peer_id": peer_id,
                "message_id": message_id,
                "sender": sender,
                "message": text,
                "timestamp_ms": timestamp_ms,
                "self_destruct_seconds": 0,
            }
        )
