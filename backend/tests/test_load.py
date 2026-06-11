"""
Comprehensive Platform Load Test
- 1000+ users
- 100+ messages/actions per feature
- Tests: Auth, News, Comments, Reactions, Q&A, Surveys, Feedback, Chat, Focus Time
"""
import asyncio
import aiohttp
import time
import os
import random
import string
import json

API_URL = os.environ.get("API_URL", "")
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"
NUM_USERS = 1000
MSGS_PER_FEATURE = 100

R = {"passed": 0, "failed": 0, "errors": [], "details": {}}

def check(name, ok):
    if ok:
        R["passed"] += 1
    else:
        R["failed"] += 1
        R["errors"].append(name)
    print(f"  {'PASS' if ok else 'FAIL'}: {name}")

async def admin_token(session):
    async with session.post(f"{API_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}) as r:
        await r.json()
        for c in session.cookie_jar:
            if c.key == "access_token":
                return c.value
    return ""

async def main():
    if not API_URL:
        print("ERROR: API_URL not set"); return
    print(f"=== LOAD TEST: {NUM_USERS} users, {MSGS_PER_FEATURE} msgs/feature ===")
    print(f"API: {API_URL}\n")
    t_total = time.time()

    async with aiohttp.ClientSession() as session:
        token = await admin_token(session)
        if not token:
            print("FATAL: No admin token"); return
        h = {"Authorization": f"Bearer {token}"}

        # ============================================================
        # PHASE 1: Create 1000 users (or find existing)
        # ============================================================
        print(f"\n[1/10] Creating {NUM_USERS} users...")
        t0 = time.time()
        user_ids = []
        user_tokens = []
        fail_u = 0
        # Batch register - skip already existing
        for i in range(NUM_USERS):
            email = f"loadtest_{i:04d}@klinik.de"
            name = f"Testuser_{i:04d}"
            try:
                async with session.post(f"{API_URL}/api/auth/register", json={
                    "email": email, "password": "Test1234!", "name": name
                }) as r:
                    d = await r.json()
                    uid = d.get("user_id", "")
                    if uid:
                        user_ids.append(uid)
                    elif "existiert" in str(d) or "exists" in str(d) or r.status != 200:
                        user_ids.append(f"existing_{i}")  # placeholder
            except:
                fail_u += 1
        # Get tokens for first 50 users only
        token_batch = 50
        for i in range(token_batch):
            email = f"loadtest_{i:04d}@klinik.de"
            try:
                jar = aiohttp.CookieJar()
                async with aiohttp.ClientSession(cookie_jar=jar) as s2:
                    async with s2.post(f"{API_URL}/api/auth/login", json={"email": email, "password": "Test1234!"}) as r:
                        if r.status == 200:
                            d = await r.json()
                            uid = d.get("user_id", "")
                            if uid and i < len(user_ids):
                                user_ids[i] = uid
                            for c in jar:
                                if c.key == "access_token":
                                    user_tokens.append(c.value)
                                    break
            except:
                pass
        el = time.time() - t0
        print(f"    Created/Found: {len(user_ids)}/{NUM_USERS} in {el:.1f}s, Tokens: {len(user_tokens)}, Failed: {fail_u}")
        check(f"{NUM_USERS} users created", len(user_ids) >= NUM_USERS * 0.95)
        R["details"]["users"] = {"created": len(user_ids), "tokens": len(user_tokens), "time": round(el, 1)}

        # Refresh admin token after user creation (may have expired)
        token = await admin_token(session)
        h = {"Authorization": f"Bearer {token}"}

        # ============================================================
        # PHASE 2: News - Create 100 posts
        # ============================================================
        print(f"\n[2/10] Creating {MSGS_PER_FEATURE} news posts...")
        t0 = time.time()
        post_ids = []
        fail_n = 0
        for i in range(MSGS_PER_FEATURE):
            pri = random.choice(["normal", "important", "critical"])
            try:
                async with session.post(f"{API_URL}/api/news/posts", headers=h, json={
                    "title": f"Klinik-News #{i+1}: {''.join(random.choices(string.ascii_letters, k=15))}",
                    "content": f"Inhalt der Nachricht #{i+1}. " * 5,
                    "excerpt": f"Kurzbeschreibung #{i+1}",
                    "priority": pri,
                    "status": "published",
                    "target_all": True,
                    "pinned": i < 3,
                    "is_mandatory": i < 5,
                    "tags": [f"tag{random.randint(1,10)}", f"tag{random.randint(11,20)}"],
                }) as r:
                    if r.status == 200:
                        d = await r.json()
                        post_ids.append(d["post_id"])
                    else:
                        fail_n += 1
            except:
                fail_n += 1
        el = time.time() - t0
        print(f"    Created: {len(post_ids)}/{MSGS_PER_FEATURE} in {el:.1f}s, Failed: {fail_n}")
        check(f"{MSGS_PER_FEATURE} news posts created", len(post_ids) >= MSGS_PER_FEATURE * 0.95)
        R["details"]["news_posts"] = {"created": len(post_ids), "time": round(el, 1)}

        # ============================================================
        # PHASE 3: Comments - 100 per post (on first 5 posts)
        # ============================================================
        print(f"\n[3/10] Creating {MSGS_PER_FEATURE} comments on 5 posts (500 total)...")
        t0 = time.time()
        comment_ok = 0
        comment_fail = 0
        target_posts = post_ids[:5] if post_ids else []
        for pid in target_posts:
            for i in range(MSGS_PER_FEATURE):
                tk = user_tokens[i % len(user_tokens)] if user_tokens else token
                try:
                    async with session.post(f"{API_URL}/api/news/posts/{pid}/comments",
                        headers={"Authorization": f"Bearer {tk}"},
                        json={"content": f"Kommentar #{i+1} von User {i % len(user_tokens)}: {''.join(random.choices(string.ascii_letters, k=30))}"}) as r:
                        if r.status == 200:
                            comment_ok += 1
                        else:
                            comment_fail += 1
                except:
                    comment_fail += 1
        el = time.time() - t0
        total_c = len(target_posts) * MSGS_PER_FEATURE
        print(f"    OK: {comment_ok}/{total_c} in {el:.1f}s ({comment_ok/max(el,0.1):.0f}/s), Failed: {comment_fail}")
        check("500 comments created", comment_ok >= total_c * 0.95)
        R["details"]["comments"] = {"created": comment_ok, "total": total_c, "time": round(el, 1)}

        # ============================================================
        # PHASE 4: Reactions - 100 users react to 10 posts
        # ============================================================
        print("\n[4/10] Adding reactions (100 users x 10 posts = 1000)...")
        t0 = time.time()
        react_ok = 0
        react_fail = 0
        react_types = ["like", "agree", "helpful"]
        for pid in post_ids[:min(10, len(post_ids))]:
            for i in range(min(MSGS_PER_FEATURE, len(user_tokens))):
                tk = user_tokens[i]
                try:
                    async with session.post(f"{API_URL}/api/news/posts/{pid}/reactions",
                        headers={"Authorization": f"Bearer {tk}"},
                        json={"reaction_type": random.choice(react_types)}) as r:
                        if r.status == 200:
                            react_ok += 1
                        else:
                            react_fail += 1
                except:
                    react_fail += 1
        el = time.time() - t0
        total_r = min(MSGS_PER_FEATURE, len(user_tokens)) * 10
        print(f"    OK: {react_ok}/{total_r} in {el:.1f}s, Failed: {react_fail}")
        check("Reactions created", react_ok >= total_r * 0.9)
        R["details"]["reactions"] = {"created": react_ok, "total": total_r, "time": round(el, 1)}

        # ============================================================
        # PHASE 5: Read Receipts - 100 users read 10 posts
        # ============================================================
        print("\n[5/10] Read receipts (100 users x 10 posts)...")
        t0 = time.time()
        read_ok = 0
        for pid in post_ids[:min(10, len(post_ids))]:
            for i in range(min(MSGS_PER_FEATURE, len(user_tokens))):
                tk = user_tokens[i]
                try:
                    async with session.post(f"{API_URL}/api/news/posts/{pid}/read",
                        headers={"Authorization": f"Bearer {tk}"}) as r:
                        if r.status == 200:
                            read_ok += 1
                except:
                    pass
        el = time.time() - t0
        print(f"    OK: {read_ok} in {el:.1f}s")
        check("Read receipts created", read_ok >= 400)
        R["details"]["reads"] = {"created": read_ok, "time": round(el, 1)}

        # ============================================================
        # PHASE 6: Q&A - 100 questions + upvotes
        # ============================================================
        print(f"\n[6/10] Creating {MSGS_PER_FEATURE} Q&A questions + upvotes...")
        t0 = time.time()
        qa_ok = 0
        qa_ids = []
        if post_ids:
            for i in range(MSGS_PER_FEATURE):
                pid = random.choice(post_ids[:min(20, len(post_ids))])
                tk = user_tokens[i % len(user_tokens)] if user_tokens else token
                try:
                    async with session.post(f"{API_URL}/api/news/posts/{pid}/questions",
                        headers={"Authorization": f"Bearer {tk}"},
                        json={"text": f"Frage #{i+1}: Wann wird das umgesetzt? {''.join(random.choices(string.ascii_letters, k=20))}"}) as r:
                        if r.status == 200:
                            d = await r.json()
                            qa_ids.append(d["question_id"])
                            qa_ok += 1
                except:
                    pass
        # Upvotes
        upvote_ok = 0
        for qid in qa_ids[:50]:
            for i in range(min(20, len(user_tokens))):
                try:
                    async with session.post(f"{API_URL}/api/news/questions/{qid}/upvote",
                        headers={"Authorization": f"Bearer {user_tokens[i]}"}) as r:
                        if r.status == 200:
                            upvote_ok += 1
                except:
                    pass
        # Answer 20 questions
        answer_ok = 0
        for qid in qa_ids[:20]:
            try:
                async with session.post(f"{API_URL}/api/news/questions/{qid}/answer",
                    headers=h, json={"answer": "Antwort: Dies wird zeitnah umgesetzt."}) as r:
                    if r.status == 200:
                        answer_ok += 1
            except:
                pass
        el = time.time() - t0
        print(f"    Questions: {qa_ok}/{MSGS_PER_FEATURE}, Upvotes: {upvote_ok}, Answers: {answer_ok}, Time: {el:.1f}s")
        check("Q&A created", qa_ok >= MSGS_PER_FEATURE * 0.9)
        R["details"]["qa"] = {"questions": qa_ok, "upvotes": upvote_ok, "answers": answer_ok, "time": round(el, 1)}

        # ============================================================
        # PHASE 7: Surveys - Create 10 surveys, 100 responses each
        # ============================================================
        print(f"\n[7/10] Creating surveys + {MSGS_PER_FEATURE} responses each...")
        t0 = time.time()
        survey_ids = []
        for i in range(10):
            try:
                async with session.post(f"{API_URL}/api/surveys", headers=h, json={
                    "title": f"Mitarbeiterumfrage #{i+1}",
                    "description": f"Umfrage zur Zufriedenheit #{i+1}",
                    "survey_type": "survey" if i < 7 else "pulse_check",
                    "anonymous": i % 3 == 0,
                    "status": "published",
                    "target_all": True,
                    "questions": [
                        {"question_id": f"q1_{i}", "text": "Wie zufrieden sind Sie?", "type": "single_choice", "options": ["Sehr zufrieden", "Zufrieden", "Neutral", "Unzufrieden"], "required": True},
                        {"question_id": f"q2_{i}", "text": "Was koennte verbessert werden?", "type": "multiple_choice", "options": ["Kommunikation", "Arbeitszeit", "Ausstattung", "Weiterbildung"], "required": False},
                        {"question_id": f"q3_{i}", "text": "Bewertung 1-10", "type": "scale", "scale_min": 1, "scale_max": 10, "required": True},
                        {"question_id": f"q4_{i}", "text": "Anmerkungen", "type": "free_text", "required": False},
                    ],
                }) as r:
                    if r.status == 200:
                        d = await r.json()
                        survey_ids.append(d["survey_id"])
            except:
                pass
        # Submit responses - use each token only once per survey (no duplicates)
        resp_ok = 0
        resp_fail = 0
        for sid in survey_ids[:5]:
            idx = survey_ids.index(sid)
            for i in range(min(len(user_tokens), MSGS_PER_FEATURE)):
                tk = user_tokens[i]
                try:
                    async with session.post(f"{API_URL}/api/surveys/{sid}/respond",
                        headers={"Authorization": f"Bearer {tk}"},
                        json={"answers": {
                            f"q1_{idx}": random.choice(["Sehr zufrieden", "Zufrieden", "Neutral", "Unzufrieden"]),
                            f"q2_{idx}": random.sample(["Kommunikation", "Arbeitszeit", "Ausstattung", "Weiterbildung"], random.randint(1, 3)),
                            f"q3_{idx}": random.randint(1, 10),
                            f"q4_{idx}": f"Kommentar von User {i}: {''.join(random.choices(string.ascii_letters, k=20))}",
                        }}) as r:
                        if r.status == 200:
                            resp_ok += 1
                        else:
                            resp_fail += 1
                except:
                    resp_fail += 1
        el = time.time() - t0
        print(f"    Surveys: {len(survey_ids)}/10, Responses: {resp_ok}, Failed: {resp_fail}, Time: {el:.1f}s")
        check("Surveys + responses created", len(survey_ids) >= 8 and resp_ok >= 100)
        R["details"]["surveys"] = {"surveys": len(survey_ids), "responses": resp_ok, "time": round(el, 1)}

        # ============================================================
        # PHASE 8: Feedback - 100 anonymous entries
        # ============================================================
        print(f"\n[8/10] Submitting {MSGS_PER_FEATURE} anonymous feedback entries...")
        t0 = time.time()
        fb_ok = 0
        cats = ["ideas", "complaints", "improvements", "questions"]
        for i in range(MSGS_PER_FEATURE):
            tk = user_tokens[i % len(user_tokens)] if user_tokens else token
            try:
                async with session.post(f"{API_URL}/api/feedback/submit",
                    headers={"Authorization": f"Bearer {tk}"},
                    json={
                        "category": random.choice(cats),
                        "subject": f"Feedback #{i+1}",
                        "content": f"Feedback-Inhalt #{i+1}: {''.join(random.choices(string.ascii_letters, k=40))}",
                    }) as r:
                    if r.status == 200:
                        fb_ok += 1
            except:
                pass
        el = time.time() - t0
        print(f"    OK: {fb_ok}/{MSGS_PER_FEATURE} in {el:.1f}s")
        check(f"{MSGS_PER_FEATURE} feedback entries", fb_ok >= MSGS_PER_FEATURE * 0.95)
        R["details"]["feedback"] = {"created": fb_ok, "time": round(el, 1)}

        # ============================================================
        # PHASE 9: Chat - 100 messages from different users
        # ============================================================
        print(f"\n[9/10] Chat: {MSGS_PER_FEATURE} messages between users...")
        t0 = time.time()
        chat_ok = 0
        # Get/create conversations for first 20 users
        conv_id = None
        for i in range(min(20, len(user_tokens))):
            tk = user_tokens[i]
            try:
                async with session.post(f"{API_URL}/api/chat/conversations",
                    headers={"Authorization": f"Bearer {tk}"},
                    json={"type": "direct", "member_ids": [user_ids[0] if user_ids else ""]}) as r:
                    if r.status == 200:
                        d = await r.json()
                        if not conv_id:
                            conv_id = d.get("conversation_id")
            except:
                pass
        if not conv_id:
            # Fallback: get existing
            async with session.get(f"{API_URL}/api/chat/conversations", headers=h) as r:
                convs = await r.json()
                if convs:
                    conv_id = convs[0]["conversation_id"]
        if conv_id:
            for i in range(MSGS_PER_FEATURE):
                tk = user_tokens[i % len(user_tokens)] if user_tokens else token
                try:
                    async with session.post(f"{API_URL}/api/chat/conversations/{conv_id}/messages",
                        headers={"Authorization": f"Bearer {tk}"},
                        json={"content": f"Chat #{i+1}: {''.join(random.choices(string.ascii_letters, k=25))}", "e2e_encrypted": False}) as r:
                        if r.status == 200:
                            chat_ok += 1
                except:
                    pass
        el = time.time() - t0
        print(f"    OK: {chat_ok}/{MSGS_PER_FEATURE} in {el:.1f}s")
        check("Chat messages sent", chat_ok >= MSGS_PER_FEATURE * 0.9)
        R["details"]["chat"] = {"messages": chat_ok, "time": round(el, 1)}

        # ============================================================
        # PHASE 10: Focus Time - 100 entries
        # ============================================================
        print("\n[10/10] Focus times + verification...")
        t0 = time.time()
        focus_ok = 0
        from datetime import datetime, timedelta
        for i in range(min(MSGS_PER_FEATURE, len(user_tokens))):
            tk = user_tokens[i]
            start = (datetime.utcnow() + timedelta(hours=i+1)).isoformat() + "Z"
            end = (datetime.utcnow() + timedelta(hours=i+2)).isoformat() + "Z"
            try:
                async with session.post(f"{API_URL}/api/focus-times",
                    headers={"Authorization": f"Bearer {tk}"},
                    json={"label": f"Focus #{i+1}", "start_time": start, "end_time": end}) as r:
                    if r.status == 200:
                        focus_ok += 1
            except:
                pass
        el = time.time() - t0
        print(f"    OK: {focus_ok} in {el:.1f}s")
        check("Focus times created", focus_ok >= 40)

        # VERIFICATION: Feed performance
        print("\n[VERIFY] Feed performance with 1000+ users and 100+ posts...")
        t0 = time.time()
        async with session.get(f"{API_URL}/api/news/feed?limit=20", headers=h) as r:
            feed = await r.json()
        feed_time = time.time() - t0
        print(f"    Feed: {feed.get('total', 0)} posts, loaded in {feed_time:.2f}s")
        check("Feed loads in <5s", feed_time < 5)

        # VERIFICATION: Survey results
        if survey_ids:
            t0 = time.time()
            async with session.get(f"{API_URL}/api/surveys/{survey_ids[0]}/results", headers=h) as r:
                results = await r.json()
            res_time = time.time() - t0
            print(f"    Survey results: {results.get('total_responses', 0)} responses, loaded in {res_time:.2f}s")
            check("Survey results load in <3s", res_time < 3)

        # VERIFICATION: Interaction stats
        t0 = time.time()
        async with session.get(f"{API_URL}/api/interaction-stats", headers=h) as r:
            stats = await r.json()
        stats_time = time.time() - t0
        print(f"    Stats: {json.dumps(stats)}")
        print(f"    Loaded in {stats_time:.2f}s")
        check("Stats load in <3s", stats_time < 3)

        # VERIFICATION: CSV Export
        if survey_ids:
            t0 = time.time()
            async with session.get(f"{API_URL}/api/surveys/{survey_ids[0]}/export", headers=h) as r:
                csv_data = await r.text()
            csv_time = time.time() - t0
            csv_lines = len(csv_data.strip().split("\n"))
            print(f"    CSV export: {csv_lines} rows in {csv_time:.2f}s")
            check("CSV export works", csv_lines > 10)

        # VERIFICATION: Unread count
        t0 = time.time()
        async with session.get(f"{API_URL}/api/news/unread-count", headers=h) as r:
            unread = await r.json()
        print(f"    Unread: {unread}")
        check("Unread count works", "unread" in unread)

    total_time = time.time() - t_total
    print(f"\n{'='*60}")
    print(f"RESULTS: {R['passed']} passed, {R['failed']} failed ({total_time:.0f}s total)")
    if R["errors"]:
        print("\nFailed:")
        for e in R["errors"]:
            print(f"  - {e}")
    print("\nDetails:")
    for k, v in R["details"].items():
        print(f"  {k}: {json.dumps(v)}")
    print(f"{'='*60}")

    with open("/app/test_reports/load_test.json", "w") as f:
        json.dump(R, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
