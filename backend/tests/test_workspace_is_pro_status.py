"""workspace_is_pro must align with workspace_allows for past_due/paused."""
import os
from unittest.mock import patch

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_workspace_is_pro")

import server


def test_workspace_is_pro_false_when_past_due():
    with patch.object(server, "BILLING_ENFORCED", True):
        assert server.workspace_is_pro({"plan": "growth", "subscription_status": "active"}) is True
        assert server.workspace_is_pro({"plan": "growth", "subscription_status": "past_due"}) is False
        assert server.workspace_is_pro({"plan": "starter", "billing_status": "paused"}) is False
        assert server.workspace_is_pro({"plan": "free", "subscription_status": "active"}) is False
