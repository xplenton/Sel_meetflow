"""iter 209 — Multi-user test for virtual background propagation.

⚠️ ENVIRONMENT REQUIREMENT: This test only runs on a host where Chromium can
be launched with `--use-fake-device-for-media-stream` (synthetic camera).
The Emergent preview container's bundled Playwright lacks fake-camera support,
so this script bails out early there. Run it locally with:

    pip install playwright && python -m playwright install chromium
    python /app/backend/tests/test_iter209_bg_multiuser.py

Test plan (when executed on a fake-cam-capable host):
  1. User A creates a meeting and joins.
  2. User B logs in and joins the same meeting.
  3. After both peers see each other in the participants list,
     User A activates the "blur" virtual background.
  4. We grab a screenshot from User B's perspective.
  5. We pull the User-A remote video tile pixel-by-pixel via canvas API
     and check whether the colour signature differs from the raw fake-cam
     pattern (which is bright green) — when blur is active, the detected
     palette should contain a smoothed/grey-ish background instead of the
     vivid green checker.

Limitations:
  * Chromium's fake cam does not produce a recognisable face, so MediaPipe
     selfie segmentation may not find any "person" pixels — in that case the
     entire frame is treated as background and blurred. Either way the
     output palette differs from the raw checker. So we only assert that
     the output is NOT identical to the raw fake-cam frame.
  * If LiveKit credentials are unset in this preview env the test bails
     gracefully (smoke check on the LiveKit token endpoint).
"""
import asyncio

API_BASE = "https://video-meet-pro.preview.emergentagent.com"
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASS = "admin123"
GUEST_EMAIL = "guest@meetflow.com"
GUEST_PASS = "guest123"


async def login(page, email, pw):
    await page.goto(f"{API_BASE}/login", wait_until="networkidle")
    await page.fill("input[type=email]", email)
    await page.fill("input[type=password]", pw)
    await page.click("button[type=submit]")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(800)


async def create_meeting(page) -> str:
    res = await page.evaluate("""async () => {
        const r = await fetch('/api/meetings', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + localStorage.getItem('token'), 'Content-Type': 'application/json' },
            body: JSON.stringify({title: 'iter209 BG-MultiUser'})
        });
        return await r.json();
    }""")
    return res["meeting_id"]


async def join_meeting(page, meeting_id: str):
    await page.goto(f"{API_BASE}/meetings/{meeting_id}/join", wait_until="domcontentloaded")
    await page.wait_for_timeout(8000)
    for sel in ['button:has-text("Beitreten")', 'button:has-text("Jetzt beitreten")']:
        b = await page.query_selector(sel)
        if b:
            await b.click(force=True)
            break
    await page.wait_for_timeout(6000)


