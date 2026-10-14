import os

os.environ.setdefault("DB_NAME", "test_helm_event_instants")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import server


def test_manila_wall_time_becomes_true_utc():
    ev = {"date": "2026-10-15", "time": "11:00", "duration": 30,
          "start_at": "2026-10-15T11:00:00+00:00", "end_at": "2026-10-15T11:30:00+00:00"}
    start, end = server._helm_event_instants(ev, {"timezone": "Asia/Manila"})
    assert start.startswith("2026-10-15T03:00:00")
    assert end.startswith("2026-10-15T03:30:00")


def test_all_day_events_are_left_alone():
    ev = {"date": "2026-10-15", "time": "", "all_day": True, "start_at": "a", "end_at": "b"}
    assert server._helm_event_instants(ev, {"timezone": "Asia/Manila"}) == ("a", "b")
