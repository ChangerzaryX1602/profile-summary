#!/usr/bin/env python3
"""font_probe.py — which characters fall back to a system font inside the A4 document?
document.fonts.check() honours the @font-face unicode-range, so a `False` here means
the browser will substitute another font for that character (visible in the PDF).
"""
import pathlib, sys
from playwright.sync_api import sync_playwright

URL = (pathlib.Path(__file__).resolve().parent.parent / 'dist' / 'index.html').as_uri()
SUSPECTS = ['→','←','·','•','–','—','»','"','"','฿','%','✓','✕','⬇','│','∘','▪','(',')','/','+','@',':']

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto(URL)
    pg.wait_for_timeout(600)
    res = pg.evaluate("""(chars) => {
        const bad = [], ok = [];
        for (const c of chars) {
            const fine = document.fonts.check('12pt "IBM Plex Sans Thai"', c);
            (fine ? ok : bad).push(c);
        }
        const thai = 'กขคไทย๑๒๓'.split('');
        return {bad, ok, thaiOk: thai.every(c=>document.fonts.check('12pt "IBM Plex Sans Thai"', c))};
    }""", SUSPECTS)
    print('renderable by IBM Plex Sans Thai :', ' '.join(res['ok']))
    print('NEEDS FALLBACK FONT             :', ' '.join(res['bad']) or '(none)')
    print('thai glyphs ok                  :', res['thaiOk'])
    b.close()

sys.exit(1 if res['bad'] else 0)
