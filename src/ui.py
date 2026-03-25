import datetime as dt
import logging
import tkinter as tk
import tkinter.font as tkfont
from queue import Empty
from tkinter import filedialog

import customtkinter as ctk

logger = logging.getLogger(__name__)


class SecureLinkUI:
    def __init__(self, logic) -> None:
        self.logic = logic
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.root = ctk.CTk()
        self.root.title("SecureLink")
        self.root.geometry("1140x720")

        self.colors = {
            "bg": "#0f172a",
            "panel": "#111827",
            "muted": "#1f2937",
            "accent": "#22d3ee",
            "accent_muted": "#0ea5e9",
            "text_subtle": "#9ca3af",
            "mine": "#0ea5e9",
            "peer": "#1f2937",
        }
        self.fonts = {
            "title": (self._font_family(["Manrope", "DejaVu Sans", "Arial", "TkDefaultFont"]), 22, "bold"),
            "subtitle": (
                self._font_family(["Manrope", "DejaVu Sans", "Arial", "TkDefaultFont"]),
                13,
                "normal",
            ),
            "body": (self._font_family(["Inter", "DejaVu Sans", "Arial", "TkDefaultFont"]), 13, "normal"),
            "chip": (self._font_family(["Inter", "DejaVu Sans", "Arial", "TkDefaultFont"]), 12, "bold"),
        }

        self.selected_peer_id: str | None = None
        self.peer_buttons: dict[str, ctk.CTkButton] = {}
        self.rendered_message_ids: set[int] = set()
        self.connected_peers: set[str] = set()
        self._progress_value = 0.0
        self._progress_target = 0.0
        self._progress_animating = False

        self.encrypted_var = tk.BooleanVar(value=True)
        self.self_destruct_var = tk.BooleanVar(value=False)

        self.root.configure(fg_color=self.colors["bg"])
        self._build_layout()
        self.root.after(120, self._poll_queues)

    def _font_family(self, candidates: list[str]) -> str:
        try:
            available = set(tkfont.families(self.root))
        except Exception:
            return "TkDefaultFont"
        for family in candidates:
            if family in available:
                return family
        return "TkDefaultFont"

    def _build_layout(self) -> None:
        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self.root, fg_color=self.colors["panel"], corner_radius=0, height=78)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_propagate(False)

        title_stack = ctk.CTkFrame(header, fg_color="transparent")
        title_stack.pack(side="left", padx=18, pady=12)
        ctk.CTkLabel(title_stack, text="SecureLink", font=self.fonts["title"]).pack(anchor="w")
        ctk.CTkLabel(
            title_stack,
            text="Encrypted LAN messenger with timed deletion",
            font=self.fonts["subtitle"],
            text_color=self.colors["text_subtle"],
        ).pack(anchor="w")

        chip_row = ctk.CTkFrame(header, fg_color="transparent")
        chip_row.pack(side="right", padx=18, pady=12)
        self._chip_enc = ctk.CTkLabel(
            chip_row,
            text="Encryption ON",
            font=self.fonts["chip"],
            fg_color=self.colors["muted"],
            corner_radius=14,
            padx=12,
            pady=6,
        )
        self._chip_enc.pack(side="left", padx=6)
        self._chip_port = ctk.CTkLabel(
            chip_row,
            text=f"Port {getattr(self.logic, 'listen_port', 5000)}",
            font=self.fonts["chip"],
            fg_color=self.colors["muted"],
            corner_radius=14,
            padx=12,
            pady=6,
        )
        self._chip_port.pack(side="left", padx=6)
        self._chip_user = ctk.CTkLabel(
            chip_row,
            text=f"User {self.logic.username}",
            font=self.fonts["chip"],
            fg_color=self.colors["muted"],
            corner_radius=14,
            padx=12,
            pady=6,
        )
        self._chip_user.pack(side="left", padx=6)

        self.sidebar = ctk.CTkFrame(self.root, width=260, corner_radius=0, fg_color=self.colors["panel"])
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        self.sidebar_title = ctk.CTkLabel(self.sidebar, text="Active Peers", font=self.fonts["title"])
        self.sidebar_title.pack(padx=12, pady=(14, 10), anchor="w")

        self.peers_frame = ctk.CTkScrollableFrame(self.sidebar, fg_color=self.colors["muted"])
        self.peers_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.main = ctk.CTkFrame(self.root, fg_color=self.colors["bg"])
        self.main.grid(row=1, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(0, weight=1)

        chat_shell = ctk.CTkFrame(self.main, fg_color=self.colors["panel"], corner_radius=16)
        chat_shell.grid(row=0, column=0, sticky="nsew", padx=16, pady=(16, 8))
        chat_shell.grid_rowconfigure(0, weight=1)
        chat_shell.grid_columnconfigure(0, weight=1)

        self.chat_text = ctk.CTkTextbox(
            chat_shell,
            corner_radius=10,
            fg_color=self.colors["panel"],
            text_color="#e5e7eb",
            wrap="word",
            font=self.fonts["body"],
            border_width=1,
            border_color=self.colors["muted"],
        )
        self.chat_text.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.chat_text.configure(state="disabled")
        self._show_empty_state("Select a peer and start chatting.")

        controls = ctk.CTkFrame(self.main, fg_color=self.colors["panel"], corner_radius=14)
        controls.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        controls.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            controls,
            placeholder_text="Type a message...",
            height=44,
            font=self.fonts["body"],
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(12, 10), pady=12)
        self.entry.bind("<Return>", lambda _event: self._send_text())

        send_btn = ctk.CTkButton(
            controls,
            text="Send",
            width=96,
            height=44,
            corner_radius=12,
            command=self._send_text,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_muted"],
        )
        send_btn.grid(row=0, column=1, padx=(0, 10), pady=12)

        file_btn = ctk.CTkButton(
            controls,
            text="Select File",
            width=110,
            height=44,
            corner_radius=12,
            command=self._send_file,
            fg_color=self.colors["muted"],
        )
        file_btn.grid(row=0, column=2, padx=(0, 12), pady=12)

        opt_row = ctk.CTkFrame(self.main, fg_color=self.colors["panel"], corner_radius=14)
        opt_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))

        enc_switch = ctk.CTkSwitch(
            opt_row, text="Encryption", variable=self.encrypted_var, command=self._refresh_header_state
        )
        enc_switch.pack(side="left", padx=8, pady=8)

        sd_switch = ctk.CTkSwitch(opt_row, text="Self-destruct (10s)", variable=self.self_destruct_var)
        sd_switch.pack(side="left", padx=8, pady=8)

        progress_row = ctk.CTkFrame(self.main, fg_color="transparent")
        progress_row.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
        progress_row.grid_columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(progress_row, height=12, corner_radius=12)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.progress.set(0)

        self.progress_slider = ctk.CTkSlider(
            progress_row,
            from_=0,
            to=1,
            state="disabled",
            width=180,
            height=18,
            progress_color=self.colors["accent"],
            button_color=self.colors["muted"],
            button_hover_color=self.colors["accent_muted"],
        )
        self.progress_slider.grid(row=0, column=1, sticky="e")

        self.status = ctk.CTkLabel(
            self.main,
            text="Connected to - | Encryption: ON | Port: 5000",
            anchor="w",
            text_color=self.colors["text_subtle"],
            font=self.fonts["body"],
        )
        self.status.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._refresh_header_state()

    def _send_text(self) -> None:
        if not self.selected_peer_id:
            self.status.configure(text="Select a peer from sidebar before sending.")
            return
        text = self.entry.get().strip()
        if not text:
            return
        self.logic.logic_in_queue.put(
            {
                "cmd": "send_text",
                "peer_id": self.selected_peer_id,
                "message": text,
                "encrypted": self.encrypted_var.get(),
                "self_destruct_seconds": 10 if self.self_destruct_var.get() else 0,
            }
        )
        logger.debug("UI queued send_text peer=%s chars=%s", self.selected_peer_id, len(text))
        self.entry.delete(0, "end")

    def _send_file(self) -> None:
        if not self.selected_peer_id:
            self.status.configure(text="Select a peer from sidebar before sending a file.")
            return
        path = filedialog.askopenfilename()
        if not path:
            return
        self.logic.logic_in_queue.put(
            {
                "cmd": "send_file",
                "peer_id": self.selected_peer_id,
                "file_path": path,
                "encrypted": self.encrypted_var.get(),
            }
        )
        logger.info("UI queued send_file peer=%s path=%s", self.selected_peer_id, path)

    def _poll_queues(self) -> None:
        self._poll_ui_queue()
        self._poll_file_progress_queue()
        self.root.after(120, self._poll_queues)

    def _poll_ui_queue(self) -> None:
        for _ in range(20):
            try:
                event = self.logic.ui_queue.get_nowait()
            except Empty:
                break

            etype = event.get("event")
            if etype == "peer_update":
                self._update_peers(event.get("peers", []))
            elif etype == "status":
                self.status.configure(text=event.get("text", ""))
            elif etype == "message":
                self._handle_message_event(event)

    def _poll_file_progress_queue(self) -> None:
        for _ in range(20):
            try:
                event = self.logic.file_progress_queue.get_nowait()
            except Empty:
                break
            percent = float(event.get("percent", 0.0))
            self._progress_target = max(0.0, min(1.0, percent / 100.0))
            self._kick_progress_animation()
            self.status.configure(
                text=f"Sending {event.get('file_name')} to {event.get('peer_id')} - {percent:.1f}%"
            )

    def _update_peers(self, peers: list[dict]) -> None:
        known = set(self.peer_buttons.keys())
        incoming = set()

        for peer in peers:
            peer_id = f"{peer['ip']}:{peer['port']}"
            incoming.add(peer_id)
            if peer_id not in self.peer_buttons:
                label = f"{peer.get('user', 'peer')} ({peer_id})"
                btn = ctk.CTkButton(
                    self.peers_frame,
                    text=label,
                    anchor="w",
                    fg_color=self.colors["muted"],
                    hover_color=self.colors["accent_muted"],
                    font=self.fonts["body"],
                    command=lambda p=peer: self._select_peer(p),
                )
                btn.pack(fill="x", padx=4, pady=3)
                self.peer_buttons[peer_id] = btn

            if peer_id == self.selected_peer_id:
                self.peer_buttons[peer_id].configure(fg_color=self.colors["accent_muted"])

        for stale in known - incoming:
            self.peer_buttons[stale].destroy()
            del self.peer_buttons[stale]

    def _select_peer(self, peer: dict) -> None:
        next_peer_id = f"{peer['ip']}:{peer['port']}"
        if next_peer_id == self.selected_peer_id:
            logger.debug("UI peer %s reselected; skipping conversation redraw", next_peer_id)
            if next_peer_id not in self.connected_peers:
                self.logic.logic_in_queue.put(
                    {"cmd": "connect_peer", "ip": peer["ip"], "port": int(peer["port"])}
                )
                self.connected_peers.add(next_peer_id)
            self._refresh_header_state()
            return

        previous_peer_id = self.selected_peer_id
        self.selected_peer_id = next_peer_id
        logger.info("UI selected peer %s", self.selected_peer_id)
        self.status.configure(
            text=f"Connected to {self.selected_peer_id} | Encryption: {'ON' if self.encrypted_var.get() else 'OFF'}"
        )
        self._refresh_header_state()
        self._highlight_selected_peer(previous_peer_id, self.selected_peer_id)
        self._render_selected_conversation()

        if self.selected_peer_id not in self.connected_peers:
            self.logic.logic_in_queue.put(
                {"cmd": "connect_peer", "ip": peer["ip"], "port": int(peer["port"])}
            )
            self.connected_peers.add(self.selected_peer_id)

    def _highlight_selected_peer(self, previous_peer_id: str | None, selected_peer_id: str) -> None:
        if previous_peer_id and previous_peer_id in self.peer_buttons:
            self.peer_buttons[previous_peer_id].configure(fg_color=self.colors["muted"])
        if selected_peer_id in self.peer_buttons:
            self.peer_buttons[selected_peer_id].configure(fg_color=self.colors["accent_muted"])

    def _handle_message_event(self, event: dict) -> None:
        peer_id = event.get("peer_id")
        if peer_id == self.selected_peer_id:
            self._add_message_line(event)

    def _render_selected_conversation(self) -> None:
        self._clear_messages()
        if not self.selected_peer_id:
            self._show_empty_state("Select a peer and start chatting.")
            return

        messages = self.logic.db.load_messages(self.selected_peer_id)
        if not messages:
            self._show_empty_state("No messages yet. Send the first one.")
            return

        for msg in messages:
            self._add_message_line(
                {
                    "peer_id": msg["peer_id"],
                    "message_id": msg["message_id"],
                    "sender": msg["sender"],
                    "message": msg["message"],
                    "timestamp_ms": msg["timestamp_ms"],
                    "self_destruct_seconds": msg["self_destruct_seconds"],
                }
            )

    def _clear_messages(self) -> None:
        self.chat_text.configure(state="normal")
        self.chat_text.delete("1.0", "end")
        self.chat_text.configure(state="disabled")
        self.rendered_message_ids.clear()

    def _show_empty_state(self, text: str) -> None:
        self.chat_text.configure(state="normal")
        self.chat_text.delete("1.0", "end")
        self.chat_text.insert("end", f"{text}\n")
        self.chat_text.configure(state="disabled")

    def _add_message_line(self, event: dict) -> None:
        peer_id = event.get("peer_id")
        if peer_id and self.selected_peer_id and peer_id != self.selected_peer_id:
            return

        sender = event.get("sender", "peer")
        message_id = int(event.get("message_id", 0))
        if message_id and message_id in self.rendered_message_ids:
            return

        raw_text = event.get("message", "")
        if isinstance(raw_text, bytes):
            text = raw_text.decode("utf-8", errors="replace")
        else:
            text = str(raw_text)
        text = "".join(ch if ch.isprintable() or ch in "\n\t" else "?" for ch in text)
        if not text.strip():
            text = "[empty message]"

        ts = dt.datetime.fromtimestamp(event.get("timestamp_ms", 0) / 1000.0)
        is_mine = sender == self.logic.username

        who = "You" if is_mine else sender
        line = f"[{ts.strftime('%H:%M:%S')}] {who}: {text}\n"
        self.chat_text.configure(state="normal")
        self.chat_text.insert("end", line)
        self.chat_text.configure(state="disabled")

        if message_id:
            self.rendered_message_ids.add(message_id)

        self_destruct_seconds = int(event.get("self_destruct_seconds", 0))
        if self_destruct_seconds > 0 and message_id:
            self._run_countdown(message_id, self_destruct_seconds)

        self.root.after(50, self._scroll_chat_to_bottom)

    def _run_countdown(self, message_id: int, seconds: int) -> None:
        if seconds <= 0:
            self.logic.logic_in_queue.put({"cmd": "delete_msg", "id": message_id})
            if self.selected_peer_id:
                self._render_selected_conversation()
            return
        self.root.after(1000, lambda: self._run_countdown(message_id, seconds - 1))

    def _kick_progress_animation(self) -> None:
        if self._progress_animating:
            return
        self._progress_animating = True
        self._step_progress()

    def _step_progress(self) -> None:
        diff = self._progress_target - self._progress_value
        if abs(diff) < 0.002:
            self._progress_value = self._progress_target
            self.progress.set(self._progress_value)
            self.progress_slider.set(self._progress_value)
            self._progress_animating = False
            return
        self._progress_value += diff * 0.2
        self.progress.set(self._progress_value)
        self.progress_slider.set(self._progress_value)
        self.root.after(16, self._step_progress)

    def _scroll_chat_to_bottom(self) -> None:
        try:
            self.chat_text.yview_moveto(1.0)
        except Exception:
            pass

    def _refresh_header_state(self) -> None:
        enc_state = "ON" if self.encrypted_var.get() else "OFF"
        enc_color = self.colors["accent_muted"] if self.encrypted_var.get() else self.colors["muted"]
        self._chip_enc.configure(text=f"Encryption {enc_state}", fg_color=enc_color)

        peer_text = self.selected_peer_id or "No peer"
        self.status.configure(
            text=f"Connected to {peer_text} | Encryption: {enc_state} | Port: {getattr(self.logic, 'listen_port', 5000)}"
        )
        self._chip_port.configure(text=f"Port {getattr(self.logic, 'listen_port', 5000)}")

    def run(self) -> None:
        self.root.mainloop()
