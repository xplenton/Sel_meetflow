"""Mobile-Layout-Regression-Sweep (Iter 379).

Klickt im iPhone-Viewport (390x844) durch alle Hauptseiten und prueft, ob
`fixed`/`absolute` Elemente (Floating Menus, Banner) Content-Buttons
ueberlappen. So fangen wir Layout-Bugs wie den Chat-`+`/UserMenu-Konflikt
VOR der Production-Deployment ab.

Aufruf:
    python3 /app/scripts/mobile_layout_sweep.py [--url URL] [--email EMAIL] [--password PW]

Exitcode 0 = sauber, 1 = Ueberlappungen gefunden (printet detaillierten Report).
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
from typing import Any

from playwright.async_api import async_playwright

# Seiten, die wir testen. Jeder Eintrag: (Route, list[Selektor-Paare]).
# Bei den Selektor-Paaren prueft das Skript jedes Element der ersten Gruppe
# (typisch: data-testid eines Floating-Elements) gegen jedes der zweiten
# Gruppe (Content-Button). Bei Bedarf koennen pro Seite mehrere Paare
# angegeben werden.
PAGES = [
    "/dashboard",
    "/chat",
    "/meetings",
    "/tasks",
    "/news",
    "/calendar",
]

# Globale Floating-Elemente, die wir auf jeder Seite gegen alle interaktiven
# Buttons prueffen. Diese sind via `fixed`/`absolute` positioniert und
# koennen daher mit darunter liegenden Buttons kollidieren.
FLOATING_SELECTORS = [
    '[data-testid="user-menu-trigger"]',     # Avatar oben rechts
    '[data-testid="notification-bell"]',     # Glocke oben rechts (falls vorhanden)
]


def _boxes_overlap(a: dict, b: dict) -> bool:
    """True wenn die zwei Bounding-Boxes sich raeumlich ueberschneiden."""
    if not a or not b:
        return False
    overlap_x = not (a["right"] <= b["left"] or b["right"] <= a["left"])
    overlap_y = not (a["bottom"] <= b["top"] or b["bottom"] <= a["top"])
    return overlap_x and overlap_y


async def _scan_page(page, route: str) -> list[dict]:
    """Sammelt alle Overlap-Verstoesse auf der aktuell geladenen Seite."""
    violations: list[dict] = []

    # Sammle alle Floating-Boxen
    floating_boxes: list[dict] = []
    for sel in FLOATING_SELECTORS:
        boxes = await page.evaluate(
            """(sel) => {
              const els = document.querySelectorAll(sel);
              return Array.from(els).map(e => {
                const r = e.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return null;
                return {
                  sel: sel,
                  testid: e.getAttribute('data-testid') || null,
                  left: r.left, top: r.top, right: r.right, bottom: r.bottom,
                };
              }).filter(Boolean);
            }""",
            sel,
        )
        floating_boxes.extend(boxes)

    if not floating_boxes:
        # Nichts Schwebendes auf dieser Seite -> nichts zu testen
        return violations

    # Sammle alle Content-Buttons mit data-testid (skippt die Floating selbst).
    floating_testids = {b["testid"] for b in floating_boxes if b.get("testid")}
    content_boxes = await page.evaluate(
        """(skipIds) => {
          const skip = new Set(skipIds);
          const els = document.querySelectorAll('[data-testid]');
          return Array.from(els).filter(e => {
            if (skip.has(e.getAttribute('data-testid'))) return false;
            // Nur interaktive Elemente
            const tag = e.tagName.toLowerCase();
            if (!['button','a','input','select'].includes(tag) && e.getAttribute('role') !== 'button') return false;
            return true;
          }).map(e => {
            const r = e.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return null;
            // Nur Buttons, die im sichtbaren Viewport-Bereich liegen.
            if (r.bottom < 0 || r.top > window.innerHeight) return null;
            return {
              testid: e.getAttribute('data-testid'),
              left: r.left, top: r.top, right: r.right, bottom: r.bottom,
            };
          }).filter(Boolean);
        }""",
        list(floating_testids),
    )

    for fb in floating_boxes:
        for cb in content_boxes:
            if _boxes_overlap(fb, cb):
                violations.append({
                    "route": route,
                    "floating": fb["testid"] or fb["sel"],
                    "content": cb["testid"],
                    "floating_box": {k: fb[k] for k in ("left", "top", "right", "bottom")},
                    "content_box": {k: cb[k] for k in ("left", "top", "right", "bottom")},
                })
    return violations


async def _login(page, base_url: str, email: str, password: str) -> None:
    await page.goto(f"{base_url}/login", timeout=30000)
    await page.wait_for_timeout(2000)
    await page.fill('input[type="email"]', email)
    await page.fill('input[type="password"]', password)
    await page.click('button[type="submit"]')
    await page.wait_for_timeout(4000)
    # Ggf. Onboarding ueberspringen
    try:
        await page.locator('button:has-text("Überspringen")').click(timeout=2000)
        await page.wait_for_timeout(800)
    except Exception:
        pass


async def run_sweep(base_url: str, email: str, password: str) -> tuple[int, list[dict]]:
    all_violations: list[dict] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},  # iPhone-17-aehnlich
                device_scale_factor=3,
            )
            page = await context.new_page()
            await _login(page, base_url, email, password)

            for route in PAGES:
                try:
                    await page.goto(f"{base_url}{route}", timeout=25000)
                    await page.wait_for_timeout(2500)
                    v = await _scan_page(page, route)
                    all_violations.extend(v)
                    print(f"[{route}] {len(v)} Overlap-Verstoss(e)")
                    for x in v:
                        print(f"    {x['floating']} ueberlappt {x['content']}")
                except Exception as e:
                    print(f"[{route}] FEHLER beim Laden: {e}")
        finally:
            await browser.close()
    return (1 if all_violations else 0), all_violations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get(
        "MEETFLOW_PREVIEW_URL",
        "https://video-meet-pro.preview.emergentagent.com",
    ))
    parser.add_argument("--email", default="qa_member@meetflow.com")
    parser.add_argument("--password", default="qa_member_pw_372")
    parser.add_argument("--json", action="store_true",
                        help="Ausgabe nur als JSON (fuer CI-Reports)")
    args = parser.parse_args()

    exit_code, violations = asyncio.run(run_sweep(args.url, args.email, args.password))
    if args.json:
        print(json.dumps({"violations": violations, "count": len(violations)}, indent=2))
    else:
        print()
        if violations:
            print(f"FAIL — {len(violations)} Overlap-Verstoss(e) auf {len({v['route'] for v in violations})} Seiten:")
            for v in violations:
                print(f"  {v['route']:14s}  {v['floating']:30s}  <->  {v['content']}")
        else:
            print("PASS — keine Mobile-Layout-Konflikte gefunden.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
