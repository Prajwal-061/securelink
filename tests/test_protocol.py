import socket
import threading

from src.protocol import HEADER_LEN, PacketType, build_packet, parse_header, recv_exact, recv_packet


def test_build_and_parse_header() -> None:
    payload = b"hello"
    packet = build_packet(PacketType.TXT, payload, flags=1, message_id=123)
    header = parse_header(packet[:HEADER_LEN])

    assert header.packet_type == PacketType.TXT
    assert header.flags == 1
    assert header.message_id == 123
    assert header.payload_size == len(payload)


def test_recv_exact_reads_full_bytes() -> None:
    s1, s2 = socket.socketpair()

    def writer() -> None:
        s1.sendall(b"abcd")

    t = threading.Thread(target=writer)
    t.start()
    data = recv_exact(s2, 4)
    t.join()

    assert data == b"abcd"
    s1.close()
    s2.close()


def test_recv_packet_roundtrip() -> None:
    s1, s2 = socket.socketpair()
    out_packet = build_packet(PacketType.TXT, b"hi")
    s1.sendall(out_packet)

    header, payload = recv_packet(s2)
    assert header.packet_type == PacketType.TXT
    assert payload == b"hi"

    s1.close()
    s2.close()
