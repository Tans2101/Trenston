"""Paddle webhook IP allowlist — list comes from api.paddle.com/ips."""
from paddle_ips import ip_allowed, reset_cache_for_tests


def test_ip_allowed_matches_cidr():
    reset_cache_for_tests()
    nets_raw = ["34.237.3.244/32", "34.195.105.136/32"]
    import ipaddress
    nets = [ipaddress.ip_network(c) for c in nets_raw]
    assert ip_allowed("34.237.3.244", nets) is True
    assert ip_allowed("1.2.3.4", nets) is False
    assert ip_allowed("not-an-ip", nets) is False
    assert ip_allowed("34.237.3.244", []) is False
