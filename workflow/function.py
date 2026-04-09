#! /usr/bin/env python3
# -*- encondig: utf-8 -*-

import os
import math
import numpy as np
import stumpy
import pyarrow as pa
import pyarrow.compute as pc
import polars as pl
from datetime import datetime
from typing import List, Any, Dict
from scipy.stats import chi2_contingency, ks_2samp, skew, genpareto

from bt_sdk.core.client import GetMdApi, FactorTopic
from bt_sdk.core.protocol import QueryBody
from backtest.execution.actor import AsyncRunner


def _initialize_mdapi():
    md_addr = os.getenv("MD_ADDR", "127.0.0.1:50051").split(":")
    mdapi = GetMdApi(addr=(md_addr[0], int(md_addr[1])))
    _runner = AsyncRunner()
    _runner.start() # new_event_loop
    _loop = _runner.get_loop()
    mdapi.start(_loop)
    return mdapi


def robust_z_normalize(window_data):
    """ mad z-norm replace (x - mean)/std """
    median_val = np.median(window_data)
    abs_dev = np.abs(window_data - median_val)
    
    mad = np.median(abs_dev)
    if mad == 0:
        mad = 1e-8
        
    robust_std = 1.4826 * mad
    robust_z = (window_data - median_val) / robust_std
    return robust_z


def extract_from_beta_with_freq(raw: pl.DataFrame, bench_ref: pa.Table, rolling_freq: int, ewm_span: int, signal_type: str = "vwap"):
    """
    :param signal_type: "close" , "vwap", "vpt"
    """
    span = int(ewm_span * 4 * np.floor(60 / rolling_freq))
    benchmark = pl.from_arrow(bench_ref)
    raw_df = raw if isinstance(raw, pl.DataFrame) else pl.from_arrow(raw)
 
    # ==========================================
    # 1. concat benchmark and eliminate 14:55
    # ==========================================
    data_joined = raw_df.join(
        benchmark.select(["tick", "close"]).rename({"close": "close_bench"}),
        on="tick",
        how="left" 
    ).sort("tick").with_columns(
        datetime = pl.from_epoch(pl.col("tick"), time_unit="s"),
        date_int = pl.from_epoch(pl.col("tick"), time_unit="s").dt.strftime("%Y%m%d").cast(pl.Int32)
    )

    data_joined = data_joined.filter(
        # pl.col("datetime").dt.time() <= datetime.time(14, 55, 0)
        pl.col("datetime").dt.hour() * 60 + pl.col("datetime").dt.minute() <= 14 * 60 + 55
    )

    # ==========================================
    # 2. vwap price / close / vpt price
    # ==========================================
    if signal_type == "vwap":
        data_joined = data_joined.with_columns(
            signal_price = pl.when(pl.col("volume") > 0)
                             .then(pl.col("amount") / pl.col("volume"))
                             .otherwise(pl.col("close"))
        )
    else:
        # Close / VPT 
        data_joined = data_joined.with_columns(
            signal_price = pl.col("close")
        )

    data_joined = data_joined.with_columns(
        log_ret_raw = pl.col("signal_price").log().diff().fill_null(0.0),
        log_ret_bench_raw = pl.col("close_bench").log().diff().fill_null(0.0)
    )

    # ==========================================
    # 3. calculate Beta 
    # ==========================================
    beta_df = data_joined.group_by_dynamic( 
        "datetime", 
        every=f"{rolling_freq}m",
        closed="left" 
    ).agg(
        close_freq = pl.col("signal_price").last(),
        close_bench_freq = pl.col("close_bench").last()
    ).sort("datetime").with_columns(
        ret_freq = pl.col("close_freq").log().diff().fill_null(0.0),
        ret_bench_freq = pl.col("close_bench_freq").log().diff().fill_null(0.0)
    ).with_columns(
        xy_ewm = (pl.col("ret_freq") * pl.col("ret_bench_freq")).ewm_mean(span=span, ignore_nulls=True),
        x_ewm  = pl.col("ret_freq").ewm_mean(span=span, ignore_nulls=True),
        y_ewm  = pl.col("ret_bench_freq").ewm_mean(span=span, ignore_nulls=True),
        y2_ewm = (pl.col("ret_bench_freq") ** 2).ewm_mean(span=span, ignore_nulls=True)
    ).with_columns(
        cov_xy = pl.col("xy_ewm") - (pl.col("x_ewm") * pl.col("y_ewm")),
        var_y  = pl.col("y2_ewm") - (pl.col("y_ewm") ** 2)
    ).with_columns(
        raw_beta = pl.when(pl.col("var_y") > 1e-8)
                     .then(pl.col("cov_xy") / pl.col("var_y"))
                     .otherwise(1.0)
    ).with_columns(
        beta_upper = pl.col("raw_beta").rolling_quantile(0.95, window_size=span, min_periods=5), 
        beta_lower = pl.col("raw_beta").rolling_quantile(0.05, window_size=span, min_periods=5)
    ).with_columns(
        beta = pl.min_horizontal(
                   pl.max_horizontal(pl.col("raw_beta"), pl.col("beta_lower").fill_null(-3.0)), 
                   pl.col("beta_upper").fill_null(3.0)
               )
    ).with_columns(
        filled_beta = pl.col("beta").shift(1).forward_fill().fill_null(1.0), 
        datetime_trunc = pl.col("datetime").dt.truncate(f"{rolling_freq}m")
    ).select(["datetime_trunc", "filled_beta"])  

    # ==========================================
    # 4. calculate residual_ret
    # ==========================================
    hf_df = data_joined.with_columns(
        datetime_trunc = pl.col("datetime").dt.truncate(f"{rolling_freq}m")
    ).join( 
        beta_df,
        on="datetime_trunc",
        how="left"
    ).with_columns(
        filled_beta = pl.col("filled_beta").forward_fill().fill_null(1.0)
    )

    hf_df = hf_df.sort("tick").with_columns( 
        residual_ret = pl.col("log_ret_raw") - pl.col("filled_beta") * pl.col("log_ret_bench_raw")
    )
    
    # ==========================================
    # 5. multiplier on vpt
    # ==========================================
    if signal_type == "vpt":
        hf_df = hf_df.with_columns(
            daily_mean_vol = pl.col("volume").mean().over("date_int")
        ).with_columns(
            vol_weight = pl.when(pl.col("daily_mean_vol") > 0)
                           .then(pl.col("volume") / pl.col("daily_mean_vol"))
                           .otherwise(1.0)
        ).with_columns(
            residual_ret = pl.col("residual_ret") * pl.col("vol_weight")
        )

    hf_df = hf_df.with_columns(
        # intraday_cum = pl.col("residual_ret").cum_sum().over("date_int"),
        intraday_cum = pl.col("residual_ret").cum_sum()
    )
    
    if "daily_mean_vol" in hf_df.columns:
        hf_df = hf_df.drop(["daily_mean_vol", "vol_weight"])
        
    return hf_df


