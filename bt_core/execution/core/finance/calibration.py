#! /usr/bin/env python3

from __future__ import annotations

import polars as pl


def calibrate_slip(actual: pl.DataFrame, backtest: pl.DataFrame) -> float:
    """
    Parameters
    ----------
    actual:
        ``sid, isbuy(bool), day, price``
    backtest:
        same schema

    Returns
    -------
    median PseudoFiller.slip_perc
    """
    j = actual.join(backtest, on=["sid", "isbuy", "day"], suffix="_bt")
    if j.height == 0:
        return 0.0
    rel = (j["price"] - j["price_bt"]) / j["price_bt"]
    # 买: 实际价 >= 回测价 => 正滑点; 卖: 实际价 <= 回测价 => 取负后为正
    adverse = j.with_columns(
        pl.when(pl.col("isbuy")).then(rel).otherwise(-rel).alias("_adverse")
    )["_adverse"]
    return float(adverse.median())


def calibrate(actual: pl.DataFrame, backtest: pl.DataFrame) -> dict:
    return {"slip_perc": calibrate_slip(actual, backtest)}


def sweep_candidate_multiplier(evaluate, multipliers=(1.0, 1.5, 2.0)) -> pl.DataFrame:
    """
    Parameters
    ----------
    evaluate:
        ``evaluate(k: float) -> dict`` 
        ``{"return": ..., "drawdown": ...}``
    multipliers:
        float k * max_positions

    Returns
    -------
    ``{candidate_multiplier, return, drawdown, return_over_dd}`` 表格,
    ``return_over_dd = return / drawdown``
    """
    rows = []
    for k in multipliers:
        m = evaluate(float(k))
        ret = float(m.get("return", 0.0))
        dd = float(m.get("drawdown", 0.0))
        rows.append({
            "candidate_multiplier": float(k),
            "return": ret,
            "drawdown": dd,
            "return_over_dd": (ret / dd) if dd > 0 else float("nan"),
        })
    return pl.DataFrame(rows)


def best_candidate_multiplier(evaluate, multipliers=(1.0, 1.5, 2.0)) -> float:
    """ return_over_dd ---> payoff """
    df = sweep_candidate_multiplier(evaluate, multipliers)
    best = df.sort("return_over_dd", descending=True, nulls_last=True)
    return float(best["candidate_multiplier"][0]) if best.height > 0 else float(multipliers[0])
