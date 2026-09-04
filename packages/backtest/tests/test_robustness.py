import numpy as np

from backtest.robustness import (
    compute_dsr,
    compute_expected_max_sharpe,
    compute_monte_carlo_p_value,
    evaluate_strategy_robustness,
)


def test_expected_max_sharpe_monotonicity():
    # 0 or 1 trial should have 0 expected max under null
    assert compute_expected_max_sharpe(1) == 0.0
    assert compute_expected_max_sharpe(0) == 0.0

    # More trials should strictly increase the hurdle
    hurdle_5 = compute_expected_max_sharpe(5)
    hurdle_20 = compute_expected_max_sharpe(20)
    hurdle_100 = compute_expected_max_sharpe(100)

    assert hurdle_5 > 0.0
    assert hurdle_20 > hurdle_5
    assert hurdle_100 > hurdle_20


def test_dsr_penalizes_multiple_trials():
    np.random.seed(42)
    # Generate returns with positive mean (modest edge)
    returns = np.random.normal(loc=0.001, scale=0.02, size=500)
    observed_sharpe = 1.8

    # 1 trial should have higher DSR than 20 trials
    dsr_1, _, _ = compute_dsr(returns, observed_sharpe, trials_count=1)
    dsr_10, _, _ = compute_dsr(returns, observed_sharpe, trials_count=10)
    dsr_50, _, _ = compute_dsr(returns, observed_sharpe, trials_count=50)

    assert dsr_1 > dsr_10 > dsr_50
    assert 0.0 <= dsr_50 <= 1.0


def test_dsr_identifies_strong_negative_skewness():
    np.random.seed(42)
    # Crash risk: small steady gains with occasional massive drops
    normal_gains = np.full(490, 0.002)
    crashes = np.full(10, -0.08)
    returns = np.concatenate([normal_gains, crashes])

    observed_sharpe = 1.5
    dsr, skew, kurt = compute_dsr(returns, observed_sharpe, trials_count=1)

    assert skew < -1.0  # Strong negative skewness detected
    assert kurt > 3.0   # Fat tails


def test_monte_carlo_p_value():
    np.random.seed(42)
    # Truly positive trend
    returns = np.random.normal(loc=0.005, scale=0.01, size=200)
    p_val_good = compute_monte_carlo_p_value(returns, observed_sharpe=2.5, num_simulations=100)
    assert p_val_good < 0.10

    # Pure noise with zero edge should fail to achieve significance (p > 0.05)
    noise = np.random.normal(loc=0.0, scale=0.02, size=200)
    p_val_noise = compute_monte_carlo_p_value(noise, observed_sharpe=0.1, num_simulations=100)
    assert p_val_noise > 0.05


def test_evaluate_strategy_robustness():
    np.random.seed(42)
    returns = np.random.normal(loc=0.002, scale=0.01, size=300)
    res = evaluate_strategy_robustness(
        returns=returns,
        observed_sharpe=2.0,
        max_drawdown=0.12,
        num_trades=25,
        trials_count=2,
    )

    assert res.observed_sharpe == 2.0
    assert res.num_trades == 25
    assert res.deflated_sharpe_ratio > 0.5
    assert res.robustness_score > 0.0
    d = res.to_dict()
    assert "deflated_sharpe_ratio" in d
    assert "robustness_score" in d
