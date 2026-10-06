"""GET /tasks/me includes legacy sample rows without assignee_user_id."""
import os
import sys
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_tasks_me_legacy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def test_task_is_mine_by_user_id():
    p = {"user_id": "u1", "name": "Ada"}
    assert server._task_is_mine({"assignee_user_id": "u1"}, p) is True
    assert server._task_is_mine({"assignee_user_id": "u2"}, p) is False


def test_task_is_mine_legacy_you_label():
    p = {"user_id": "owner_1", "name": "Kalun"}
    assert server._task_is_mine({"assignee": "You"}, p) is True
    assert server._task_is_mine({"assignee": "me"}, p) is True
    assert server._task_is_mine({"assignee": "Kalun"}, p) is True
    assert server._task_is_mine({"assignee": "Devin"}, p) is False
    # Explicit other assignee wins over label
    assert server._task_is_mine({"assignee": "You", "assignee_user_id": "other"}, p) is False
