"""Find the exact byte sequence we need to match for the rendered temp."""
import re
import requests

r = requests.get("https://www.montesanoclub.org/pool", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
print("status:", r.status_code, "encoding:", r.encoding, "len:", len(r.text))

# Find any 1-3 digit . 1-3 digit value near 'Pool temperature' or 'Last updated'
for m in re.finditer(r"Pool temperature.{0,400}", r.text):
    snippet = m.group(0)
    print(f"\nsnippet around 'Pool temperature':\n  {snippet!r}")

# Show the raw bytes around any 'XX.X' that looks like a temp
for m in re.finditer(r"\"(\d{2}\.\d)\"", r.text):
    pos = m.start()
    print(f"\nat pos {pos}: {r.text[max(0,pos-30):pos+60]!r}")
    if pos < 100000:  # only first few
        pass
    break

# Specifically look for the degree symbol pattern in any form
patterns = [
    r'\\u00b0F',
    r'°F',
    r'\\u00B0F',
    r'00b0F',
]
for p in patterns:
    found = r.text.count(p) if not p.startswith("\\") else len(re.findall(p, r.text))
    print(f"\noccurrences of {p!r}: {found}")
