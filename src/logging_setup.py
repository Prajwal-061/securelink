import logging
from pathlib import Path


def setup_logging(level: str = "INFO", log_file: str = "logs/seclink.log") -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(threadName)s | %(message)s"
    )

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Avoid duplicate handlers when app restarts in same interpreter session.
    if root.handlers:
        for h in list(root.handlers):
            root.removeHandler(h)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)
