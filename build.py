#!/usr/bin/env python3
"""build.py — inline fonts into a single self-contained dist/index.html"""
import pathlib, sys, re

ROOT = pathlib.Path(__file__).resolve().parent
src = (ROOT / 'src' / 'index.html').read_text(encoding='utf-8')
fonts = (ROOT / 'fonts' / 'fonts.css').read_text(encoding='utf-8')

link = '<link rel="stylesheet" href="fonts/fonts.css">'
if link not in src:
    sys.exit('FAIL: font <link> not found in src/index.html')

out = src.replace(link, '<style>\n' + fonts + '</style>')

# sanity: single file, no external refs left
ext = re.findall(r'(?:href|src)="(?!#|data:)([^"]+)"', out)
bad = [u for u in ext if not u.startswith('data:')]
if bad:
    sys.exit(f'FAIL: external references remain: {bad}')
if 'data:font/woff2;base64' not in out:
    sys.exit('FAIL: no embedded font data')

dist = ROOT / 'dist'
dist.mkdir(exist_ok=True)
(dist / 'index.html').write_text(out, encoding='utf-8')

size = (dist / 'index.html').stat().st_size
print(f'OK dist/index.html = {size/1024:.1f} KB (self-contained, 0 external requests)')
print(f'   embedded woff2 blocks: {out.count("data:font/woff2;base64")}')
