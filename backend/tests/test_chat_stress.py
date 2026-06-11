"""
Comprehensive Chat Stress Test: 1000+ messages with mixed types.
"""
import asyncio
import aiohttp
import time
import os
import random
import string
import json

API_URL = os.environ.get("API_URL", "")
EMAIL = "admin@meetflow.com"
PASSWORD = "admin123"
RESULTS = {"passed": 0, "failed": 0, "errors": []}

def check(name, condition):
    if condition:
        RESULTS["passed"] += 1
        print(f"  PASS: {name}")
    else:
        RESULTS["failed"] += 1
        RESULTS["errors"].append(f"FAIL: {name}")
        print(f"  FAIL: {name}")

async def get_token(session):
    async with session.post(f"{API_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}) as r:
        await r.json()
        for cookie in session.cookie_jar:
            if cookie.key == "access_token":
                return cookie.value
    return ""

async def main():
    if not API_URL:
        print("ERROR: API_URL not set"); return
    print(f"=== Chat Stress Test against {API_URL} ===\n")
    
    async with aiohttp.ClientSession() as session:
        token = await get_token(session)
        if not token:
            print("ERROR: Could not get token"); return
        h = {"Authorization": f"Bearer {token}"}

        # 1. Get/create conversation
        print("[1] Getting test conversation...")
        async with session.get(f"{API_URL}/api/chat/users", headers=h) as r:
            users = await r.json()
        if not users:
            print("ERROR: No users"); return

        async with session.post(f"{API_URL}/api/chat/conversations", headers=h, json={
            "type": "direct", "member_ids": [users[0]["user_id"]]
        }) as r:
            conv = await r.json()
            conv_id = conv.get("conversation_id")
        if not conv_id:
            async with session.get(f"{API_URL}/api/chat/conversations", headers=h) as r:
                convs = await r.json()
                for c in convs:
                    if c.get("type") == "direct":
                        conv_id = c["conversation_id"]; break
        print(f"    Conv: {conv_id}")

        # 2. Send 500 text messages
        print("\n[2] Sending 500 text messages...")
        t0 = time.time()
        sent_ids = []
        fail_count = 0
        for i in range(500):
            msg = f"Stress #{i+1} - {''.join(random.choices(string.ascii_letters, k=20))}"
            try:
                async with session.post(f"{API_URL}/api/chat/conversations/{conv_id}/messages", headers=h, json={
                    "content": msg, "e2e_encrypted": False
                }) as r:
                    if r.status == 200:
                        d = await r.json()
                        sent_ids.append(d["message_id"])
                    else:
                        fail_count += 1
                        if fail_count <= 3:
                            t = await r.text()
                            print(f"    FAIL #{i+1}: {r.status} {t[:60]}")
            except Exception as e:
                fail_count += 1
                if fail_count <= 3: print(f"    ERR #{i+1}: {e}")
        el = time.time() - t0
        print(f"    Sent: {len(sent_ids)}/500 in {el:.1f}s ({len(sent_ids)/max(el,0.1):.0f}/s), Failed: {fail_count}")
        check("500 text messages sent", fail_count < 25)

        # 3. Verify retrieval
        print("\n[3] Verifying messages retrievable...")
        async with session.get(f"{API_URL}/api/chat/conversations/{conv_id}/messages?limit=80", headers=h) as r:
            msgs = await r.json()
        print(f"    Got {len(msgs)} (limit 80)")
        check("Messages retrievable", len(msgs) >= 50)

        # 4. Upload 20 file types
        print("\n[4] Uploading 20 files...")
        files = [
            ("test.txt", "text/plain", b"Hello World"),
            ("test.csv", "text/csv", b"a,b\n1,2"),
            ("test.json", "application/json", b'{"k":"v"}'),
            ("test.html", "text/html", b"<h1>Hi</h1>"),
            ("test.md", "text/markdown", b"# Title"),
            ("test.xml", "text/xml", b"<r/>"),
            ("test.log", "text/plain", b"LOG:ok"),
            ("img.png", "image/png", b'\x89PNG\r\n\x1a\n' + b'\x00'*50),
            ("photo.jpg", "image/jpeg", b'\xff\xd8\xff\xe0' + b'\x00'*50),
            ("doc.pdf", "application/pdf", b'%PDF-1.4' + b'\x00'*50),
            ("sheet.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b'\x00'*50),
            ("slide.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", b'\x00'*50),
            ("arc.zip", "application/zip", b'PK\x03\x04' + b'\x00'*50),
            ("sound.mp3", "audio/mpeg", b'\xff\xfb' + b'\x00'*50),
            ("video.mp4", "video/mp4", b'\x00\x00\x00\x18ftyp' + b'\x00'*50),
            ("style.css", "text/css", b"body{}"),
            ("app.js", "application/javascript", b"var x=1;"),
            ("cfg.yaml", "text/yaml", b"k: v"),
            ("readme.txt", "text/plain", b"README"),
            ("data.bin", "application/octet-stream", bytes(range(128))),
        ]
        file_ids = []
        ff = 0
        for fn, ft, fc in files:
            try:
                form = aiohttp.FormData()
                form.add_field('file', fc, filename=fn, content_type=ft)
                async with session.post(f"{API_URL}/api/chat/conversations/{conv_id}/upload", headers=h, data=form) as r:
                    if r.status == 200:
                        d = await r.json()
                        file_ids.append(d["message_id"])
                        if not d.get("file_url") or not d.get("file_name"):
                            print(f"    WARN: Missing fields for {fn}")
                    else:
                        ff += 1; t = await r.text()
                        print(f"    FAIL {fn}: {r.status} {t[:50]}")
            except Exception as e:
                ff += 1; print(f"    ERR {fn}: {e}")
        print(f"    OK: {len(file_ids)}/20, Fail: {ff}")
        check("20 file types uploaded", len(file_ids) >= 18)

        # 5. Verify downloads
        print("\n[5] Verifying downloads...")
        dl_ok = 0
        async with session.get(f"{API_URL}/api/chat/conversations/{conv_id}/messages?limit=200", headers=h) as r:
            all_msgs = await r.json()
        for mid in file_ids[:5]:
            fm = next((m for m in all_msgs if m["message_id"] == mid), None)
            if fm and fm.get("file_url"):
                async with session.get(f"{API_URL}{fm['file_url']}") as fr:
                    if fr.status == 200: dl_ok += 1
                async with session.get(f"{API_URL}{fm['file_url']}?download=1") as fr:
                    if fr.status == 200 and "attachment" in fr.headers.get("Content-Disposition", ""):
                        pass
        print(f"    Downloads OK: {dl_ok}/5")
        check("File downloads work", dl_ok >= 4)

        # 6. Send 500 more mixed messages
        print("\n[6] Sending 500 mixed-content messages...")
        t0 = time.time()
        ok6 = 0; fail6 = 0
        pats = [
            lambda i: f"**Bold** #{i}",
            lambda i: f"@mention #{i}",
            lambda i: f"K{i}",
            lambda i: f"{'Lang '*20}#{i}",
            lambda i: f"äöü ß #{i}",
            lambda i: f"👍❤️ #{i}",
            lambda i: f"`code={i}`",
            lambda i: f"> Zitat\n#{i}",
            lambda i: f"https://x.com/{i}",
            lambda i: f"!!!Dringend #{i}",
        ]
        for i in range(500):
            try:
                async with session.post(f"{API_URL}/api/chat/conversations/{conv_id}/messages", headers=h, json={
                    "content": pats[i%10](i+501), "e2e_encrypted": False
                }) as r:
                    if r.status == 200: ok6 += 1
                    else: fail6 += 1
            except: fail6 += 1
        el = time.time() - t0
        print(f"    OK: {ok6}/500 in {el:.1f}s, Fail: {fail6}")
        check("500 mixed messages sent", fail6 < 25)

        # 7. Reactions
        print("\n[7] Adding 50 reactions...")
        emojis = ['👍','❤️','😂','😮','😢','🎉','🔥','👀']
        rok = 0
        for mid in sent_ids[:50]:
            try:
                async with session.post(f"{API_URL}/api/chat/messages/{mid}/reactions", headers=h, json={"emoji": random.choice(emojis)}) as r:
                    if r.status == 200:
                        d = await r.json()
                        if d.get("reactions") is not None: rok += 1
            except: pass
        print(f"    OK: {rok}/50")
        check("Reactions work", rok >= 40)

        # 8. Message ordering
        print("\n[8] Checking order...")
        async with session.get(f"{API_URL}/api/chat/conversations/{conv_id}/messages?limit=80", headers=h) as r:
            om = await r.json()
        ordered = all(om[i]["created_at"] <= om[i+1]["created_at"] for i in range(len(om)-1)) if len(om) >= 2 else True
        print(f"    Ordered: {ordered}")
        check("Chronological order", ordered)

        # 9. Conv list
        print("\n[9] Conv list updated...")
        async with session.get(f"{API_URL}/api/chat/conversations", headers=h) as r:
            convs = await r.json()
        tc = next((c for c in convs if c["conversation_id"] == conv_id), None)
        check("Conv list has last_message", tc and tc.get("last_message") is not None)

        # 10. Pagination
        print("\n[10] Pagination...")
        async with session.get(f"{API_URL}/api/chat/conversations/{conv_id}/messages?limit=20", headers=h) as r:
            p1 = await r.json()
        if len(p1) >= 2:
            async with session.get(f"{API_URL}/api/chat/conversations/{conv_id}/messages?limit=20&before={p1[0]['created_at']}", headers=h) as r:
                p2 = await r.json()
            overlap = any(m["message_id"] in [x["message_id"] for x in p1] for m in p2)
            print(f"    P1:{len(p1)} P2:{len(p2)} overlap:{overlap}")
            check("No page overlap", not overlap)
        else:
            check("No page overlap", True)

        # 11. Interleaved text+file
        print("\n[11] Rapid interleaved sends...")
        iok = 0
        for i in range(20):
            try:
                async with session.post(f"{API_URL}/api/chat/conversations/{conv_id}/messages", headers=h, json={
                    "content": f"Inter #{i}", "e2e_encrypted": False
                }) as r:
                    if r.status == 200: iok += 1
                form = aiohttp.FormData()
                form.add_field('file', f"File#{i}".encode(), filename=f"i_{i}.txt", content_type="text/plain")
                async with session.post(f"{API_URL}/api/chat/conversations/{conv_id}/upload", headers=h, data=form) as r:
                    if r.status == 200: iok += 1
            except: pass
        print(f"    OK: {iok}/40")
        check("Interleaved sends work", iok >= 35)

        # 12. Total count
        print("\n[12] Final count...")
        total = 0
        cursor = None
        for _ in range(100):
            url = f"{API_URL}/api/chat/conversations/{conv_id}/messages?limit=200"
            if cursor: url += f"&before={cursor}"
            async with session.get(url, headers=h) as r:
                batch = await r.json()
            if not batch: break
            total += len(batch)
            cursor = batch[0]["created_at"]
            if len(batch) < 200: break
        print(f"    Total: {total}")
        check(f"Total >= 1000 (got {total})", total >= 1000)

    print(f"\n{'='*50}")
    print(f"RESULTS: {RESULTS['passed']} passed, {RESULTS['failed']} failed")
    if RESULTS["errors"]:
        for e in RESULTS["errors"]: print(f"  - {e}")
    print(f"{'='*50}")
    with open("/app/test_reports/chat_stress_test.json", "w") as f:
        json.dump(RESULTS, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
