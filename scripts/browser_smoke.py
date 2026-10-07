"""Opt-in browser integration against an isolated running offline mock backend."""

import argparse
from pathlib import Path
from urllib.request import urlopen
import json

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8011')
    parser.add_argument('--output', default='data/browser-evidence')
    args = parser.parse_args()
    state = json.load(urlopen(args.url+'/api/state', timeout=5))
    if state['mode'] != 'MOCK / REPLAY' or state['storage'] != 'SQLITE_OFFLINE':
        raise RuntimeError('browser mutation checks require isolated offline mock backend')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width':1440,'height':1000})
        errors = []
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(args.url)
        expect(page.locator('#health')).to_contain_text('RECOVERING')
        page.locator('[data-action="demo"]').click()
        expect(page.locator('#subscriptions tr')).to_have_count(3)
        expect(page.locator('#candles')).to_contain_text('5m')
        expect(page.locator('#proof')).to_contain_text('VERIFIED')
        expect(page.locator('#budgets tr')).to_have_count(3)
        form = page.locator('#policy-form')
        for name,value in {'strategy':'momentum','max_daily_loss':'500','max_position':'80','max_orders_per_minute':'10'}.items():
            form.locator(f'[name="{name}"]').fill(value)
        form.locator('button').click()
        expect(page.locator('#budgets')).to_contain_text('/ 80')
        page.locator('[data-action="failure-lab/partial"]').click()
        expect(page.locator('#orders')).to_contain_text('PARTIALLY_FILLED')
        page.locator('[data-action="failure-lab/rejection"]').click()
        expect(page.locator('#orders')).to_contain_text('REJECTED')
        page.locator('[data-action="failure-lab/position_limit"]').click()
        expect(page.locator('#lab-result')).to_contain_text('RISK_MAX_POSITION')
        page.locator('[data-action="kill"]').click()
        expect(page.locator('#certificate')).to_contain_text('SUCCESS',timeout=15000)
        expect(page.locator('#health')).to_contain_text('KILLED')
        page.screenshot(path=str(output/'desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'mobile page overflow'
        page.screenshot(path=str(output/'mobile.png'),full_page=True)
        page.route('**/api/state',lambda route:route.abort())
        expect(page.locator('#health')).to_contain_text('UNKNOWN',timeout=6000)
        expect(page.locator('#proof')).to_contain_text('UNKNOWN')
        page.unroute('**/api/state')
        expect(page.locator('#health')).to_contain_text('KILLED',timeout=6000)
        assert not errors, errors
        browser.close()
    print('Browser PASS: desktop/mobile, replay, policies, partial/reject/risk, kill and unavailable backend')


if __name__ == '__main__':
    main()