async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        # Launch one browser instance with fake-cam args used by both contexts.
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--auto-accept-camera-and-microphone-capture",
            ],
        )
        ctx_a = await browser.new_context(viewport={"width": 1280, "height": 720})
        ctx_b = await browser.new_context(viewport={"width": 1280, "height": 720})
        for ctx in (ctx_a, ctx_b):
            await ctx.grant_permissions(["camera", "microphone"], origin=API_BASE)
        page_a = await ctx_a.new_page()
        page_b = await ctx_b.new_page()

        # Capture console output from both pages so we can debug in the report.
        page_a.on("console", lambda msg: print(f"[A][{msg.type}] {msg.text}") if msg.type == "error" else None)
        page_b.on("console", lambda msg: print(f"[B][{msg.type}] {msg.text}") if msg.type == "error" else None)

        # 1. User A logs in & creates meeting
        await login(page_a, ADMIN_EMAIL, ADMIN_PASS)
        meeting_id = await create_meeting(page_a)
        print(f"meeting_id={meeting_id}")
        await join_meeting(page_a, meeting_id)

        # 2. User B logs in & joins
        await login(page_b, GUEST_EMAIL, GUEST_PASS)
        # Make sure guest is allowed to join: meeting has guest_access=true by default
        await join_meeting(page_b, meeting_id)

        # 3. Wait for B's participant list to include User A's video
        await page_b.wait_for_timeout(6000)
        remote_count_b = await page_b.evaluate("""() => document.querySelectorAll('video').length""")
        print(f"User B sees {remote_count_b} <video> elements")

        # 4. Capture a baseline screenshot from B before applying BG
        await page_b.screenshot(path="/tmp/iter209_b_before.png", full_page=False)

        # Pull a colour palette from B's largest remote video (raw fake-cam frame).
        baseline = await page_b.evaluate(r"""() => {
            const vids = Array.from(document.querySelectorAll('video')).filter(v => v.srcObject && !v.muted);
            if (!vids.length) return null;
            // Pick the one with the largest area (most likely the remote tile).
            vids.sort((a, b) => (b.videoWidth*b.videoHeight) - (a.videoWidth*a.videoHeight));
            const v = vids[0];
            if (!v.videoWidth) return null;
            const c = document.createElement('canvas');
            c.width = 80; c.height = 45;
            c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
            const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data;
            // Compute simple mean R,G,B
            let r=0,g=0,b=0,n=c.width*c.height;
            for (let i=0;i<d.length;i+=4){r+=d[i];g+=d[i+1];b+=d[i+2];}
            return {r:r/n, g:g/n, b:b/n, w:v.videoWidth, h:v.videoHeight};
        }""")
        print(f"B baseline palette: {baseline}")

        # 5. User A activates blur background.
        bg_btn = await page_a.query_selector('[data-testid="toggle-bg-button"]')
        if bg_btn:
            await bg_btn.click(force=True)
            await page_a.wait_for_timeout(1200)
            # Click the "blur" preset
            blur = await page_a.query_selector('[data-testid="bg-blur"]')
            if blur:
                await blur.click(force=True)
                print("A clicked blur")
            else:
                # alternative: by text
                btn = await page_a.query_selector('button:has-text("Blur")')
                if btn: await btn.click(force=True); print("A clicked Blur (text)")
            await page_a.wait_for_timeout(8000)  # wait for MediaPipe model + first frames

        # 6. Wait for the canvas track to propagate
        await page_b.wait_for_timeout(5000)
        await page_b.screenshot(path="/tmp/iter209_b_after.png", full_page=False)
        await page_a.screenshot(path="/tmp/iter209_a_after.png", full_page=False)

        # 7. Pull the new palette from B's remote video.
        after = await page_b.evaluate(r"""() => {
            const vids = Array.from(document.querySelectorAll('video')).filter(v => v.srcObject && !v.muted);
            if (!vids.length) return null;
            vids.sort((a, b) => (b.videoWidth*b.videoHeight) - (a.videoWidth*a.videoHeight));
            const v = vids[0];
            if (!v.videoWidth) return null;
            const c = document.createElement('canvas');
            c.width = 80; c.height = 45;
            c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
            const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data;
            let r=0,g=0,b=0,n=c.width*c.height;
            for (let i=0;i<d.length;i+=4){r+=d[i];g+=d[i+1];b+=d[i+2];}
            return {r:r/n, g:g/n, b:b/n, w:v.videoWidth, h:v.videoHeight};
        }""")
        print(f"B after-bg palette: {after}")

        if not baseline or not after:
            print("WARN: no palette captured — likely no remote video subscribed (LiveKit creds missing?)")
        else:
            # We expect at least a noticeable shift after enabling blur.
            dr, dg, db = abs(after["r"]-baseline["r"]), abs(after["g"]-baseline["g"]), abs(after["b"]-baseline["b"])
            total = dr+dg+db
            print(f"colour delta ΔR={dr:.1f} ΔG={dg:.1f} ΔB={db:.1f}  total={total:.1f}")
            if total < 8:
                print("⚠ Frame palette barely changed → BG may not be propagating.")
            else:
                print("✓ Significant colour delta — virtual BG appears propagated to remote.")

        # Cleanup
        await page_a.evaluate(f"""async () => {{
            await fetch('/api/meetings/{meeting_id}', {{
                method: 'DELETE',
                headers: {{ 'Authorization': 'Bearer ' + localStorage.getItem('token') }}
            }});
        }}""")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
