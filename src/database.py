import sqlite3
from pathlib import Path


class ChatDatabase:
    def __init__(self, db_path: str = "data/chat.db") -> None:
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER,
                    peer_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    message TEXT,
                    timestamp_ms INTEGER NOT NULL,
                    self_destruct_seconds INTEGER DEFAULT 0
                )
                """
            )

    def save_message(
        self,
        message_id: int,
        peer_id: str,
        sender: str,
        message: str,
        timestamp_ms: int,
        self_destruct_seconds: int = 0,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO chat_history
                (message_id, peer_id, sender, message, timestamp_ms, self_destruct_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    peer_id,
                    sender,
                    message,
                    timestamp_ms,
                    self_destruct_seconds,
                ),
            )

    def load_messages(self, peer_id: str, limit: int = 200) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT message_id, peer_id, sender, message, timestamp_ms, self_destruct_seconds
            FROM chat_history
            WHERE peer_id = ?
            ORDER BY timestamp_ms ASC
            LIMIT ?
            """,
            (peer_id, limit),
        )
        rows = cur.fetchall()
        return [
            {
                "message_id": r[0],
                "peer_id": r[1],
                "sender": r[2],
                "message": r[3],
                "timestamp_ms": r[4],
                "self_destruct_seconds": r[5],
            }
            for r in rows
        ]

    def delete_message(self, message_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM chat_history WHERE message_id = ?", (message_id,))
