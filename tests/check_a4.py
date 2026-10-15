#!/usr/bin/env python3
"""check_a4.py — real-browser proof that the export is exactly one A4 page.

Cases:
  A empty      -> no shrink needed, 1 page
  B demo       -> long content, auto-shrunk, 1 page
  C extreme    -> overflow beyond 70% floor -> warning shown, still 1 page (clipped, never page 2)
Also asserts: embedded Thai font in the PDF, selectable/vector text, no console errors.
"""
import pathlib, re, sys, json
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = (ROOT / 'dist' / 'index.html').as_uri()
OUT = ROOT / 'tests' / 'out'
OUT.mkdir(parents=True, exist_ok=True)

EXTREME = {
  "th": {"name":"ทดสอบ ข้อมูลยาวมาก","role":"Engineer","team":"Team","headline":"ทดสอบการย่ออัตโนมัติเมื่อข้อมูลเยอะเกินหนึ่งหน้า",
         "projects":[{"name":f"โปรเจกต์ {i}","desc":"รายละเอียดโปรเจกต์ที่ยาวมาก " * 60} for i in range(1,13)],
         "skills":"\n".join([f"ทักษะที่ {i}" for i in range(1,60)]),
         "strengths":"จุดแข็งหนึ่ง\nจุดแข็งสอง\nจุดแข็งสาม",
         "path":"เส้นทางที่อยากไป " * 45,
         "email":"a@b.com","phone":"0800000000","line":"@x","portfolio":"github.com/x"},
  "en": {"name":"Extreme Test","role":"Engineer","team":"Team","headline":"Auto-fit behaviour under heavy content load",
         "projects":[{"name":f"Project {i}","desc":"A very long project description " * 60} for i in range(1,13)],
         "skills":"\n".join([f"Skill {i}" for i in range(1,60)]),
         "strengths":"Strength one\nStrength two\nStrength three",
         "path":"Career direction " * 45,
         "email":"a@b.com","phone":"0800000000","line":"@x","portfolio":"github.com/x"},
}

SIX_NAME = 'ทดสอบ หกโปรเจกต์'
SIX_PROJECTS = [
    {"name": "Home Network Agent (current employer)",
     "desc": "Architected and delivered a Thai voice-controlled home network agent: Go backend, MQTT device control,\n"
             "web dashboard, Aliyun/AISF SDK integration for FTTR, Thai ASR/TTS, ESP32 and shift-register LED board.\n"
             "Ran integration tests with Huawei R&D HQ and owned deployment, access control and security."},
    {"name": "Fibre3 Smart Home Application (current employer)",
     "desc": "Supported the Smart Home application through QA: triaged defects, explained technical detail to QA,\n"
             "drove fixes with vendors and internal teams, and validated on site at AIS Tower 2 including NAS testing."},
    {"name": "KKU Healthy Life — Season 5 & 6",
     "desc": "Backend (Go, Fiber v2) for an exercise-to-rewards platform used by staff across the university;\n"
             "then DevOps in Season 6: self-hosted deployment, CI/CD pipeline, reverse proxy and hardening."},
    {"name": "KKU Document Management System",
     "desc": "Backend (Go) replacing paper-based official document workflows: numbered documents, inbox/outbox,\n"
             "receive/send/reply/forward/classified handling and RBAC via bitwise operations; in production at KKU."},
    {"name": "PI E-Billing and E-Payment Platform",
     "desc": "Backend (Go) for tuition and fee billing: billing runs and reports, plus reconciliation of\n"
             "bank statement files to update payment status automatically."},
    {"name": "KKU GS Admission",
     "desc": "Admissions platform for KKU Graduate School (master's and doctoral applications): backend (Go)\n"
             "and DevOps for build and deployment."},
]


def pages_of(pdf_bytes):
    try:
        import io, pypdf
        r = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        txt = re.sub(r'\s+', ' ', r.pages[0].extract_text() or '')   # wraps inside words/names -> normalise
        fonts = set()
        try:
            for f in r.pages[0]['/Resources']['/Font'].values():
                fonts.add(str(f.get_object().get('/BaseFont')))
        except Exception:
            pass
        return len(r.pages), txt, fonts, 'pypdf'
    except ImportError:
        n = len(re.findall(rb'/Type\s*/Page[^s]', pdf_bytes))
        return n, '', set(), 'regex'

