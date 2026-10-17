"""Iteration 3: Onboarding + entry-driven Financials + flow-through into Telemetry/Briefing.

Runs against the public REACT_APP_BACKEND_URL. Uses three pre-seeded sessions:
  OWNER:  test_session_kalun_123 (has sample data applied)
  MEMBER: test_session_user2 (member of owner's workspace)
  FRESH:  test_session_new (empty, onboarding_done=false)

Integration: requires a seeded preview backend + live Mongo.
Set RUN_INTEGRATION=1 to run.
"""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION") != "1",
        reason="integration: seeded preview + live Mongo; set RUN_INTEGRATION=1",
    ),
]

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://exec-cockpit.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

OWNER = "test_session_kalun_123"
MEMBER = "test_session_user2"
FRESH = "test_session_new"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


def H(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session", autouse=True)
def ensure_fresh_user():
    """Reset the FRESH user + session so onboarding is empty at start-of-suite."""
    if os.environ.get("RUN_INTEGRATION") != "1":
        yield
        return
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    db.users.update_one(
        {"user_id": "test-user-new"},
        {"$set": {"user_id": "test-user-new", "email": "newceo@example.com",
                  "name": "Fresh CEO", "created_at": now.isoformat()}},
        upsert=True,
    )
    db.user_sessions.update_one(
        {"session_token": "test_session_new"},
        {"$set": {"user_id": "test-user-new", "session_token": "test_session_new",
                  "expires_at": (now + timedelta(days=7)).isoformat(),
                  "created_at": now.isoformat()}},
        upsert=True,
    )
    # Delete previous membership/workspace for this fresh user
    mems = list(db.memberships.find({"user_id": "test-user-new"}))
    ws_ids = [m["workspace_id"] for m in mems]
    if ws_ids:
        db.workspaces.delete_many({"workspace_id": {"$in": ws_ids}})
        db.financial_entries.delete_many({"workspace_id": {"$in": ws_ids}})
        db.memberships.delete_many({"user_id": "test-user-new"})
    db.users.update_one({"user_id": "test-user-new"}, {"$unset": {"active_workspace_id": ""}})
    # New behavior (iteration 5): no silent auto-workspace. A fresh owner explicitly
    # creates an empty company. Do that here so the onboarding-empty tests have a company.
    requests.post(f"{API}/workspaces", headers=H("test_session_new"), json={"name": "Fresh CEO's Company"})
    yield
    client.close()


# ------------------------- Onboarding: empty state -------------------------
class TestOnboardingEmpty:
    def test_fresh_user_company_is_empty(self):
        r = requests.get(f"{API}/company", headers=H(FRESH))
        assert r.status_code == 200
        d = r.json()
        assert d["onboarding_done"] is False
        assert d.get("company_setup_done") is False
        assert d["template"] == "empty"
        assert d["role"] == "owner"

    def test_fresh_user_financials_empty(self):
        r = requests.get(f"{API}/financials", headers=H(FRESH))
        assert r.status_code == 200
        d = r.json()
        assert d["has_data"] is False
        assert d["mrr"] == "$0"
        assert d["runway_months"] is None
        assert d["entries"] == []
        assert d["can_write"] is True  # owner has finance:write

    def test_fresh_user_other_modules_empty(self):
        for path in ["/decisions", "/tasks", "/telemetry"]:
            r = requests.get(f"{API}{path}", headers=H(FRESH))
            assert r.status_code == 200, f"{path} -> {r.status_code}"


# ------------------------- Apply template: clean & sample -------------------------
class TestApplyTemplate:
    def test_apply_clean_sets_onboarding_done(self):
        # Uses FRESH user
        r = requests.post(f"{API}/workspace/apply-template", headers=H(FRESH), json={"template": "clean"})
        assert r.status_code == 200
        c = requests.get(f"{API}/company", headers=H(FRESH)).json()
        assert c["onboarding_done"] is True
        # Data remains empty
        fin = requests.get(f"{API}/financials", headers=H(FRESH)).json()
        assert fin["has_data"] is False
        assert fin["entries"] == []

    def test_apply_template_member_forbidden(self):
        r = requests.post(f"{API}/workspace/apply-template", headers=H(MEMBER), json={"template": "sample"})
        assert r.status_code == 403

    def test_owner_sample_already_applied(self):
        """Owner (kalun) already has sample applied per test_credentials note."""
        fin = requests.get(f"{API}/financials", headers=H(OWNER)).json()
        assert fin["has_data"] is True
        # mrr ~$248K, runway 15-16mo, burn ~$182K, cash $3.10M
        assert "$248K" in fin["mrr"] or "$247K" in fin["mrr"] or "$249K" in fin["mrr"]
        assert 14.5 <= fin["runway_months"] <= 17
        assert "$182K" in fin["burn"] or "$181K" in fin["burn"] or "$183K" in fin["burn"]
        assert "$3.10M" in fin["cash"] or "$3.1" in fin["cash"]
        assert len(fin["entries"]) >= 30


# ------------------------- Financial Entry CRUD (owner + member) -------------------------
@pytest.mark.parametrize("token,label", [(OWNER, "owner"), (MEMBER, "member")])
class TestFinEntryCRUD:
    def test_create_edit_delete_entry(self, token, label):
        payload = {"type": "revenue", "category": f"TEST_{label}_cat",
                   "name": f"TEST {label} item",
                   "amount": 1234.56, "month": "2025-10", "recurring": False,
                   "note": f"TEST entry {label}"}
        r = requests.post(f"{API}/financials/entries", headers=H(token), json=payload)
        if label == "member":
            # member pack is read-only for finance:write (Phase 0 access packs)
            assert r.status_code == 403, r.text
            return
        assert r.status_code == 200, r.text
        entry = r.json()["entry"]
        assert entry["type"] == "revenue"
        assert entry["amount"] == 1234.56
        assert entry["category"] == f"TEST_{label}_cat"
        assert entry["name"] == f"TEST {label} item"
        assert entry["month"] == "2025-10"
        eid = entry["id"]

        # Verify via GET
        listing = requests.get(f"{API}/financials", headers=H(token)).json()["entries"]
        assert any(e["id"] == eid for e in listing)

        # PATCH
        p2 = dict(payload)
        p2["amount"] = 999.0
        p2["note"] = "TEST updated"
        r2 = requests.patch(f"{API}/financials/entries/{eid}", headers=H(token), json=p2)
        assert r2.status_code == 200
        listing2 = requests.get(f"{API}/financials", headers=H(token)).json()["entries"]
        got = [e for e in listing2 if e["id"] == eid][0]
        assert got["amount"] == 999.0
        assert got["note"] == "TEST updated"

        # DELETE
        r3 = requests.delete(f"{API}/financials/entries/{eid}", headers=H(token))
        assert r3.status_code == 200
        listing3 = requests.get(f"{API}/financials", headers=H(token)).json()["entries"]
        assert not any(e["id"] == eid for e in listing3)

    def test_invalid_type_400(self, token, label):
        r = requests.post(f"{API}/financials/entries", headers=H(token),
                          json={"type": "junk", "category": "c", "name": "x", "amount": 1, "month": "2025-10"})
        # member is denied before validation (403); owner reaches validation (400)
        assert r.status_code == (403 if label == "member" else 400)


# ------------------------- Computed flow-through -------------------------
class TestFinancialFlowThrough:
    """Add a recurring revenue entry for the latest month, verify MRR flows into
    /telemetry KPI and /briefing metrics."""

    def setup_method(self, method):
        # Snapshot baseline mrr for OWNER
        fin = requests.get(f"{API}/financials", headers=H(OWNER)).json()
        self._baseline_mrr = fin["mrr"]
        # Determine latest month from series
        latest_label = fin["revenue_series"][-1]["month"] if fin["revenue_series"] else "Oct"
        # find corresponding YYYY-MM by re-scanning entries
        # Use the most-recent entry's month
        entries = sorted(fin["entries"], key=lambda e: e["month"], reverse=True)
        self._latest_month = entries[0]["month"] if entries else "2025-10"
        self._injected_id = None

    def teardown_method(self, method):
        if self._injected_id:
            requests.delete(f"{API}/financials/entries/{self._injected_id}", headers=H(OWNER))

    def test_recurring_revenue_flows_into_telemetry_and_briefing(self):
        # inject an unmistakably large recurring revenue for the latest month
        payload = {"type": "revenue", "category": "TEST_flow_revenue",
                   "name": "TEST flow-through MRR",
                   "amount": 50000.0, "month": self._latest_month, "recurring": True,
                   "note": "TEST flow-through"}
        r = requests.post(f"{API}/financials/entries", headers=H(OWNER), json=payload)
        assert r.status_code == 200
        self._injected_id = r.json()["entry"]["id"]

        fin = requests.get(f"{API}/financials", headers=H(OWNER)).json()
        assert fin["has_data"] is True
        mrr_fin = fin["mrr"]

        # Telemetry MRR KPI should match financials.mrr
        tel = requests.get(f"{API}/telemetry", headers=H(OWNER)).json()
        mrr_kpi = [k for k in tel["kpis"] if k["label"] == "MRR"][0]
        assert mrr_kpi["value"] == mrr_fin, f"telemetry MRR {mrr_kpi['value']} != financials {mrr_fin}"
        assert len(tel["revenue_trend"]) > 0

        # Briefing metrics include MRR/Runway/Burn from same computation
        br = requests.get(f"{API}/briefing", headers=H(OWNER)).json()
        labels = [m["label"] for m in br["metrics"]]
        assert "MRR" in labels and "Runway" in labels and "Burn" in labels
        mrr_metric = [m for m in br["metrics"] if m["label"] == "MRR"][0]
        assert mrr_metric["value"] == mrr_fin


# ------------------------- Settings -------------------------
class TestFinSettings:
    def test_update_settings_recomputes_runway(self):
        # Get current cash
        before = requests.get(f"{API}/financials", headers=H(OWNER)).json()
        prev_cash = before["settings"]["cash"]
        prev_gm = before["settings"].get("gross_margin")

        # Set new cash / gm
        new_cash = 5_000_000.0
        r = requests.put(f"{API}/financials/settings", headers=H(OWNER),
                         json={"cash": new_cash, "gross_margin": 72})
        assert r.status_code == 200
        after = requests.get(f"{API}/financials", headers=H(OWNER)).json()
        assert after["settings"]["cash"] == new_cash
        assert after["settings"]["gross_margin"] == 72
        assert after["gross_margin"] in ("72%", "72.0%")
        # runway should now be higher than before (or at least not the same)
        assert after["runway_months"] != before["runway_months"] or before["runway_months"] is None

        # Restore
        requests.put(f"{API}/financials/settings", headers=H(OWNER),
                     json={"cash": prev_cash, "gross_margin": prev_gm})


# ------------------------- Stripe import removed -------------------------
@pytest.mark.skip(reason="Stripe financial import removed")
class TestStripeImport:
    def test_stripe_import_returns_400_not_500(self):
        r = requests.post(f"{API}/financials/import/stripe", headers=H(OWNER))
        # Either 400 (auth error / invalid key) or 200 if it magically works with 0 records
        assert r.status_code in (200, 400), f"unexpected {r.status_code}: {r.text}"
        if r.status_code == 400:
            body = r.json()
            assert "detail" in body


# ------------------------- Authorization matrix -------------------------
class TestFinancePermissions:
    def test_member_cannot_write_finance(self):
        # sanity: member GET works
        r = requests.get(f"{API}/financials", headers=H(MEMBER))
        assert r.status_code == 200
        # member pack is read-only for finance:write (Phase 0 access packs)
        assert r.json()["can_write"] is False
        # settings update denied
        r = requests.put(f"{API}/financials/settings", headers=H(MEMBER),
                        json={"cash": 3_100_000.0, "gross_margin": 68})
        assert r.status_code == 403

    def test_fresh_user_apply_sample_then_verify(self):
        """Owner (fresh) applies sample template, verifies data materialized."""
        # FRESH already ran apply-template clean earlier. Apply sample now.
        r = requests.post(f"{API}/workspace/apply-template", headers=H(FRESH),
                          json={"template": "sample"})
        assert r.status_code == 200
        c = requests.get(f"{API}/company", headers=H(FRESH)).json()
        assert c["onboarding_done"] is True
        fin = requests.get(f"{API}/financials", headers=H(FRESH)).json()
        assert fin["has_data"] is True
        assert len(fin["entries"]) >= 30
        # rough sample numbers
        assert "$248K" in fin["mrr"] or "$247K" in fin["mrr"] or "$249K" in fin["mrr"]
        assert 14.5 <= fin["runway_months"] <= 17
