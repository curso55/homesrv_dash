#!/usr/bin/env python3
"""
Polls the Factorio server over RCON for its player list and writes a
status.json consumed by the Homepage "Factorio" dashboard tile via its
Custom API widget.

RCON is bound to 127.0.0.1 only (Pterodactyl allocation), so this only
works run locally on homesrv.
"""
import json
import os
import socket
import struct
import tempfile
from datetime import datetime, timezone

RCON_HOST = "172.23.0.1"  # Wings' pterodactyl0 bridge gateway -- allocation IP 127.0.0.1
# gets published here, not true host loopback. Still LAN-unreachable.
RCON_PORT = 27015
ENV_FILE = "/home/curso/homesrv_webstack/config/homepage/.env"
STATUS_DIR = "/home/curso/homesrv_webstack/config/homepage/update-status/factorio"
STATUS_FILE = os.path.join(STATUS_DIR, "status.json")

SERVERDATA_AUTH = 3
SERVERDATA_EXECCOMMAND = 2


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("RCON connection closed unexpectedly")
        buf += chunk
    return buf


def _send_packet(sock, pkt_id, pkt_type, body):
    payload = struct.pack("<ii", pkt_id, pkt_type) + body.encode("utf-8") + b"\x00\x00"
    sock.sendall(struct.pack("<i", len(payload)) + payload)


def _read_packet(sock):
    (length,) = struct.unpack("<i", _recv_exact(sock, 4))
    data = _recv_exact(sock, length)
    pkt_id, pkt_type = struct.unpack("<ii", data[:8])
    body = data[8:-2].decode("utf-8", errors="replace")
    return pkt_id, pkt_type, body


def rcon_command(host, port, password, command, timeout=5):
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(timeout)
    try:
        _send_packet(sock, 1, SERVERDATA_AUTH, password)
        auth_id, auth_type, _ = _read_packet(sock)
        if auth_id == -1:
            raise PermissionError("RCON authentication failed")

        _send_packet(sock, 2, SERVERDATA_EXECCOMMAND, command)
        _, _, body = _read_packet(sock)
        return body
    finally:
        sock.close()


def read_rcon_password():
    with open(ENV_FILE) as f:
        for line in f:
            if line.startswith("FACTORIO_RCON_PASSWORD="):
                return line.strip().split("=", 1)[1]
    raise RuntimeError("FACTORIO_RCON_PASSWORD not set in " + ENV_FILE)


def parse_players(raw):
    players = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("players ("):
            continue
        online = line.endswith("(online)")
        name = line[: -len("(online)")].strip() if online else line
        if name:
            players.append({"name": name, "online": online})
    return players


def main():
    status = {"generated_at": datetime.now(timezone.utc).astimezone().isoformat()}
    try:
        password = read_rcon_password()
        raw = rcon_command(RCON_HOST, RCON_PORT, password, "/players")
        players = parse_players(raw)
        online = [p["name"] for p in players if p["online"]]

        status.update(
            {
                "reachable": True,
                "players": players,
                "registered_count": len(players),
                "online_count": len(online),
                "online_names": ", ".join(online) if online else "none",
                "status_text": f"\U0001f7e2 {len(online)} online" if online else "⚪ 0 online",
            }
        )
    except (OSError, PermissionError, RuntimeError) as e:
        status.update(
            {
                "reachable": False,
                "players": [],
                "registered_count": 0,
                "online_count": 0,
                "online_names": "",
                "status_text": f"\U0001f534 unreachable ({type(e).__name__})",
            }
        )

    os.makedirs(STATUS_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=STATUS_DIR)
    with os.fdopen(fd, "w") as f:
        json.dump(status, f, indent=2)
    os.chmod(tmp_path, 0o644)
    os.replace(tmp_path, STATUS_FILE)


if __name__ == "__main__":
    main()
