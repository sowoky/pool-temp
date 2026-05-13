"""Pull the design tokens out of the minified MSC CSS bundle."""
import re
from pathlib import Path

css = Path(r"C:\Users\kyler\workspace\pool-temp\tools\msc-cache\00dc4cd7c5dbe29a.css").read_text(encoding="utf-8")

# Tailwind v4 @theme blocks declare --color-* variables.
theme = re.search(r"@theme[^{]*\{(.*?)\}", css, re.S)
if theme:
    body = theme.group(1)
    print("--- @theme block first 4000 chars ---")
    print(body[:4000])
    print("\n--- color tokens in @theme ---")
    for m in re.finditer(r"--color-([a-z0-9-]+)\s*:\s*([^;]+);", body):
        print(f"  {m.group(1):20s} = {m.group(2).strip()}")
    print("\n--- font tokens in @theme ---")
    for m in re.finditer(r"--font-([a-z0-9-]+)\s*:\s*([^;]+);", body):
        print(f"  {m.group(1):20s} = {m.group(2).strip()}")

# Also pull any top-level variable definitions (older Tailwind).
print("\n--- top-level :root color vars ---")
for m in re.finditer(r"--color-([a-z0-9-]+)\s*:\s*([^;]+);", css):
    print(f"  {m.group(1):20s} = {m.group(2).strip()}")

# All explicit hex colors that appear in single-line context with a class name.
print("\n--- a sampling of hex colors used in compiled classes ---")
hex_classes = re.findall(r"\.(bg|text|fill|border|from|to)-([a-z0-9-]+)\{[^}]*?(#[0-9A-Fa-f]{3,8}|oklch\([^)]+\))", css)
seen = set()
for prefix, name, val in hex_classes:
    key = f"{prefix}-{name}"
    if key in seen:
        continue
    seen.add(key)
    print(f"  .{prefix}-{name:24s} = {val}")
