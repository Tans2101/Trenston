import os

os.environ.setdefault("DB_NAME", "test_site_events")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import site_events


def test_unknown_events_are_dropped():
    assert site_events.clean_event("drop_tables", "/", {}) is None
    assert site_events.clean_event(None, "/", {}) is None


def test_only_allowed_props_survive_and_are_trimmed():
    row = site_events.clean_event(
        "cta_click", "/pricing?utm=x#top", {"where": "hero" * 30, "email": "a@b.com"},
    )
    assert row["path"] == "/pricing"
    assert set(row["props"]) == {"where"}
    assert len(row["props"]["where"]) == site_events.MAX_VALUE_LEN


def test_non_dict_props_are_ignored():
    row = site_events.clean_event("signup_view", "/sign-up", "oops")
    assert row == {"name": "signup_view", "path": "/sign-up", "props": {}}
