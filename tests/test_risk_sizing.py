from risk_sizing import RiskSizingInput, calculate_position_size, confidence_to_multiplier, fractional_kelly


def test_confidence_multiplier_score_bands():
    assert confidence_to_multiplier(65) == 0.0
    assert confidence_to_multiplier(75) == 0.25
    assert confidence_to_multiplier(85) == 0.50
    assert confidence_to_multiplier(92) == 0.75
    assert confidence_to_multiplier(98) == 1.0


def test_high_confidence_trade_gets_contract_size():
    result = calculate_position_size(
        RiskSizingInput(
            account_equity=100_000,
            signal_confidence=95,
            entry_price=2.00,
            stop_price=1.50,
            atr=0.20,
            win_probability=0.62,
            payoff_ratio=1.3,
            liquidity_score=0.90,
        )
    )
    assert result.decision in {"ALLOW", "REDUCE"}
    assert result.contracts > 0
    assert result.dollars_at_risk <= 1_000


def test_three_losses_blocks_trade():
    result = calculate_position_size(
        RiskSizingInput(
            account_equity=100_000,
            signal_confidence=99,
            entry_price=2.00,
            stop_price=1.50,
            consecutive_losses=3,
        )
    )
    assert result.decision == "BLOCK"
    assert result.contracts == 0
    assert any("consecutive losses" in reason for reason in result.reasons)


def test_fractional_kelly_is_capped_and_non_negative():
    assert fractional_kelly(0.40, 1.0) == 0.0
    assert 0.0 < fractional_kelly(0.65, 1.5) <= 0.25
