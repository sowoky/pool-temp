"""Fetch montesanoclub.org and report its assets so we can study the visual design."""

import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

CACHE = Path(r"C:\Users\kyler\workspace\pool-temp\tools\msc-cache")
CACHE.mkdir(parents=True, exist_ok=True)
ROOT  = "https://montesanoclub.org/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch(url: str, dest: Path) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        dest.write_text(r.text, encoding="utf-8")
        print(f"  saved {dest.name} ({len(r.text)} bytes)")
        return r.text
    except Exception as e:
        print(f"  FAILED {url}: {e}")
        return None


def fetch_binary(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        dest.write_bytes(r.content)
        print(f"  saved {dest.name} ({len(r.content)} bytes)")
        return True
    except Exception as e:
        print(f"  FAILED {url}: {e}")
        return False


def main() -> int:
    print(f"--- fetching {ROOT} ---")
    html = fetch(ROOT, CACHE / "index.html")
    if not html:
        return 1

    # CSS links
    css_links = re.findall(r'<link[^>]+rel=[\"]?stylesheet[\"]?[^>]*>', html, re.I)
    print(f"\n--- CSS link tags ({len(css_links)}) ---")
    for tag in css_links:
        print(" ", tag)

    css_urls = re.findall(r'href=["\']([^"\']+)["\']', "\n".join(css_links))
    print(f"\n--- CSS urls ---")
    for url in css_urls:
        print(" ", url)

    # Image refs
    img_srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I)
    print(f"\n--- image srcs ({len(img_srcs)}) ---")
    for src in img_srcs[:50]:
        print(" ", src)

    # SVG external refs
    svg_srcs = re.findall(r'<(?:image|use)[^>]+(?:href|xlink:href)=["\']([^"\']+)["\']', html, re.I)
    print(f"\n--- svg external refs ({len(svg_srcs)}) ---")
    for src in svg_srcs[:20]:
        print(" ", src)

    # Inline style blocks
    inline = re.findall(r"<style[^>]*>(.*?)</style>", html, re.I | re.S)
    total_inline = sum(len(b) for b in inline)
    print(f"\n--- inline style blocks: {len(inline)} blocks, {total_inline} chars total ---")

    # Background images in style attrs
    bg_imgs = re.findall(r'background[^;]*url\(["\']?([^"\')]+)["\']?\)', html, re.I)
    print(f"\n--- background-image urls in inline style ({len(bg_imgs)}) ---")
    for src in bg_imgs[:30]:
        print(" ", src)

    # Headline / hero region heuristics
    h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    print(f"\n--- h1 tags ({len(h1s)}) ---")
    for h in h1s[:5]:
        print(" ", re.sub(r"<[^>]+>", " ", h).strip()[:200])

    # Now download all CSS files for inspection
    print(f"\n--- downloading CSS files ---")
    for i, css_url in enumerate(css_urls):
        full = urljoin(ROOT, css_url)
        if not full.startswith("http"):
            continue
        # skip Google Fonts / external — we just want the site's own CSS
        if urlparse(full).netloc not in ("montesanoclub.org", ""):
            print(f"  skip external: {full}")
            continue
        name = os.path.basename(urlparse(full).path) or f"css-{i}.css"
        fetch(full, CACHE / name)

    print("\n--- done ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
