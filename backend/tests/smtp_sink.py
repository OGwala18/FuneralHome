"""A small SMTP server for the tests: it keeps what it receives, or fails on purpose.

The `mailbox` fixture in conftest replaces the sender function, which proves
what the API asked to send. This goes one layer further down: the real smtplib
code path, login and all, against a server that answers like a real one. That
is where the 12 Nov 2026 failure lived ("550 SMTP AUTH is required"), and no
stub of `_send` could have caught it.

Plain text on 127.0.0.1 only; tests set SMTP_STARTTLS=0 to talk to it, the same
opt-out config.py documents for local mail catchers.

Modes (SmtpSink.mode), each a failure a real mail host produces:
    ok                 accept and keep everything
    auth_required      refuse every recipient: 550 SMTP AUTH is required
    auth_failed        refuse the login: 535
    recipient_refused  refuse every recipient: 550 mailbox unavailable
    sender_refused     refuse MAIL FROM: 553
    reject_data        refuse the message itself: 554 (spam filter)
    drop               close the connection without a greeting
    silent             accept the connection and never answer
    no_starttls        ok, but never offers STARTTLS
"""

from __future__ import annotations

import base64
import email
import socketserver
import threading
import time
from dataclasses import dataclass, field
from email import policy


@dataclass
class Received:
    mail_from: str
    rcpt_to: list[str]
    raw: bytes
    login: str | None

    @property
    def message(self) -> email.message.EmailMessage:
        return email.message_from_bytes(self.raw, policy=policy.default)


@dataclass
class SmtpSink:
    host: str = "127.0.0.1"
    port: int = 0
    mode: str = "ok"
    username: str = "sink-user"
    password: str = "sink-password"
    received: list[Received] = field(default_factory=list)
    connections: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _server: socketserver.ThreadingTCPServer | None = None

    def start(self) -> "SmtpSink":
        sink = self

        class Handler(socketserver.StreamRequestHandler):
            timeout = 10

            def handle(self) -> None:  # noqa: C901 - one SMTP conversation
                with sink._lock:
                    sink.connections += 1
                mode = sink.mode
                if mode == "drop":
                    return
                if mode == "silent":
                    time.sleep(5)
                    return
                self.say("220 sink ESMTP ready")
                login: str | None = None
                mail_from = ""
                rcpt: list[str] = []
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    command = line.decode("utf-8", "replace").rstrip("\r\n")
                    verb = command.split(" ", 1)[0].upper()
                    if verb in ("EHLO", "HELO"):
                        # PLAIN only: offering more makes smtplib retry with
                        # the next mechanism and report that one's refusal.
                        offers = ["250-sink", "250-AUTH PLAIN"]
                        if mode != "no_starttls":
                            offers.append("250-STARTTLS")
                        offers.append("250 SIZE 1048576")
                        self.say("\r\n".join(offers))
                    elif verb == "AUTH":
                        parts = command.split(" ")
                        if len(parts) >= 3 and parts[1].upper() == "PLAIN":
                            decoded = base64.b64decode(parts[2]).split(b"\x00")
                            user = decoded[1].decode()
                            secret = decoded[2].decode()
                        else:
                            self.say("504 only AUTH PLAIN here")
                            continue
                        if mode == "auth_failed" or (user, secret) != (sink.username, sink.password):
                            self.say("535 5.7.8 Authentication credentials invalid")
                        else:
                            login = user
                            self.say("235 2.7.0 Authentication successful")
                    elif verb == "MAIL":
                        mail_from = command[10:].strip("<> ")
                        if mode == "sender_refused":
                            self.say("553 5.7.1 Sender address rejected: not owned by user")
                        else:
                            self.say("250 OK")
                    elif verb == "RCPT":
                        address = command[8:].strip("<> ")
                        if mode == "auth_required" or (mode == "ok" and login is None):
                            self.say("550 5.7.1 SMTP AUTH is required")
                        elif mode == "recipient_refused":
                            self.say(f"550 5.1.1 <{address}>: Recipient address rejected")
                        else:
                            rcpt.append(address)
                            self.say("250 OK")
                    elif verb == "DATA":
                        self.say("354 End data with <CR><LF>.<CR><LF>")
                        chunks = []
                        while True:
                            data_line = self.rfile.readline()
                            if data_line in (b".\r\n", b""):
                                break
                            if data_line.startswith(b".."):
                                data_line = data_line[1:]
                            chunks.append(data_line)
                        if mode == "reject_data":
                            self.say("554 5.7.1 Message rejected as spam")
                        else:
                            with sink._lock:
                                sink.received.append(
                                    Received(mail_from, list(rcpt), b"".join(chunks), login))
                            self.say("250 OK queued")
                        rcpt = []
                    elif verb == "RSET":
                        rcpt = []
                        self.say("250 OK")
                    elif verb == "NOOP":
                        self.say("250 OK")
                    elif verb == "QUIT":
                        self.say("221 bye")
                        return
                    else:
                        self.say("502 command not implemented")

            def say(self, text: str) -> None:
                self.wfile.write(text.encode() + b"\r\n")
                self.wfile.flush()

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = True

        self._server = Server((self.host, self.port), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def clear(self) -> None:
        with self._lock:
            self.received.clear()
            self.connections = 0
