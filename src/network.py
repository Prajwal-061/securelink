import json
import logging
import socket
import threading
import time
import errno
from dataclasses import dataclass
from pathlib import Path
from queue import Queue

from .protocol import PacketType, parse_header, build_packet, recv_packet


DISCOVERY_PORT = 5556
LOCAL_DISCOVERY_DIR = Path("/tmp/seclink_local_discovery")
LOCAL_DISCOVERY_TTL_SEC = 6
logger = logging.getLogger(__name__)


@dataclass
class Peer:
    peer_id: str
    ip: str
    port: int


class TcpEngine:
    # Retry configuration for mobile hotspot reliability
    SEND_RETRY_ATTEMPTS = 3
    SEND_RETRY_DELAY = 0.5  # seconds, exponential backoff
    SOCKET_TIMEOUT = 10.0  # seconds, for send/recv operations
    
    def __init__(self, recv_queue: Queue) -> None:
        self.recv_queue = recv_queue
        self.peers: dict[str, socket.socket] = {}
        self.send_queues: dict[str, Queue] = {}
        self._lock = threading.Lock()

    def start_server(self, host: str, port: int) -> None:
        def server_loop() -> None:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen(8)
            logger.info("TCP server listening on %s:%s", host, port)
            while True:
                conn, addr = server.accept()
                # Configure socket for reliability
                self._configure_socket(conn)
                peer_id = f"{addr[0]}:{addr[1]}"
                logger.info("Accepted TCP client %s", peer_id)
                self._register_peer(peer_id, conn)
                threading.Thread(
                    target=self._recv_loop, args=(peer_id, conn), daemon=True
                ).start()

        threading.Thread(target=server_loop, daemon=True).start()

    def connect_to(self, ip: str, port: int) -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Configure socket for reliability
        self._configure_socket(sock)
        logger.debug("Connecting to %s:%s", ip, port)
        sock.connect((ip, port))
        peer_id = f"{ip}:{port}"
        logger.info("Connected to peer %s", peer_id)
        self._register_peer(peer_id, sock)
        threading.Thread(target=self._recv_loop, args=(peer_id, sock), daemon=True).start()
        return peer_id

    def _configure_socket(self, sock: socket.socket) -> None:
        """Configure socket for mobile hotspot reliability."""
        try:
            # Enable TCP keepalive to detect stale connections
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            # Set timeout to detect hung connections
            sock.settimeout(self.SOCKET_TIMEOUT)
            
            # TCP_NODELAY: send immediately, don't wait for buffer to fill (for low-latency messages)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            logger.debug("Socket configured with keepalive enabled and timeout %.1fs", self.SOCKET_TIMEOUT)
        except Exception as exc:
            logger.warning("Failed to configure socket: %s", exc)

    def _register_peer(self, peer_id: str, sock: socket.socket) -> None:
        with self._lock:
            if peer_id in self.peers:
                try:
                    self.peers[peer_id].close()
                except OSError:
                    pass
            self.peers[peer_id] = sock
            send_queue = Queue()
            self.send_queues[peer_id] = send_queue
        threading.Thread(
            target=self._send_loop, args=(peer_id, sock, send_queue), daemon=True
        ).start()

    def _send_loop(self, peer_id: str, sock: socket.socket, send_queue: Queue) -> None:
        """Send loop with retry logic for mobile hotspot reliability."""
        while True:
            packet = send_queue.get()
            if packet is None:
                return
            
            # Try to send with retries for transient errors
            for attempt in range(1, self.SEND_RETRY_ATTEMPTS + 1):
                try:
                    sock.sendall(packet)
                    logger.debug("Sent packet to %s bytes=%s", peer_id, len(packet))
                    break  # Success, move to next packet
                except socket.timeout:
                    logger.warning(
                        "Send timeout to peer %s (attempt %d/%d)",
                        peer_id,
                        attempt,
                        self.SEND_RETRY_ATTEMPTS,
                    )
                    if attempt < self.SEND_RETRY_ATTEMPTS:
                        # Transient timeout, retry with exponential backoff
                        time.sleep(self.SEND_RETRY_DELAY * (2 ** (attempt - 1)))
                        continue
                    else:
                        # Final attempt failed, drop peer
                        logger.error("Send timeout exhausted for peer %s", peer_id)
                        self._drop_peer(peer_id)
                        return
                except OSError as exc:
                    # Check if it's a transient error that might recover
                    if attempt < self.SEND_RETRY_ATTEMPTS and self._is_transient_error(exc):
                        logger.warning(
                            "Send error to peer %s: %s (attempt %d/%d, retrying)",
                            peer_id,
                            exc,
                            attempt,
                            self.SEND_RETRY_ATTEMPTS,
                        )
                        time.sleep(self.SEND_RETRY_DELAY * (2 ** (attempt - 1)))
                        continue
                    else:
                        # Permanent error or final attempt failed
                        logger.error("Send failed for peer %s: %s", peer_id, exc)
                        self._drop_peer(peer_id)
                        return
            
    def _is_transient_error(self, exc: OSError) -> bool:
        """Check if the error might be transient (e.g., temporary network issue)."""
        # Transient errors that might recover with retry
        transient_codes = {
            # Connection issues that might recover
            errno.EAGAIN,      # Resource temporarily unavailable
            errno.EWOULDBLOCK, # Would block (non-blocking socket)
            errno.EINTR,       # Interrupted system call
            errno.ECONNRESET,  # Connection reset (might reconnect)
            errno.EPIPE,       # Broken pipe (might recover)
        }
        
        # Check if error code suggests transient nature
        if hasattr(exc, 'errno') and exc.errno in transient_codes:
            return True
        
        # Check by message content
        error_msg = str(exc).lower()
        if any(pattern in error_msg for pattern in ['temporarily', 'try again', 'reset', 'timeout']):
            return True
        
        return False

    def _recv_loop(self, peer_id: str, sock: socket.socket) -> None:
        """Receive loop with better error handling for mobile connectivity."""
        while True:
            try:
                header, payload = recv_packet(sock)
                self.recv_queue.put((peer_id, header, payload))
                logger.debug(
                    "Received packet from %s type=%s size=%s",
                    peer_id,
                    header.packet_type.name,
                    header.payload_size,
                )
            except socket.timeout:
                logger.debug("Recv timeout from peer %s (connection may be idle)", peer_id)
                # Timeout is not necessarily fatal on mobile networks; continue listening
                continue
            except Exception as exc:
                self.recv_queue.put((peer_id, "error", str(exc).encode("utf-8")))
                logger.warning("Receive loop ended for %s: %s", peer_id, exc)
                self._drop_peer(peer_id)
                return

    def _drop_peer(self, peer_id: str) -> None:
        with self._lock:
            sock = self.peers.pop(peer_id, None)
            q = self.send_queues.pop(peer_id, None)
        logger.info("Dropping peer %s", peer_id)
        if q is not None:
            try:
                q.put_nowait(None)
            except Exception:
                pass
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def send_packet(
        self,
        peer_id: str,
        packet_type: PacketType,
        payload: bytes,
        flags: int = 0,
        message_id: int = 0,
    ) -> bool:
        packet = build_packet(packet_type, payload, flags=flags, message_id=message_id)
        q = self.send_queues.get(peer_id)
        if q is not None:
            q.put(packet)
            return True
        else:
            logger.warning("send_packet skipped; peer not connected: %s", peer_id)
            return False

    def get_connected_peers(self) -> list[str]:
        with self._lock:
            return list(self.peers.keys())

    def remap_peer(self, old_peer_id: str, new_peer_id: str) -> None:
        if old_peer_id == new_peer_id:
            return

        with self._lock:
            sock = self.peers.pop(old_peer_id, None)
            send_queue = self.send_queues.pop(old_peer_id, None)
            if sock is None or send_queue is None:
                return

            prev_sock = self.peers.get(new_peer_id)
            prev_queue = self.send_queues.get(new_peer_id)
            self.peers[new_peer_id] = sock
            self.send_queues[new_peer_id] = send_queue

        if prev_queue is not None:
            try:
                prev_queue.put_nowait(None)
            except Exception:
                pass
        if prev_sock is not None and prev_sock is not sock:
            try:
                prev_sock.close()
            except OSError:
                pass
        logger.info("Remapped peer %s -> %s", old_peer_id, new_peer_id)


