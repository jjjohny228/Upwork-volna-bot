from upwork_bot.estimator import estimate_budget


def test_months_use_21_working_days_at_8h():
    result = estimate_budget(35, months=3)
    assert result["total_hours"] == 504.0  # 3 * 21 * 8
    assert result["total_usd"] == 17640.0
    assert result["hourly_rate"] == 35


def test_mixed_duration_sums_units():
    result = estimate_budget(50, weeks=2, days=1, hours=4)
    # 2*40 + 1*8 + 4 = 92
    assert result["total_hours"] == 92.0
    assert result["total_usd"] == 4600.0


def test_zero_duration():
    result = estimate_budget(40)
    assert result["total_hours"] == 0.0
    assert result["total_usd"] == 0.0
