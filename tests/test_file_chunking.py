import json
from pathlib import Path

from src.protocol import CHUNK_SIZE


def test_file_chunk_reassembly(tmp_path: Path) -> None:
    original = b"A" * (CHUNK_SIZE + 17) + b"B" * (CHUNK_SIZE // 2)
    src = tmp_path / "src.bin"
    src.write_bytes(original)

    recv_dir = tmp_path / "recv"
    recv_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = recv_dir / "out.bin.tmp"
    final_file = recv_dir / "out.bin"

    with src.open("rb") as f:
        seq = 0
        sent = 0
        total = len(original)
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            seq += 1
            sent += len(chunk)
            is_last = sent >= total

            payload = json.dumps({"name": "out.bin", "seq": seq, "last": is_last}).encode("utf-8") + b"\n" + chunk

            file_meta_raw, body = payload.split(b"\n", 1)
            meta = json.loads(file_meta_raw.decode("utf-8"))
            assert meta["seq"] == seq

            with tmp_file.open("ab") as out:
                out.write(body)

            if meta["last"]:
                tmp_file.replace(final_file)

    assert final_file.read_bytes() == original
