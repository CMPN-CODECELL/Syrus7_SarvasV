"""Opt-in browser integration against an isolated running offline mock backend."""

import argparse
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8011")
    parser.add_argument("--output", default="data/browser-evidence")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        page.goto(args.url)
        expect(page).to_have_url(f"{args.url}/login")
        page.get_by_role("link", name="Create an account").click()
        page.get_by_label("Username").fill("browsercheck")
        page.get_by_label("Password", exact=True).fill("testing123")
        page.get_by_label("Confirm Password").fill("testing123")
        page.get_by_role("button", name="Create Account").click()
        expect(page).to_have_url(f"{args.url}/")
        expect(page.get_by_text("Signed in as")).to_be_visible()

        form = page.locator("#subscription-form")
        expect(form.locator('[name="account_id"]')).to_have_count(0)
        form.get_by_label("Strategy instance ID").fill("reliance-ema-01")
        form.get_by_label("Strategy").select_option("rsi_reversal")
        form.get_by_label("Symbol").fill("RELIANCE")
        form.get_by_role("button", name="Subscribe strategy").click()
        expect(page.locator("#strategy-rows")).to_contain_text("reliance-ema-01")
        expect(page.locator("#strategy-rows")).to_contain_text("rsi reversal")

        expect(page.locator(".safety-strip")).to_be_visible()
        expect(page.locator("#safety-state")).to_have_count(0)
        page.screenshot(path=str(output / "desktop.png"), full_page=True)

        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), "mobile page overflow"
        expect(form).to_be_visible()
        page.screenshot(path=str(output / "mobile.png"), full_page=True)

        assert not errors, errors
        browser.close()

    print(
        "Browser PASS: login gate, automatic account ownership, strategy-only form, "
        "safety indicators and mobile layout"
    )


if __name__ == "__main__":
    main()