class UdpDiscovery:
    def __init__(self, username: str, tcp_port: int, logic_in_queue: Queue) -> None:
        self.username = username
        self.tcp_port = tcp_port
        self.logic_in_queue = logic_in_queue
        self.instance_id = f"{self.username}-{self.tcp_port}"
        self.local_record_path = LOCAL_DISCOVERY_DIR / f"{self.instance_id}.json"

    def start_broadcaster(self) -> None:
        def loop() -> None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            logger.info("UDP broadcaster started on port %s", DISCOVERY_PORT)
            while True:
                payload = {
                    "user": self.username,
                    "port": self.tcp_port,
                    "ts": int(time.time()),
                }
                data = json.dumps(payload).encode("utf-8")
                packet = build_packet(PacketType.DSC, data)
                sock.sendto(packet, ("255.255.255.255", DISCOVERY_PORT))
                self._write_local_heartbeat(payload)
                logger.debug("Broadcast discovery packet user=%s tcp_port=%s", self.username, self.tcp_port)
                time.sleep(2)

        threading.Thread(target=loop, daemon=True).start()

    def start_listener(self) -> None:
        def loop() -> None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", DISCOVERY_PORT))
            logger.info("UDP discovery listener bound on 0.0.0.0:%s", DISCOVERY_PORT)
            while True:
                packet, addr = sock.recvfrom(65535)
                try:
                    if len(packet) < 32:
                        continue
                    header = parse_header(packet[:32])
                    if header.packet_type != PacketType.DSC:
                        continue
                    payload = packet[32 : 32 + header.payload_size]
                    data = json.loads(payload.decode("utf-8"))
                    self.logic_in_queue.put(
                        {
                            "cmd": "peer_seen",
                            "peer": {
                                "ip": addr[0],
                                "port": int(data.get("port", 0)),
                                "user": data.get("user", "unknown"),
                            },
                        }
                    )
                    logger.debug("Discovered peer announce ip=%s port=%s", addr[0], data.get("port"))
                except Exception:
                    continue

        threading.Thread(target=loop, daemon=True).start()
        threading.Thread(target=self._local_registry_loop, daemon=True).start()

    def _write_local_heartbeat(self, payload: dict) -> None:
        try:
            LOCAL_DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
            self.local_record_path.write_text(json.dumps(payload), encoding="utf-8")
        except Exception as exc:
            logger.debug("Local discovery heartbeat write failed: %s", exc)

    def _local_registry_loop(self) -> None:
        logger.info("Localhost discovery registry watching %s", LOCAL_DISCOVERY_DIR)
        while True:
            try:
                LOCAL_DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
                now = time.time()
                for record_path in LOCAL_DISCOVERY_DIR.glob("*.json"):
                    if record_path == self.local_record_path:
                        continue

                    try:
                        record = json.loads(record_path.read_text(encoding="utf-8"))
                    except Exception:
                        continue

                    ts = int(record.get("ts", 0))
                    if (now - ts) > LOCAL_DISCOVERY_TTL_SEC:
                        continue

                    user = record.get("user", "unknown")
                    port = int(record.get("port", 0))
                    if user == self.username and port == self.tcp_port:
                        continue

                    self.logic_in_queue.put(
                        {
                            "cmd": "peer_seen",
                            "peer": {
                                "ip": "127.0.0.1",
                                "port": port,
                                "user": user,
                            },
                        }
                    )
                    logger.debug("Discovered localhost peer user=%s port=%s", user, port)
            except Exception as exc:
                logger.debug("Localhost discovery loop error: %s", exc)

            time.sleep(1)