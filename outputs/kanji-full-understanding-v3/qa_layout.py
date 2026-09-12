"""Exercise the mobile preview and inspect every chapter at the largest type size."""
from pathlib import Path
from urllib.parse import quote
import argparse
import json
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-url', default='http://127.0.0.1:32872/', help='URL of the preview server')
parser.add_argument('--chromium-path', help='Optional Chromium executable; defaults to Playwright Chromium')
args = parser.parse_args()
BASE = args.base_url.rstrip('/') + '/'
(ROOT / 'qa').mkdir(exist_ok=True)
assembled = json.loads((ROOT / 'assembled.json').read_text())
errors = []; measurements = []; anchor_checks = 0

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=args.chromium_path)
    page = browser.new_page(viewport={'width': 390, 'height': 844}, device_scale_factor=1)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(BASE + quote('阅读预览.html'))
    page.evaluate('document.fonts.ready')
    page.screenshot(path=str(ROOT / 'qa/mobile-index.png'))
    page.locator('#search').fill('いける')
    assert page.locator('.indexcard:visible').count() == 1
    assert page.locator('.indexcard:visible .glyph').inner_text() == '生'
    page.screenshot(path=str(ROOT / 'qa/mobile-search.png'))
    page.locator('.indexcard:visible').click()
    page.locator('.readinglink').filter(has=page.locator('.kana', has_text='いける')).click()
    page.screenshot(path=str(ROOT / 'qa/mobile-ikeru.png'))
    page.locator('#kana-toggle').click()
    assert page.locator('#kana-toggle').get_attribute('aria-pressed') == 'true'
    assert page.locator('.reading').first.evaluate('(e)=>getComputedStyle(e).visibility') == 'hidden'
    page.locator('#kana-toggle').click()
    assert page.locator('.reading').first.evaluate('(e)=>getComputedStyle(e).visibility') == 'visible'
    page.goto(BASE + 'preview/patterns.html#patterns-s5')
    page.screenshot(path=str(ROOT / 'qa/mobile-patterns.png'))
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.goto(BASE + quote('阅读预览.html'))
    page.screenshot(path=str(ROOT / 'qa/desktop-index.png'))
    page.goto(BASE + 'preview/char-4e0b.html')
    page.screenshot(path=str(ROOT / 'qa/desktop-reading-map.png'))
    page.set_viewport_size({'width': 320, 'height': 760})
    paths = [quote('阅读预览.html'), 'preview/intro.html', 'preview/patterns.html', 'preview/practice.html', 'preview/practice-answers.html']
    paths += [f'preview/char-{ord(c):x}.html' for c in assembled['order']]
    for i, path in enumerate(paths):
        page.goto(BASE + path)
        for _ in range(7): page.locator('#larger').click()
        measurement = page.evaluate('''() => ({width: innerWidth, document:document.documentElement.scrollWidth,
          font:getComputedStyle(document.body).fontSize, brokenReadings:[...document.querySelectorAll('.readinglink .kana')].filter(e=>{
          const s=getComputedStyle(e);return e.getBoundingClientRect().height>parseFloat(s.lineHeight)*1.2}).map(e=>e.textContent)})''')
        measurement['path'] = path
        measurements.append(measurement)
        assert measurement['document'] <= measurement['width'] + 1, ('overflow', measurement)
        assert not measurement['brokenReadings'], ('reading label wraps', measurement)
        links = page.locator('.readinglink')
        for j in range(links.count()):
            link = links.nth(j); target = link.get_attribute('href')
            link.click()
            position = page.locator(target).evaluate('(e)=>({top:e.getBoundingClientRect().top,bottom:e.getBoundingClientRect().bottom})')
            header = page.locator('.topbar').bounding_box()
            assert position['top'] >= header['height'] - 1, ('anchor obscured', path, target, position, header)
            assert position['top'] < 740, ('anchor not reached', path, target, position)
            anchor_checks += 1
        if path in ['preview/char-751f.html', 'preview/char-4e0b.html', 'preview/patterns.html']:
            page.evaluate('scrollTo(0,0)')
            page.screenshot(path=str(ROOT / ('qa/mobile-large-' + Path(path).stem + '.png')))
        if i % 40 == 0: print('Checked mobile pages:', i + 1, flush=True)
    browser.close()
assert not errors, errors
report = {'pages_checked_at_320px_26px_type':len(measurements), 'reading_links_clicked':anchor_checks,
          'search_and_kana_toggle':'passed', 'browser_errors':errors, 'measurements':measurements}
(ROOT / 'qa/layout.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='measurements'}, ensure_ascii=False, indent=2))
