from queue import Queue

from src.logic import LogicController


def test_handle_hello_remaps_ephemeral_peer_to_listen_port() -> None:
    logic = LogicController(username="alpha", listen_port=5000)
    old_peer_id = "127.0.0.1:42000"

    class NetStub:
        def __init__(self) -> None:
            self.remaps = []

        def remap_peer(self, old_peer_id: str, new_peer_id: str) -> None:
            self.remaps.append((old_peer_id, new_peer_id))

    logic.net = NetStub()
    logic.peers[old_peer_id] = {"ip": "127.0.0.1", "port": 42000, "user": "bravo"}
    logic.peer_last_seen[old_peer_id] = 1.0

    canonical = logic._handle_hello(old_peer_id, 'HELLO:{"user":"bravo","port":5001}')

    assert canonical == "127.0.0.1:5001"
    assert logic.peer_aliases[old_peer_id] == "127.0.0.1:5001"
    assert logic.peers["127.0.0.1:5001"]["user"] == "bravo"
    assert ("127.0.0.1:42000", "127.0.0.1:5001") in logic.net.remaps


def test_canonical_peer_id_uses_explicit_alias() -> None:
    logic = LogicController(username="alpha", listen_port=5000)
    logic.peer_aliases["127.0.0.1:42000"] = "127.0.0.1:5001"

    assert logic._canonical_peer_id("127.0.0.1:42000") == "127.0.0.1:5001"
    assert logic._canonical_peer_id("127.0.0.1:5002") == "127.0.0.1:5002"
