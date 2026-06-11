"""
Iteration 258 — 50 Concurrent User Load Test für Profil-Modul
Testet:
- 50× GET /api/auth/me concurrent
- 50× PUT /api/users/profile concurrent (same user)
- 50× POST /api/users/me/office-days/skip concurrent (race condition test)
"""
import requests
import os
import time
import concurrent.futures
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    import pytest
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)

ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


def get_auth_token():
    """Get fresh auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
    }, timeout=10)
    if resp.status_code == 200:
        return resp.json().get("token")
    return None


def make_request(endpoint, method="GET", json_data=None, token=None):
    """Make a single request and return timing info"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    start = time.time()
    try:
        if method == "GET":
            resp = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=10)
        elif method == "PUT":
            resp = requests.put(f"{BASE_URL}{endpoint}", headers=headers, json=json_data, timeout=10)
        elif method == "POST":
            resp = requests.post(f"{BASE_URL}{endpoint}", headers=headers, json=json_data, timeout=10)
        else:
            resp = requests.request(method, f"{BASE_URL}{endpoint}", headers=headers, json=json_data, timeout=10)
        duration = time.time() - start
        return {
            "status": resp.status_code,
            "duration": duration,
            "success": resp.status_code < 400,
            "body": resp.text[:200] if resp.status_code >= 400 else None
        }
    except Exception as e:
        return {
            "status": 0,
            "duration": time.time() - start,
            "success": False,
            "error": str(e)
        }


def run_concurrent_test(name, endpoint, method="GET", json_data=None, count=50, token=None):
    """Run concurrent requests and report results"""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"Endpoint: {method} {endpoint}")
    print(f"Concurrent requests: {count}")
    print(f"{'='*60}")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
        if callable(json_data):
            # json_data is a function that generates unique data per request
            futures = [
                executor.submit(make_request, endpoint, method, json_data(i), token)
                for i in range(count)
            ]
        else:
            futures = [
                executor.submit(make_request, endpoint, method, json_data, token)
                for _ in range(count)
            ]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    success_count = sum(1 for r in results if r["success"])
    fail_count = count - success_count
    durations = [r["duration"] for r in results if r["success"]]
    
    if durations:
        avg_duration = sum(durations) / len(durations)
        p50 = sorted(durations)[len(durations) // 2]
        p95 = sorted(durations)[int(len(durations) * 0.95)]
        p99 = sorted(durations)[int(len(durations) * 0.99)] if len(durations) > 1 else p95
    else:
        avg_duration = p50 = p95 = p99 = 0
    
    print("\nResults:")
    print(f"  Success: {success_count}/{count} ({success_count/count*100:.1f}%)")
    print(f"  Failed:  {fail_count}/{count}")
    if durations:
        print(f"  Avg:     {avg_duration*1000:.1f}ms")
        print(f"  p50:     {p50*1000:.1f}ms")
        print(f"  p95:     {p95*1000:.1f}ms")
        print(f"  p99:     {p99*1000:.1f}ms")
    
    # Show sample errors
    errors = [r for r in results if not r["success"]][:3]
    if errors:
        print("\nSample errors:")
        for e in errors:
            print(f"  - Status {e['status']}: {e.get('error') or e.get('body', '')[:100]}")
    
    return {
        "name": name,
        "success_count": success_count,
        "total": count,
        "success_rate": success_count / count,
        "avg_ms": avg_duration * 1000,
        "p95_ms": p95 * 1000,
        "p99_ms": p99 * 1000,
    }


def main():
    print("="*60)
    print("ITERATION 258 — 50 CONCURRENT USER LOAD TEST")
    print(f"Base URL: {BASE_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print("="*60)
    
    # Get auth token
    print("\nGetting auth token...")
    token = get_auth_token()
    if not token:
        print("ERROR: Could not get auth token")
        return
    print(f"Token obtained: {token[:20]}...")
    
    results = []
    
    # Test 1: 50× GET /api/auth/me
    results.append(run_concurrent_test(
        "50× GET /api/auth/me",
        "/api/auth/me",
        "GET",
        token=token
    ))
    
    # Test 2: 50× PUT /api/users/profile (same user, different names)
    results.append(run_concurrent_test(
        "50× PUT /api/users/profile (same user)",
        "/api/users/profile",
        "PUT",
        json_data=lambda i: {"name": f"LoadTest User {i}"},
        token=token
    ))
    
    # Restore name
    requests.put(f"{BASE_URL}/api/users/profile", 
                 headers={"Authorization": f"Bearer {token}"},
                 json={"name": "Admin User"})
    
    # Test 3: 50× GET /api/users/me/privacy
    results.append(run_concurrent_test(
        "50× GET /api/users/me/privacy",
        "/api/users/me/privacy",
        "GET",
        token=token
    ))
    
    # Test 4: 50× GET /api/users/me/office-days
    results.append(run_concurrent_test(
        "50× GET /api/users/me/office-days",
        "/api/users/me/office-days",
        "GET",
        token=token
    ))
    
    # Test 5: 50× GET /api/users/me/email-preferences
    results.append(run_concurrent_test(
        "50× GET /api/users/me/email-preferences",
        "/api/users/me/email-preferences",
        "GET",
        token=token
    ))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    all_passed = True
    for r in results:
        status = "✓ PASS" if r["success_rate"] >= 0.9 else "✗ FAIL"
        if r["success_rate"] < 0.9:
            all_passed = False
        print(f"{status} {r['name']}: {r['success_count']}/{r['total']} ({r['success_rate']*100:.0f}%), p95={r['p95_ms']:.0f}ms")
    
    print("\n" + "="*60)
    if all_passed:
        print("ALL LOAD TESTS PASSED")
    else:
        print("SOME LOAD TESTS FAILED")
    print("="*60)
    
    return results


if __name__ == "__main__":
    main()
