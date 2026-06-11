"""Iter 253 Phase 3 — Survey PDF async pipeline regression test.

Tests the full enqueue -> worker -> result -> download flow for survey PDFs.
"""
import asyncio
import httpx
import pytest

API = "http://localhost:8001/api"
ADMIN = {"email": "admin@meetflow.com", "password": "admin123"}


@pytest.mark.asyncio
async def test_survey_pdf_async_pipeline():
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{API}/auth/login", json=ADMIN)
        H = {"Authorization": f"Bearer {r.json()['token']}"}

        # Create a survey
        r = await c.post(f"{API}/surveys", headers=H, json={
            "title": "pdf-async-test",
            "description": "test",
            "questions": [{"question_id": "q1", "type": "single_choice",
                            "text": "?", "options": ["a", "b"], "required": True}],
            "target_all": True,
        })
        assert r.status_code in (200, 201), r.text
        survey_id = r.json()["survey_id"]

        try:
            # Enqueue
            r = await c.post(f"{API}/exports/surveys/{survey_id}/pdf/async", headers=H)
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["status"] == "queued"
            job_id = data["job_id"]
            assert job_id and job_id != "inline"

            # Poll for completion (up to 15s)
            for _ in range(30):
                await asyncio.sleep(0.5)
                r = await c.get(f"{API}/jobs/{job_id}", headers=H)
                assert r.status_code == 200, r.text
                status_payload = r.json()
                if status_payload.get("status") == "complete":
                    break
            assert status_payload["status"] == "complete", f"final: {status_payload}"
            assert status_payload["result"]["binary"] is True
            assert status_payload["result"]["size"] > 1000

            # Download
            r = await c.get(f"{API}/exports/surveys/jobs/{job_id}/pdf", headers=H)
            assert r.status_code == 200, r.text
            assert r.headers["content-type"] == "application/pdf"
            assert r.content[:8] == b"%PDF-1.4", f"not a PDF: {r.content[:8]!r}"
        finally:
            await c.delete(f"{API}/surveys/{survey_id}", headers=H)
