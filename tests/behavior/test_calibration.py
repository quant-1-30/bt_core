#! /usr/bin/env python3
"""finance.calibration → slip_perc """

import polars as pl

from bt_core.execution.core.finance.calibration import (
    best_candidate_multiplier,
    calibrate,
    calibrate_slip,
    sweep_candidate_multiplier,
)


def _fills(buy_prices, sell_prices, base=100.0):
    """构造 (actual, backtest) 两个成交集; 回测按 base 无滑点成交。"""
    rows_a = []
    rows_b = []
    for i, p in enumerate(buy_prices):
        rows_a.append({"sid": f"{i:06d}", "isbuy": True, "day": 20261120, "price": p})
        rows_b.append({"sid": f"{i:06d}", "isbuy": True, "day": 20261120, "price": base})
    for i, p in enumerate(sell_prices):
        rows_a.append({"sid": f"9{i:05d}", "isbuy": False, "day": 20261121, "price": p})
        rows_b.append({"sid": f"9{i:05d}", "isbuy": False, "day": 20261121, "price": base})
    return pl.DataFrame(rows_a), pl.DataFrame(rows_b)


def test_calibrate_slip_buy_and_sell_adverse():
    # 买: 实际价 101 (回测 100) -> +1%; 卖: 实际价 99 (回测 100) -> +1% 逆向滑点
    actual, backtest = _fills(buy_prices=[101.0], sell_prices=[99.0])
    assert abs(calibrate_slip(actual, backtest) - 0.01) < 1e-9


def test_calibrate_slip_empty_join_returns_zero():
    actual = pl.DataFrame({"sid": ["a"], "isbuy": [True], "day": [20261120], "price": [101.0]})
    backtest = pl.DataFrame({"sid": ["b"], "isbuy": [True], "day": [20261120], "price": [100.0]})
    assert calibrate_slip(actual, backtest) == 0.0


def test_calibrate_returns_dict():
    actual, backtest = _fills(buy_prices=[102.0], sell_prices=[98.0])
    out = calibrate(actual, backtest)
    assert abs(out["slip_perc"] - 0.02) < 1e-9


def test_sweep_candidate_multiplier_payoff_table():
    perf = {1.0: {"return": 0.10, "drawdown": 0.05},
            1.5: {"return": 0.15, "drawdown": 0.06},
            2.0: {"return": 0.16, "drawdown": 0.10}}
    df = sweep_candidate_multiplier(lambda k: perf[k], (1.0, 1.5, 2.0))
    assert df["candidate_multiplier"].to_list() == [1.0, 1.5, 2.0]
    # return_over_dd = return / drawdown
    assert abs(df.filter(pl.col("candidate_multiplier") == 1.5)["return_over_dd"][0] - 0.15 / 0.06) < 1e-12
    # 1.5 的 payoff (2.5) 最高
    assert best_candidate_multiplier(lambda k: perf[k], (1.0, 1.5, 2.0)) == 1.5
