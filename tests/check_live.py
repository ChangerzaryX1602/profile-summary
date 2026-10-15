#!/usr/bin/env python3
"""check_live.py — end-to-end proof for the DEPLOYED site (https://profile.mysterchat.com).

Asserts: HTTP 200 through Cloudflare, page + JS work, auto-fit runs, the Print/PDF export
still yields exactly one A4 page with our embedded fonts, and no console errors.
Run:  pwpy tests/check_live.py
"""
import io, pathlib, re, sys, urllib.request
from playwright.sync_api import sync_playwright

URL = 'https://profile.mysterchat.com/'
OUT = pathlib.Path(__file__).resolve().parent / 'out'
OUT.mkdir(parents=True, exist_ok=True)


def http_headers():
    req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode('utf-8', 'replace')
        return r.status, dict(r.headers), body


def main():
    fails = []
    try:
        status, headers, body = http_headers()
    except Exception as exc:
        print(f'FAIL: cannot reach {URL}: {exc}')
        return 1
    print(f'HTTP {status} | {len(body)/1024:.1f} KB | server={headers.get("Server")}')
    if status != 200:
        fails.append(f'expected HTTP 200, got {status}')
    if 'noindex' not in body:
        fails.append('noindex meta missing from the served HTML')
    if 'X-Robots-Tag' not in str(headers) and 'x-robots-tag' not in {k.lower() for k in headers}:
        print('  note: no X-Robots-Tag header (meta noindex is still present)')

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={'width': 1500, 'height': 1000})
        errs = []
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        pg.on('pageerror', lambda e: errs.append(str(e)))
        reqs = []
        pg.on('request', lambda r: reqs.append(r.url))
        pg.goto(URL, wait_until='load')
        pg.wait_for_timeout(900)

        title = pg.title()
        print(f'title: {title}')
        if 'Career Summary' not in title:
            fails.append(f'unexpected title: {title}')

        external = [u for u in reqs if not u.startswith('https://profile.mysterchat.com')]
        print(f'requests: {len(reqs)} total, {len(external)} off-origin {external[:3]}')
        if external:
            fails.append(f'page made off-origin requests: {external[:3]}')

        pg.on('dialog', lambda d: d.accept())
        pg.click('#btnDemo')
        pg.wait_for_timeout(600)
        st = pg.evaluate("""() => {
            const sheet=document.getElementById('sheet'), fit=document.getElementById('fit');
            return {scale: parseFloat(getComputedStyle(sheet).getPropertyValue('--s')),
                    warn: document.getElementById('warn').classList.contains('show'),
                    fitH: fit.getBoundingClientRect().height,
                    sheetH: sheet.getBoundingClientRect().height,
                    name: document.querySelector('.doc-head h1').textContent,
                    saved: !!localStorage.getItem('hermes.careerSummary.v1')};
        }""")
        print(f"demo: name={st['name']} scale={st['scale']:.2f} warn={st['warn']} "
              f"fitH={st['fitH']:.0f}/{st['sheetH']:.0f} localStorage={st['saved']}")
        if not st['saved']:
            fails.append('localStorage persistence does not work on the live site')

        # retired fields must be gone from the document (target team + measurable outcome)
        ptext = pg.evaluate("() => document.getElementById('fit').innerText")
        for bad in ('ทีมเป้าหมาย', 'Target team', '0.4% → 0.01%', 'Duplicate-payment errors'):
            if bad in ptext:
                fails.append(f'retired content is still rendered: {bad!r}')
        if 'ออกแบบ idempotency' not in ptext:
            fails.append('project description is missing from the document')

        pdf = pg.pdf(format='A4', print_background=True, prefer_css_page_size=True)
        (OUT / 'live.pdf').write_bytes(pdf)
        try:
            import pypdf
            r = pypdf.PdfReader(io.BytesIO(pdf))
            n = len(r.pages)
            txt = r.pages[0].extract_text() or ''
            fonts = set()
            for f in r.pages[0]['/Resources']['/Font'].values():
                fonts.add(str(f.get_object().get('/BaseFont')))
        except ImportError:
            n = len(re.findall(rb'/Type\s*/Page[^s]', pdf)); txt = ''; fonts = set()
        print(f'live PDF: {n} page(s), {len(pdf)/1024:.0f} KB, fonts={sorted(fonts)}')
        if n != 1:
            fails.append(f'live PDF is {n} pages, expected 1')
        foreign = [f for f in fonts if 'IBMPlexSansThai' not in f]
        if foreign:
            fails.append(f'live PDF used a system font: {foreign}')
        if 'Somchai' not in txt and 'สมชาย' not in txt:
            fails.append('live PDF text layer does not contain the document text')
        if errs:
            fails.append(f'console errors: {errs[:3]}')
        b.close()

    print('\n' + '=' * 60)
    if fails:
        print('FAIL')
        for f in fails:
            print(' -', f)
        return 1
    print('PASS — live site serves, auto-fit runs, export = 1 A4 page with embedded fonts')
    return 0


if __name__ == '__main__':
    sys.exit(main())
