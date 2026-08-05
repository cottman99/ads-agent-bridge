from ads_agent_bridge.compatibility import support_tier


def test_support_tiers() -> None:
    assert support_tier(2026, "1") == "stable"
    assert support_tier(2025, None) == "stable"
    assert support_tier(2024, "2") == "preview"
    assert support_tier(2024, "1") == "experimental"
    assert support_tier(2023, "2") == "experimental"
    assert support_tier(2023, "1") == "unsupported"
