"""TCP-connect test from a specific local source IP. Used to verify that a
service is reachable from a path that doesn't go through the VPN."""

import socket
import sys

if len(sys.argv) != 4:
    print("usage: tcp-probe.py <src_ip> <host> <port>")
    sys.exit(2)

src_ip = sys.argv[1]
host   = sys.argv[2]
port   = int(sys.argv[3])

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
try:
    s.bind((src_ip, 0))
    s.connect((host, port))
    print(f"CONNECTED to {host}:{port} via {src_ip}")
    # Send a minimal HTTP request to verify Flask responds through the tunnel.
    s.sendall(b"GET /healthz HTTP/1.1\r\nHost: " + host.encode() + b"\r\nConnection: close\r\n\r\n")
    data = s.recv(2048)
    print(data.decode(errors="replace")[:500])
except Exception as e:
    print(f"FAILED: {e}")
finally:
    s.close()