def dsample_and_concat(hf_dfs: Dict[str, pl.DataFrame], downsample: int, m: int , amplify:int =1000):
    """
    fill m np.nan between assets
    """
    multi_asset =[]
    nan_buffer = np.full(m, np.nan)  
    
    for sid, hf_df in hf_dfs.items():
        hf_df_1455 = hf_df.filter(
            # pl.col("datetime").dt.time() <= datetime.time(14, 55, 0)
            pl.col("datetime").dt.hour() * 60 + pl.col("datetime").dt.minute() <= 14 * 60 + 55
        )
        
        df_sampled = hf_df_1455.with_columns(
            intraday_cum_bps = pl.col("intraday_cum") * amplify
        ).group_by_dynamic(
            "datetime", every=f"{downsample}m", closed="right", label="right"
        ).agg(
            cum_val = pl.col("intraday_cum_bps").last()
        ).drop_nulls(subset=["cum_val"])
        
        cum_vals = df_sampled["cum_val"].to_numpy()
        
        if len(cum_vals) > 0:
            multi_asset.append(cum_vals)
            multi_asset.append(nan_buffer) 
            
    if not multi_asset:
        return np.array([])
        
    return np.concatenate(multi_asset)


def extract_asset_feature(hf_df: pl.DataFrame, downsample: int, m: int, amplify: int = 1000):
    """
        1. strict with 14:55 to eliminate future
        2. revise daily_ret from T-1 14:55 to T 14:55
        3. filter suspend and price limit
    """
    
    # ==========================================
    # 1. eliminate data after 14:55:00
    # ==========================================
    hf_df_1455 = hf_df.filter(
        # pl.col("datetime").dt.time() <= datetime.time(14, 55, 0)
        pl.col("datetime").dt.hour() * 60 + pl.col("datetime").dt.minute() <= 14 * 60 + 55
    )
    
    # ==========================================
    # 2. cross ret 14:55 -> 14:55
    # ==========================================
    daily_price_1455 = hf_df_1455.with_columns(
        date_int_tmp = pl.col("datetime").dt.strftime("%Y%m%d").cast(pl.Int32)
    ).group_by("date_int_tmp").agg(
        close_1455 = pl.col("close").last() 
    ).sort("date_int_tmp")
    
    daily_ret_df = daily_price_1455.with_columns(
        daily_ret = pl.col("close_1455").log().diff().fill_null(0.0) # T-1 14:55: T 14:55 pnl 
    )
    ret_dict = dict(zip(daily_ret_df["date_int_tmp"].to_list(), daily_ret_df["daily_ret"].to_list()))
    
    # ==========================================
    # 3. downsample 
    # ==========================================
    df_sampled = hf_df_1455.with_columns(
        intraday_cum_bps = pl.col("intraday_cum") * amplify
    ).group_by_dynamic(
        "datetime", 
        every=f"{downsample}m", 
        closed="right",
        label="right"
    ).agg(
        cum_val = pl.col("intraday_cum_bps").last(),
        date_int = pl.col("date_int").last(),
        last_beta = pl.col("filled_beta").last(),
        last_tick_time = pl.col("datetime").last(),
        last_price = pl.col("close").last() 
    ).drop_nulls(subset=["cum_val"])
    
    cum_vals = df_sampled["cum_val"].to_numpy()
    dates = df_sampled["date_int"].to_numpy()
    betas = df_sampled["last_beta"].to_numpy()
    tick_times = df_sampled["last_tick_time"].to_list()
    prices = df_sampled["last_price"].to_numpy() 
    
    if len(cum_vals) < m:
        return[]
        
    is_eod = np.concatenate([dates[:-1] != dates[1:], [True]])
    eod_indices = np.where(is_eod)[0]
    
    records =[]
    for idx in eod_indices:
        if idx - m + 1 < 0:
            continue
            
        # suspend logic
        t_time = tick_times[idx]
        if t_time.hour < 14 or (t_time.hour == 14 and t_time.minute < 45):
            continue
            
        # reach price limit eg 14:35, 14:45, 14:55  
        tail_prices = prices[idx - 2 : idx + 1] if idx >= 2 else prices[:idx+1]
        if np.std(tail_prices) < 1e-5: 
            continue
            
        curve_m = cum_vals[idx - m + 1 : idx + 1]
        curr_date = dates[idx]
        
        records.append({
            "date_int": curr_date,
            "curve": curve_m,
            "daily_ret": ret_dict.get(curr_date, 0.0), 
            "last_beta": betas[idx]
        })
        
    return records


