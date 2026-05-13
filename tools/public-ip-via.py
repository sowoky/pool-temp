"""Print our public IP as seen when egress is forced via a specific local IP."""
import socket, sys, urllib.request

bind_ip = sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0"
real_socket = socket.socket

def patched(*a, **kw):
    s = real_socket(*a, **kw)
    try:
        s.bind((bind_ip, 0))
    except OSError as e:
        print(f"bind {bind_ip} failed: {e}", file=sys.stderr)
    return s

socket.socket = patched

try:
    print(urllib.request.urlopen("https://api.ipify.org", timeout=8).read().decode())
except Exception as e:
    print(f"FAILED via {bind_ip}: {e}")
