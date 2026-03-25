import enum
import socket
import struct
import time
import zlib
from dataclasses import dataclass


MAGIC = b"SLNK"
VERSION = 0x01
HEADER_LEN = 32
CHUNK_SIZE = 4096


class PacketType(enum.IntEnum):
    TXT = 0x01
    FIL = 0x02
    DSC = 0x03
    ACK = 0x04
    META = 0x05
    ERR = 0x06


class Flags:
    ENCRYPTED = 1 << 0
    SELF_DESTRUCT = 1 << 1
    IS_ACK = 1 << 2
    IS_LAST_CHUNK = 1 << 3


@dataclass
class Header:
    version: int
    packet_type: PacketType
    flags: int
    message_id: int
    timestamp_ms: int
    payload_size: int
    checksum: int


def now_ms() -> int:
    return int(time.time() * 1000)


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def make_header(
    packet_type: PacketType,
    payload: bytes,
    flags: int = 0,
    message_id: int = 0,
    timestamp_ms: int | None = None,
) -> bytes:
    if timestamp_ms is None:
        timestamp_ms = now_ms()
    size = len(payload)
    checksum = crc32(payload)
    return struct.pack(
        "!4sBBBBQQII",
        MAGIC,
        VERSION,
        int(packet_type),
        flags & 0xFF,
        0,  # reserved
        message_id,
        timestamp_ms,
        size,
        checksum,
    )


def parse_header(raw: bytes) -> Header:
    if len(raw) != HEADER_LEN:
        raise ValueError(f"Invalid header length: {len(raw)}")
    magic, version, pkt_type, flags, _reserved, msg_id, ts, size, checksum = struct.unpack(
        "!4sBBBBQQII", raw
    )
    if magic != MAGIC:
        raise ValueError("Invalid magic")
    if version != VERSION:
        raise ValueError(f"Unsupported version: {version}")
    try:
        pkt_enum = PacketType(pkt_type)
    except ValueError as exc:
        raise ValueError(f"Unknown packet type: {pkt_type}") from exc
    return Header(
        version=version,
        packet_type=pkt_enum,
        flags=flags,
        message_id=msg_id,
        timestamp_ms=ts,
        payload_size=size,
        checksum=checksum,
    )


def build_packet(
    packet_type: PacketType,
    payload: bytes,
    flags: int = 0,
    message_id: int = 0,
    timestamp_ms: int | None = None,
) -> bytes:
    return make_header(packet_type, payload, flags, message_id, timestamp_ms) + payload


def recv_exact(sock: socket.socket, n: int) -> bytes:
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Socket closed while receiving data")
        data.extend(chunk)
    return bytes(data)


def recv_packet(sock: socket.socket) -> tuple[Header, bytes]:
    header_bytes = recv_exact(sock, HEADER_LEN)
    header = parse_header(header_bytes)
    payload = recv_exact(sock, header.payload_size)
    if crc32(payload) != header.checksum:
        raise ValueError("Checksum mismatch")
    return header, payload