def compute_rolling_macro_states(bench_data: pa.Table, loopback: int):
    """
    T-1 14:55 / T 14:55 动态分位数界定宏观状态自适应高波/低波周期, 避免状态太多先验概率支撑模型会严重退化 
    """
    bench_df = pl.from_arrow(bench_data).sort("tick").with_columns(
        datetime = pl.from_epoch(pl.col("tick"), time_unit="s")
    )
    min_periods = int(loopback/2)
    
    # ==========================================
    # 1. eliminate data after 14:55
    # ==========================================
    bench_1455 = bench_df.filter(
        # pl.col("datetime").dt.time() <= datetime.time(14, 55, 0) # expr
        pl.col("datetime").dt.hour() * 60 + pl.col("datetime").dt.minute() <= 14 * 60 + 55
    )
    
    # ==========================================
    # 2. aggregate snapshot after 14:55
    # ==========================================
    daily_bench = bench_1455.with_columns(
        date_int = pl.col("datetime").dt.strftime("%Y%m%d").cast(pl.Int32)
    ).group_by("date_int").agg(
        close_1455 = pl.col("close").last() 
    ).sort("date_int")
    
    # ==========================================
    # 3. 252 rolling rets 
    # ==========================================
    daily_bench = daily_bench.with_columns(
        daily_ret_1455 = pl.col("close_1455").pct_change()
    ).with_columns(
        p20 = pl.col("daily_ret_1455").rolling_quantile(quantile=0.2, window_size=loopback, min_periods=min_periods), # at least not null nums
        p80 = pl.col("daily_ret_1455").rolling_quantile(quantile=0.8, window_size=loopback, min_periods=min_periods)
    ).drop_nulls() 
    
    # ==========================================
    # 4. macro_state
    # ==========================================
    daily_bench = daily_bench.with_columns(
        macro_state = pl.when(pl.col("daily_ret_1455") < pl.col("p20")).then(0)  
                      .when(pl.col("daily_ret_1455") > pl.col("p80")).then(2)  
                      .otherwise(1)                                            
    )
    
    return dict(zip(daily_bench["date_int"].to_list(), daily_bench["macro_state"].to_list()))


