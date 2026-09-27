"""Tests for helm_config URL helpers."""
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import helm_config  # noqa: E402

_CANONICAL_ENV_KEYS = ("TRENSTON_CANONICAL_ORIGIN", "HELM_CANONICAL_ORIGIN")


def _reload_helm_config_with_env(**overrides):
    """Reload helm_config after applying env overrides; restore prior env afterward."""
    saved = {k: os.environ.get(k) for k in _CANONICAL_ENV_KEYS}
    try:
        for k in _CANONICAL_ENV_KEYS:
            if k in overrides:
                val = overrides[k]
                if val is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = val
            else:
                os.environ.pop(k, None)
        importlib.reload(helm_config)
        yield helm_config
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(helm_config)


def test_registrable_cookie_domain_strips_www():
    assert helm_config.registrable_cookie_domain("www.trenston.com") == "trenston.com"


def test_registrable_cookie_domain_apex():
    assert helm_config.registrable_cookie_domain("trenston.com") == "trenston.com"


def test_public_api_origin_defaults_to_canonical():
    assert helm_config.public_api_origin().startswith("https://www.trenston.com")


def test_oauth_google_callback_uri_default():
    """Default public origin + /api/oauth/google/callback — matches FastAPI route."""
    for mod in _reload_helm_config_with_env():
        uri = f"{mod.public_api_origin()}/api/oauth/google/callback"
        assert uri == "https://www.trenston.com/api/oauth/google/callback"


def test_trenston_canonical_origin_wins_over_helm():
    """TRENSTON_CANONICAL_ORIGIN takes precedence when both rename-era vars are set."""
    for mod in _reload_helm_config_with_env(
        TRENSTON_CANONICAL_ORIGIN="https://www.trenston.com",
        HELM_CANONICAL_ORIGIN="https://www.helmcontrol.online",
    ):
        assert mod.public_api_origin() == "https://www.trenston.com"
        assert mod.TRENSTON_CANONICAL_ORIGIN == "https://www.trenston.com"


def test_is_stale_deploy_url():
    assert helm_config.is_stale_deploy_url("https://helm-company-cockpit.onrender.com")
    assert helm_config.is_stale_deploy_url("https://foo.vercel.app")
    assert not helm_config.is_stale_deploy_url("https://www.trenston.com")