def main():
    fails = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={'width':1500,'height':1000})
        errors = []
        pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        pg.on('pageerror', lambda e: errors.append(str(e)))

        def state():
            return pg.evaluate("""() => {
                const sheet=document.getElementById('sheet'), fit=document.getElementById('fit');
                return {scale: parseFloat(getComputedStyle(sheet).getPropertyValue('--s')),
                        warn: document.getElementById('warn').classList.contains('show'),
                        warnText: document.getElementById('warnBody').textContent,
                        sheetH: sheet.getBoundingClientRect().height,
                        fitH: fit.getBoundingClientRect().height,
                        name: (document.querySelector('.doc-head h1')||{}).textContent||''};
            }""")

        def export(tag, name):
            s = state()
            pdf = pg.pdf(format='A4', print_background=True, prefer_css_page_size=True)
            (OUT / f'{tag}.pdf').write_bytes(pdf)
            n, txt, fonts, how = pages_of(pdf)
            print(f"\n[{tag}] scale={s['scale']:.2f} warn={s['warn']} fitH={s['fitH']:.0f}px sheetH={s['sheetH']:.0f}px")
            print(f"      PDF pages={n} (counted via {how})  file={(OUT/f'{tag}.pdf').stat().st_size/1024:.0f} KB")
            if fonts: print(f"      fonts in PDF: {sorted(fonts)}")
            got_name = bool(name and name.split()[0] in txt)
            print(f"      text extractable={bool(txt.strip())} name-found={got_name}")
            foreign = [f for f in fonts if 'IBMPlexSansThai' not in f]
            if foreign: fails.append(f'{tag}: PDF used a system fallback font {foreign}')
            if n != 1: fails.append(f'{tag}: PDF is {n} pages, expected 1')
            if s['fitH'] > s['sheetH'] + 1 and not s['warn']:
                fails.append(f"{tag}: content taller than the sheet without warning")
            if s['fitH'] > s['sheetH'] + 1 and s['warn']:
                print('      (overflow at the 0.70 floor - clipped + warning shown, as designed)')
            return s, n, txt

        # ---- case A: empty ----
        pg.goto(URL); pg.wait_for_timeout(400)
        sA, nA, _ = export('A-empty', sA_name := "")
        if sA['scale'] != 1.0: fails.append(f"A-empty: expected scale 1.00, got {sA['scale']}")
        if sA['warn']: fails.append('A-empty: warning shown on empty content')

        # ---- case B: demo (Thai + EN) ----
        pg.on('dialog', lambda d: d.accept())
        pg.click('#btnDemo'); pg.wait_for_timeout(500)
        sB, nB, _ = export('B-demo-th', sB_name := pg.evaluate("document.querySelector('.doc-head h1').textContent"))
        if 'สมชาย' not in sB_name: fails.append('B-demo-th: demo name not rendered')
        pg.click('#langEn'); pg.wait_for_timeout(400)
        sB2, nB2, txtB = export('B-demo-en', 'Somchai')
        if 'Somchai' not in sB2['name']: fails.append('B-demo-en: EN switch failed')

        # ---- case C: extreme overflow ----
        pg.evaluate("d => localStorage.setItem('hermes.careerSummary.v1', JSON.stringify(d))", EXTREME)
        pg.reload(); pg.wait_for_timeout(600)
        sC, nC, _ = export('C-extreme', 'Extreme')
        if not sC['warn']: fails.append('C-extreme: expected the overflow warning to appear')
        if sC['scale'] > 0.71: fails.append(f"C-extreme: expected shrink to the 0.70 floor, got {sC['scale']}")
        print(f"      warning text: {sC['warnText'][:150]}")
        if 'Page' not in str(nC) and nC != 1: fails.append('C-extreme: page count wrong')

        # ---- case D: exotic-but-normal characters must not fall back to a system font ----
        SPECIAL = json.loads(json.dumps(EXTREME))
        SPECIAL['th']['headline'] = 'งบ ฿1,200,000 → ลด 18% » ผ่าน • ทีม ← ปี 2566–2569'
        SPECIAL['th']['projects'][0]['desc'] = 'ใช้จ่าย ฿45,000 → คืน 2% ↑ · ปิดงาน 100%'
        SPECIAL['th']['skills'] = 'Go · Python · ฿งบประมาณ → roadmap'
        pg.evaluate("d => localStorage.setItem('hermes.careerSummary.v1', JSON.stringify(d))", SPECIAL)
        pg.reload(); pg.wait_for_timeout(600)
        sD, nD, txtD = export('D-special-chars', 'ทดสอบ')
        for ch in ['฿','→','»','•','←','↑','·']:
            if ch not in txtD: fails.append(f'D-special-chars: {ch!r} lost in the PDF text layer')

        # ---- case E: six real projects (the layout the user actually wants) ----
        SIX = {
          "th": {"name": SIX_NAME, "role": "Backend / DevOps Engineer", "team": "ตัวอย่าง",
                 "headline": "โปรเจกต์จริง 6 รายการ ต้องพอดี 1 หน้า A4",
                 "projects": SIX_PROJECTS,
                 "skills": "Go, Fiber, MQTT, Docker, CI/CD\nRedis, PostgreSQL",
                 "strengths": "จุดแข็งหนึ่ง\nจุดแข็งสอง\nจุดแข็งสาม",
                 "path": "สนใจ Infrastructure / Network และการประยุกต์ AI กับงานประจำวัน",
                 "email": "a@b.com", "phone": "0800000000", "line": "@x", "portfolio": "github.com/x"},
          "en": {"name": "Six Projects", "role": "Backend / DevOps Engineer", "team": "Sample",
                 "headline": "Six real projects must fit one A4 page",
                 "projects": SIX_PROJECTS,
                 "skills": "Go, Fiber, MQTT, Docker, CI/CD\nRedis, PostgreSQL",
                 "strengths": "Strength one\nStrength two\nStrength three",
                 "path": "Infrastructure / networking, plus applying AI to everyday work",
                 "email": "a@b.com", "phone": "0800000000", "line": "@x", "portfolio": "github.com/x"},
        }
        pg.evaluate("d => localStorage.setItem('hermes.careerSummary.v1', JSON.stringify(d))", SIX)
        pg.reload(); pg.wait_for_timeout(800)
        sE, nE, txtE = export('E-six-projects', SIX_NAME)
        mode = pg.evaluate("() => document.getElementById('sheet').classList.contains('stacked') ? 'single-column' : 'two-column'")
        print(f"      layout chosen: {mode}, scale {sE['scale']:.2f}, warning={sE['warn']}")
        if sE['warn']:
            fails.append('E-six-projects: six projects still do not fit one page (warning shown)')
        if nE != 1:
            fails.append(f'E-six-projects: PDF is {nE} pages')
        for needle in ('Home Network Agent', 'KKU Document Management System', 'PI E-Billing'):
            if needle not in txtE:
                fails.append(f'E-six-projects: {needle!r} missing from the document')

        # the single-column fallback (chosen when two columns cannot fit) must still be one page
        pg.evaluate("() => document.getElementById('sheet').classList.add('stacked')")
        pg.wait_for_timeout(250)
        cols = pg.evaluate("() => getComputedStyle(document.querySelector('.cols')).gridTemplateColumns.split(' ').length")
        print('      stacked fallback: grid columns =', cols)
        if cols != 1:
            fails.append('stacked layout did not collapse to a single column (got %s)' % cols)
        pdfS = pg.pdf(format='A4', print_background=True, prefer_css_page_size=True)
        nS, txtS, _, _ = pages_of(pdfS)
        if nS != 1:
            fails.append('stacked layout produced %s pages' % nS)
        pg.evaluate("() => document.getElementById('sheet').classList.remove('stacked')")

        if errors: fails.append(f'console/page errors: {errors[:5]}')
        b.close()

    print('\n' + ('='*60))
    if fails:
        print('FAIL')
        for f in fails: print(' -', f)
        return 1
    print('PASS — all cases: exactly 1 A4 page, fonts embedded, text vector, no console errors')
    return 0

if __name__ == '__main__':
    sys.exit(main())
