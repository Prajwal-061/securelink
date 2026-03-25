import argparse
import logging
from pathlib import Path

from .logic import LogicController
from .logging_setup import setup_logging
from .ui import SecureLinkUI


def _default_profile_dir(username: str, port: int) -> str:
    safe_user = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in username).strip("_") or "user"
    return str(Path("data") / "profiles" / f"{safe_user}_{port}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SecureLink LAN messenger")
    parser.add_argument("--username", default="user", help="Display name for discovery and chat")
    parser.add_argument("--port", type=int, default=5000, help="TCP listen port")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Runtime log verbosity",
    )
    parser.add_argument(
        "--log-file",
        default="logs/seclink.log",
        help="Path to runtime log file",
    )
    parser.add_argument(
        "--profile-dir",
        default=None,
        help="Per-instance storage directory for chat DB, key, and received files",
    )
    parser.add_argument(
        "--key-path",
        default="data/seclink.key",
        help="Shared key file path used for message/file encryption",
    )
    args = parser.parse_args()
    profile_dir = args.profile_dir or _default_profile_dir(args.username, args.port)

    setup_logging(level=args.log_level, log_file=args.log_file)
    logger = logging.getLogger(__name__)
    logger.info(
        "Starting SecureLink username=%s port=%s level=%s profile_dir=%s key_path=%s",
        args.username,
        args.port,
        args.log_level,
        profile_dir,
        args.key_path,
    )

    logic = LogicController(
        username=args.username,
        listen_port=args.port,
        profile_dir=profile_dir,
        key_path=args.key_path,
    )
    logic.start()

    ui = SecureLinkUI(logic)
    ui.run()


if __name__ == "__main__":
    main()
