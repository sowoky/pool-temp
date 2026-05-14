"""Find the rendered temperature value + its surrounding context in the
React Server Components flight payload, so we know exactly what to scrape."""

import re

flight = open(r"C:\Users\kyler\workspace\pool-temp\tools\msc-pool-cache\next-flight.txt", encoding="utf-8").read()

def show(label, pattern, ctx=160, limit=5):
    matches = list(re.finditer(pattern, flight, re.I))
    print(f"\n--- {label} ({len(matches)} hit{'s' if len(matches)!=1 else ''}) ---")
    for i, m in enumerate(matches[:limit]):
        start = max(0, m.start() - ctx)
        end   = min(len(flight), m.end() + ctx)
        snippet = flight[start:end].replace("\\n", " ").replace("\\\"", '"')
        print(f"  [{i}] ...{snippet}...")

show("temperature numeric values",            r"\d{2}\.\d{1,3}")
show("'Pool temperature' label and context",  r"Pool temperature")
show("'Last updated' label and context",      r"Last updated")
show("any reference to a second sensor",      r"sensor|second|other|probe|both", limit=10)
show("explicit /pool or /temps endpoint",     r"/(pool|temps?)(?:/[a-z0-9_\-]+)?")
show("anything that looks like JSON state for the page", r"\"temp[A-Za-z_]*\"\s*:")
