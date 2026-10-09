"""Browser smoke for the current React SPA, never a live/provider target."""

import argparse
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


def wait_for_server(url, process, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"isolated mock server exited with {process.returncode}")
        try:
            with urlopen(f"{url}/api/auth/me", timeout=1):
                return
        except URLError:
            time.sleep(0.25)
    raise TimeoutError("isolated mock server did not become ready within 30 seconds")


def stop(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="existing isolated loopback mock URL")
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--output", default="data/browser-evidence")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    process = None
    temp_dir = None
    base_url = args.url
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "127.0.0.1",
            "localhost",
        }:
            raise SystemExit("browser smoke refuses non-loopback targets")
    else:
        temp_dir = tempfile.TemporaryDirectory(prefix="browser-smoke-", dir=output)
        db_path = Path(temp_dir.name) / "rehearsal.db"
        base_url = f"http://127.0.0.1:{args.port}"
        log = open(output / "server.log", "w", encoding="utf-8")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "scripts.rehearsal_runner",
                "--serve",
                "--port",
                str(args.port),
                "--db",
                str(db_path),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_for_server(base_url, process)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.shared.provision_operator",
                "--sqlite-path",
                str(db_path),
                "--username",
                "demo_user",
            ],
            check=True,
            timeout=20,
        )

    username = f"browser_{uuid.uuid4().hex[:10]}"
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(f"page: {error}"))
        page.on(
            "console",
            lambda message: (
                errors.append(f"console: {message.text}")
                if message.type == "error"
                else None
            ),
        )
        page.goto(base_url, wait_until="networkidle", timeout=30000)
        expect(page).to_have_url(f"{base_url}/login")
        page.get_by_role("link", name="Create an account").click()
        page.get_by_label("Username").fill(username)
        page.get_by_label("Password", exact=True).fill("testing123")
        page.get_by_label("Confirm Password").fill("testing123")
        page.get_by_role("button", name="Create Account").click()
        expect(page).to_have_url(f"{base_url}/")
        expect(page.get_by_text("Signed in as")).to_be_visible()
        expect(
            page.get_by_role("button", name="Kill all strategies (Operator required)")
        ).to_be_disabled()

        page.get_by_role("link", name="Strategies").click()
        page.get_by_label("Stocks").fill("RELIANCE,TCS")
        page.get_by_role("button", name="Add").click()
        page.get_by_role("button", name="Run on 2 stocks").click()
        expect(page.get_by_text("Created 2 strategy instances.")).to_be_visible()
        expect(page.get_by_text("RELIANCE")).to_be_visible()
        expect(page.get_by_text("TCS")).to_be_visible()
        page.get_by_role("link", name="Overview").click()
        expect(page.get_by_text("Provider readiness evidence")).to_be_visible()
        expect(page.get_by_text("Historical kill certificate")).to_be_visible()
        page.get_by_role("button", name="Sign out").click()
        expect(page).to_have_url(f"{base_url}/login")
        expect(page.get_by_text("Signed in as")).not_to_be_visible()

        page.get_by_label("Username").fill("demo_user")
        page.get_by_label("Password").fill("password123")
        page.get_by_role("button", name="Sign in").click()
        expect(page.get_by_text("Operator")).to_be_visible()
        page.get_by_role("link", name="Orders").click()
        expect(page.get_by_text("PARTIALLY_FILLED")).to_be_visible()
        page.get_by_role("link", name="Overview").click()
        page.once("dialog", lambda dialog: dialog.accept())
        page.get_by_role("button", name="Kill all strategies").click()
        expect(page.get_by_text("SUCCESS")).to_be_visible()
        page.screenshot(path=str(output / "desktop.png"), full_page=True)

        page.set_viewport_size({"width": 375, "height": 812})
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        ), "mobile page overflow"
        expect(page.get_by_text("Provider readiness evidence")).to_be_visible()
        page.screenshot(path=str(output / "mobile.png"), full_page=True)

        assert not errors, errors
        browser.close()
        pw.stop()
    finally:
        stop(process)
        if temp_dir is not None:
            temp_dir.cleanup()

    print(
        "Browser PASS: isolated mock React workflow, account/operator boundaries, partial-fill and historical kill evidence, logout, desktop and 375px mobile"
    )


if __name__ == "__main__":
    main()
