"""
Iter 318 — Smoke test for the resources/admin package split.

Verifies that the 1477-line monolith was successfully split into a
package without losing any endpoints. Each sub-module's representative
endpoint is hit once via the live backend.

Run: `cd /app/backend && pytest tests/test_iter318_admin_split.py -v`
"""
import requests


def _auth(base_url: str, token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_admin_package_loads_cleanly():
    """Module-level import sanity — proves the package structure is valid
    Python without needing the live backend."""
    from routes.resources.admin import router
    from routes.resources.admin import crud, floorplans, master_data, analytics, demo_seed
    # All sub-routers should be wired into the master router
    assert router is not None
    assert len(router.routes) >= 40, f"Expected ≥40 routes, got {len(router.routes)}"
    # Each module contributes its own router
    for mod in (crud, floorplans, master_data, analytics, demo_seed):
        assert hasattr(mod, "router"), f"{mod.__name__} missing `router` export"


def test_crud_module_endpoints(base_url: str, admin_token: str):
    """crud.py: list_resources + favorites."""
    r = requests.get(f"{base_url}/api/resources",
                     headers=_auth(base_url, admin_token), timeout=10, verify=False)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    r = requests.get(f"{base_url}/api/favorites/desks",
                     headers=_auth(base_url, admin_token), timeout=10, verify=False)
    assert r.status_code == 200
    assert "desk_ids" in r.json()


def test_floorplans_module_endpoints(base_url: str, admin_token: str):
    """floorplans.py: list_floorplans + items."""
    r = requests.get(f"{base_url}/api/floorplans",
                     headers=_auth(base_url, admin_token), timeout=10, verify=False)
    assert r.status_code == 200


def test_master_data_module_endpoints(base_url: str, admin_token: str):
    """master_data.py: cost-centers + accounts."""
    r = requests.get(f"{base_url}/api/cost-centers",
                     headers=_auth(base_url, admin_token), timeout=10, verify=False)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    r = requests.get(f"{base_url}/api/accounts",
                     headers=_auth(base_url, admin_token), timeout=10, verify=False)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_analytics_module_endpoints(base_url: str, admin_token: str):
    """analytics.py: dashboard overview + snapshot + no-show + in-office."""
    for path in (
        "/api/resources/dashboard/overview",
        "/api/resource-availability-snapshot",
        "/api/resources/dashboard/no-show",
        "/api/resources-in-office",
        "/api/resource-upload-config",
    ):
        r = requests.get(f"{base_url}{path}",
                         headers=_auth(base_url, admin_token), timeout=10, verify=False)
        assert r.status_code == 200, f"{path} returned {r.status_code}"


def test_auth_enforcement_on_modified_endpoints(base_url: str):
    """No bearer token → 401 on all the F841-touched endpoints (regression
    guard for the Iter 318 lint cleanup that removed `user = await
    get_current_user(request)` but had to keep the auth side-effect)."""
    for path in (
        "/api/resources",
        "/api/cost-centers",
        "/api/accounts",
        "/api/floorplans",
        "/api/resources/dashboard/overview",
    ):
        r = requests.get(f"{base_url}{path}", timeout=10, verify=False)
        assert r.status_code == 401, f"{path} should require auth, got {r.status_code}"


def test_deprecated_driver_license_returns_410(base_url: str, admin_token: str):
    """The deprecated singular endpoint must respond 410 Gone, not 404."""
    r = requests.get(f"{base_url}/api/users/anyone/driver-license",
                     headers=_auth(base_url, admin_token), timeout=10, verify=False)
    assert r.status_code == 410
