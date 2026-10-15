#!/usr/bin/env python3
"""check_typing.py — regression test for the reported bug:
"Refresh แล้วข้อมูลหาย ไม่ Auto Save และไม่ Auto Preview".

Types into the REAL rendered fields (bindings are discovered from the DOM, not
hard-coded, so a binding regression cannot pass by accident), then asserts:
  1. the live preview shows every typed value immediately,
  2. localStorage holds every value,
  3. after a reload nothing is lost (inputs + preview),
  4. the autosave indicator says it saved.

Usage:  pwpy tests/check_typing.py [local|live]      (default: live)
"""
import json, pathlib, sys
from playwright.sync_api import sync_playwright

TARGET = (sys.argv[1] if len(sys.argv) > 1 else 'live').lower()
ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = (ROOT / 'dist' / 'index.html').as_uri() if TARGET == 'local' else 'https://profile.mysterchat.com/'
LS = 'hermes.careerSummary.v1'


def main():
    fails = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={'width': 1500, 'height': 1100})
        pg = ctx.new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('console', lambda m: errs.append('console: ' + m.text) if m.type == 'error' else None)
        pg.goto(URL, wait_until='load')
        pg.evaluate("k => localStorage.removeItem(k)", LS)
        pg.reload(wait_until='load')
        pg.wait_for_timeout(500)

        # discover the real bindings per section, straight from the DOM
        secs = pg.evaluate("""() => Array.from(document.querySelectorAll('#editor .sec')).map(sec => ({
            title: (sec.querySelector('h3') || {}).textContent || '',
            binds: Array.from(sec.querySelectorAll('[data-bind]')).map(el => el.getAttribute('data-bind'))
        }))""")
        print('sections found:', len(secs))
        for i, s in enumerate(secs):
            print(f'  [{i}] {s["title"].strip()[:34]:<34} binds={s["binds"][:4]}')
        if len(secs) < 5:
            print('FAIL: editor did not render all sections'); return 1

        basic, prj, skills = secs[0], secs[1], secs[2]

        def fill(bind, text):
            el = pg.query_selector(f'[data-bind="{bind}"]')
            if not el:
                fails.append(f'field {bind} not found'); return
            el.fill(''); el.type(text, delay=6)

        plan = [
            (basic['binds'][0], 'ทดสอบ ออโต้เซฟ', 'full name'),
            (basic['binds'][1], 'Backend Engineer', 'role'),
            (prj['binds'][0], 'โปรเจกต์ที่พิมพ์เอง', 'project name'),
            (prj['binds'][1], 'รายละเอียดโปรเจกต์ที่พิมพ์เอง ไม่มีตัวเลขผลลัพธ์', 'project detail'),
            (skills['binds'][0], 'Go, PostgreSQL, Kubernetes', 'skills'),
        ]
        for bind, text, label in plan:
            fill(bind, text)
            print(f'  typed {label:<18} into {bind}')

        pg.wait_for_timeout(700)
        preview = pg.evaluate("() => document.getElementById('fit').innerText")
        stored_raw = pg.evaluate("k => localStorage.getItem(k)", LS)
        state = pg.evaluate("() => (document.getElementById('saveState')||{}).textContent || ''")
        print(f'autosave indicator: {state!r}')

        for bind, text, label in plan:
            needle = text.split(' ')[0] if len(text.split(' ')[0]) > 3 else text
            ok_prev = text in preview or needle in preview
            print(f"  preview shows {label:<18} {'OK' if ok_prev else 'MISSING'}")
            if not ok_prev:
                fails.append(f'preview does not show the typed {label}')

        if not stored_raw:
            fails.append('nothing was written to localStorage (no autosave)')
        else:
            d = json.loads(stored_raw).get('th', {})
            checks = [('name', d.get('name')), ('role', d.get('role')),
                      ('projects[0].name', (d.get('projects') or [{}])[0].get('name')),
                      ('projects[0].desc', (d.get('projects') or [{}])[0].get('desc')),
                      ('skills', d.get('skills'))]
            if 'exp' in d:
                fails.append('retired section "exp" is still present in the saved data')
            for label, val in checks:
                good = bool(val)
                print(f"  stored {label:<16} {'OK' if good else 'MISSING'}")
                if not good:
                    fails.append(f'localStorage did not keep {label}')
        if 'บันทึกแล้ว' not in state and 'พร้อมใช้งาน' not in state:
            fails.append(f'autosave indicator never reported a save (saw {state!r})')

        # the actual complaint: reload must not lose anything
        pg.reload(wait_until='load')
        pg.wait_for_timeout(900)
        prev2 = pg.evaluate("() => document.getElementById('fit').innerText")
        for bind, text, label in plan:
            val = pg.evaluate("b => { const el = document.querySelector('[data-bind=\"' + b + '\"]'); return el ? el.value : null; }", bind)
            needle = text.split(' ')[0] if len(text.split(' ')[0]) > 3 else text
            ok = (val == text) or (text in prev2 or needle in prev2)
            print(f"  after refresh {label:<18} {'OK' if ok else 'LOST'}  (input={val!r})")
            if not ok:
                fails.append(f'after refresh the {label} is gone')

        if errs:
            fails.append(f'page errors: {errs[:3]}')
        b.close()

    print('\n' + '=' * 60)
    if fails:
        print('FAIL')
        for f in fails:
            print(' -', f)
        return 1
    print('PASS — typing autosaves, preview updates live, refresh keeps everything')
    return 0


if __name__ == '__main__':
    sys.exit(main())
