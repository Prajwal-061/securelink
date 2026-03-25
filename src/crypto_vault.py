from pathlib import Path

from cryptography.fernet import Fernet


def generate_key() -> bytes:
    return Fernet.generate_key()


def save_key(path: str, key: bytes) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(key)


def load_key(path: str) -> bytes:
    return Path(path).read_bytes()


def get_or_create_key(path: str) -> bytes:
    p = Path(path)
    if p.exists():
        return p.read_bytes()
    key = generate_key()
    save_key(path, key)
    return key


def encrypt(data: bytes, key: bytes) -> bytes:
    return Fernet(key).encrypt(data)


def decrypt(data: bytes, key: bytes) -> bytes:
    return Fernet(key).decrypt(data)