def calculate_gpd(returns_series: np.array, quantiles: list): 
    """
    :param returns_series: np.array daily_returns
    :param quantiles: np.array  bins
    """
    returns = np.array(returns_series)
    returns = returns[np.isfinite(returns)]
    
    centers = np.zeros(len(quantiles) + 1)

    edges = np.quantile(returns, quantiles) # any np.nan return nan
    u_down = edges[0] 
    u_up = edges[-1]  
    
    # ==========================================
    # empritical
    # ==========================================
    centers[1] = np.mean(returns[(returns >= edges[0]) & (returns < edges[1])])
    centers[2] = np.mean(returns[(returns >= edges[1]) & (returns < edges[2])])
    centers[3] = np.mean(returns[(returns >= edges[2]) & (returns < edges[3])])
    
    # ==========================================
    # right GPD 
    # ==========================================
    right_tail = returns[returns > u_up] - u_up # loc = 0

    if len(right_tail) > 10:
        # scipy genpareto
        c_right, loc_right, scale_right = genpareto.fit(right_tail, floc=0) # evt and gpd
        
        # GPD E[X - u | X > u] = scale / (1 - c) 
        if c_right < 1:
            expected_excess_up = scale_right / (1 - c_right)
            centers[4] = u_up + expected_excess_up
        else:
            centers[4] = np.mean(returns[returns > u_up])
    else:
        centers[4] = np.mean(returns[returns > u_up])
        
    # ==========================================
    # left GPD
    # ==========================================
    left_tail = -returns[returns < u_down] - (-u_down) # min 
    if len(left_tail) > 10:
        c_left, loc_left, scale_left = genpareto.fit(left_tail, floc=0)
        if c_left < 1:
            expected_excess_down = scale_left / (1 - c_left)
            centers[0] = - (-u_down + expected_excess_down) 
        else:
            centers[0] = np.mean(returns[returns < u_down])
    else:
        centers[0] = np.mean(returns[returns < u_down])
    return edges, centers


def build_rolling_gpd(panel_df: pl.DataFrame, quantiles: list, loopback: int, freq_month: int):
    df = panel_df.select(["date_int", "daily_ret"]).drop_nulls()
    unique_dates = df.select("date_int").unique().sort("date_int").to_series().to_numpy()
    
    gpd_dict = {}
    last_update_idx = -9999
    current_edges, current_centers = None, None
    
    for idx, d_int in enumerate(unique_dates):
        year = d_int // 10000
        month = (d_int % 10000) // 100
        curr_month_idx = year * 12 + month
        
        if current_edges is None or (curr_month_idx - last_update_idx >= freq_month):
            start_idx = max(0, idx - loopback)
            start_date = unique_dates[start_idx]
                
            hist_rets = df.filter(
                (pl.col("date_int") >= start_date) & 
                (pl.col("date_int") <= d_int) # 14:55
            )["daily_ret"].to_numpy()
                
            current_edges, current_centers = calculate_gpd(hist_rets, quantiles)
            last_update_idx = curr_month_idx
                    
        gpd_dict[d_int] = (current_edges, current_centers)
    return gpd_dict


def evaluate_objective(p_val: float, cond_mean: np.array, uncond_mean:np.array, m:int, penalty_m:int): 
    """
    1. **no direction**  abs(spread)
    2. **smooth** -log10(p_val)
    3. **length penalty**
    """
    spread = cond_mean - uncond_mean
    abs_spread = abs(spread)
    
    safe_pval = max(p_val, 1e-10)
    confidence = -np.log10(safe_pval) # penalty  log10(1.0) = 0 / log10(0.001) = -3 
    raw_score = confidence * abs_spread * 10000.0

    # Occam's Razor
    if m > penalty_m:
        penalty_factor = math.exp(- (m - penalty_m) / 50.0) 
        raw_score = raw_score * penalty_factor
    return raw_score
