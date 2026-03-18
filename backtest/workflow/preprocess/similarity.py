#! /usr/bin/env python3
# -*- encondig: utf-8 -*-

import os
import ray
import uuid
import math
import numpy as np
import stumpy
import pyarrow as pa
import pyarrow.compute as pc
import polars as pl
import matplotlib.pyplot as plt
import scipy.stats as stats
from itertools import chain
from typing import List, Any, Dict
from ray import tune
from scipy.stats import chi2_contingency, ks_2samp, skew, genpareto

import backtest as bt

from bt_sdk.core.client import GetMdApi, FactorTopic
from bt_sdk.core.protocol import QueryBody
from backtest.execution.actor import *


def _initialize_mdpai():
    md_addr = os.getenv("MD_ADDR", "127.0.0.1:50051").split(":")
    mdapi = GetMdApi(addr=(md_addr[0], int(md_addr[1])))
    _runner = AsyncRunner()
    _runner.start() # new_event_loop
    _loop = _runner.get_loop()
    mdapi.start(_loop)
    return mdapi


def preload(start_date: int, end_date: int, benchmark: bytes, market: str, frac:float, adj=1): # 0 1 2 / raw qfq hfq
    md_api = _initialize_mdpai()

    # universe
    table = md_api.get_instrument() 
    mask = pc.and_(
        pc.less(table["first_trading"], end_date),
        # pc.greater(table["delist"], start_date)
        pc.starts_with(table["sid"], market)
    )
    filter_table = table.filter(mask)

    num_rows = filter_table.num_rows
    num_samples = int(frac * num_rows)
    result = filter_table.take(np.random.choice(num_rows, size=num_samples, replace=False))
    universe = result.column("sid").cast(pa.binary()).to_pylist() # view(pa.uint8())
    # benchmark
    bench_body = QueryBody(start_date=start_date, end_date=end_date, sid=[benchmark]) 
    bench_data = md_api.get_benchmark(bench_body)
    # tick
    body = QueryBody(start_date=start_date, end_date=end_date, sid=universe)
    tick_data = md_api.get_subscribe(body, adj)
    return {"benchmark": bench_data[benchmark], "tick": tick_data}


def extract_from_beta_with_freq(raw, bench_ref, rolling_freq: int, ewm_span: int):
    """
    :param data_joined: 包含高频数据的 DataFrame (需包含 tick, close, close_bench, log_ret, log_ret_bench)
    :param rolling_freq: 降采样的频率，例如 "10m"
    :param ewm_span: 交易日
    """
    span = int(ewm_span * 4 * np.floor(60/rolling_freq))
    
    benchmark = pl.from_arrow(bench_ref)
    # filter(
    #     pl.col("timestamp").dt.minute() % rolling_freq == 0)
 
    data_joined = raw.join(
        benchmark.select(["tick", "close"]).rename({"close": "close_bench"}),
        on="tick",
        how="left" # left / inner / right / outer
    ).sort("tick").with_columns(
        datetime = pl.from_epoch(pl.col("tick"), time_unit="s"),
        log_ret_raw = pl.col("close").log().diff(),
        log_ret_bench_raw = pl.col("close_bench").log().diff()
    )

    beta_df = data_joined.group_by_dynamic( # agg drop original column and keep new
        "datetime", 
        every=f"{rolling_freq}m",
        closed="left"
    ).agg(
        close_freq = pl.col("close").last(),
        close_bench_freq = pl.col("close_bench").last()
    ).sort("datetime").with_columns(
        ret_freq = pl.col("close_freq").log().diff(),
        ret_bench_freq = pl.col("close_bench_freq").log().diff()
    ).with_columns(
        xy_ewm = (pl.col("ret_freq") * pl.col("ret_bench_freq")).ewm_mean(span=span, ignore_nulls=True),
        x_ewm  = pl.col("ret_freq").ewm_mean(span=span, ignore_nulls=True),
        y_ewm  = pl.col("ret_bench_freq").ewm_mean(span=span, ignore_nulls=True),
        y2_ewm = (pl.col("ret_bench_freq") ** 2).ewm_mean(span=span, ignore_nulls=True)
    ).with_columns(
        cov_xy = pl.col("xy_ewm") - (pl.col("x_ewm") * pl.col("y_ewm")),
        var_y  = pl.col("y2_ewm") - (pl.col("y_ewm") ** 2)
    ).with_columns(
        beta = pl.when(pl.col("var_y") > 1e-8)
                     .then(pl.col("cov_xy") / pl.col("var_y"))
                     .otherwise(0.0),
    ).with_columns(
        filled_beta = pl.col("beta").shift(1).forward_fill().fill_null(1.0),
        datetime_trunc = pl.col("datetime").dt.truncate(f"{rolling_freq}m")
    ).select(["datetime_trunc", "filled_beta"])  

    hf_df = data_joined.with_columns(
        datetime_trunc = pl.col("datetime").dt.truncate(f"{rolling_freq}m")
    ).join(
        beta_df,
        on="datetime_trunc",
        how="left"
    ).with_columns(
        filled_beta = pl.col("filled_beta").forward_fill().fill_null(1.0)
    )

    hf_df = hf_df.sort("tick").with_columns( # join disorder
        residual_ret = pl.col("log_ret_raw") - pl.col("filled_beta") * pl.col("log_ret_bench_raw").fill_null(0.0),
        date_int = pl.col("datetime").dt.strftime("%Y%m%d").cast(pl.Int32)
    ).with_columns(
        # intraday_cum = pl.col("residual_ret").cum_sum().over("date_int"),
        # intraday_bench_cum = pl.col("log_ret_bench_raw").cum_sum().over("date_int")
        intraday_cum = pl.col("residual_ret").cum_sum(),
        intraday_bench_cum = pl.col("log_ret_bench_raw").cum_sum()
    )
    return hf_df


def dsample_and_concat(hf_dfs: Dict[str, pl.DataFrame], m: int , downsample: int = 10, amplify:int =1000):
    """
        downsample: minute
    """
    multi_asset =[]
    multi_macro = []
    multi_dates =[]
    
    nan_buffer = np.full(m, np.nan)
    date_buffer = np.full(m, -1) 

    # mulitply = 10000
    for hf_df in hf_dfs.values():
        sample_df = hf_df.with_columns( # sort("datetime")
            intraday_cum_bps = pl.col("intraday_cum") * amplify ,
            intraday_cum_bench_bps = pl.col("intraday_bench_cum") * amplify 
        ).group_by_dynamic(
            "datetime", 
            every=f"{downsample}m", 
            closed="left"
        ).agg(
            cum_5m = pl.col("intraday_cum_bps").last(),
            cum_bench_5m = pl.col("intraday_cum_bench_bps").last(),
            date_int = pl.col("date_int").last()
        )
        # # concat add np.nan between day
        sample_nan_df = sample_df.drop_nulls(subset=["cum_5m"])
        # values = sample_nan_df["cum_5m"].to_numpy()
        # bench_values = sample_nan_df["cum_bench_5m"].to_numpy()
        # dates = sample_nan_df["date_int"].to_numpy()
        multi_asset.append(sample_nan_df["cum_5m"].to_numpy())
        multi_macro.append(sample_nan_df["cum_bench_5m"].to_numpy())
        multi_dates.append(sample_nan_df["date_int"].to_numpy())

        # fill np.nan between different asset 
        multi_asset.append(nan_buffer)
        multi_macro.append(nan_buffer)
        multi_dates.append(date_buffer)

    multi_dates = np.concatenate(multi_dates)
    multi_asset = np.concatenate(multi_asset)
    multi_macro = np.concatenate(multi_macro)
    
    # dates[i] != dates[i+1] last_day tick
    boundaries = np.where(multi_dates[:-1] != multi_dates[1:])[0]
    valid_boundaries = [idx for idx in boundaries if multi_dates[idx] != -1]
    if multi_dates[-1] != -1:
        valid_boundaries.append(len(multi_dates) - 1)
    eod_indices = np.array(valid_boundaries)
    return multi_asset, multi_macro, eod_indices 


def get_atsc(raw_array: np.array, m: int, threshold_r: float):
    # filter by person d^2 = 2m(1-r)
    threshold_d = math.sqrt(2 * m * (1 - threshold_r)) 
    mp = stumpy.stump(raw_array, m=m)
    # import pdb; pdb.set_trace()

    distances = np.copy(mp[:, 0])
    # np.argmin <= np.inf
    zero_mask = distances <= 1e-5
    if np.all(zero_mask):
        raise ValueError("所有片段的距离都接近 0.0 (可能全是相同的常数/涨跌停直线)")
    distances[zero_mask] = np.inf

    anchor_idx = np.argmin(distances)
    v_d = distances[anchor_idx]
    
    if v_d > threshold_d or np.isinf(v_d):
        return None, None

    left_I = np.copy(mp[:, 2])   
    right_I = np.copy(mp[:, 3])  

    invalid_mask = (mp[:, 0] > threshold_d) | zero_mask
    left_I[invalid_mask] = -1  
    right_I[invalid_mask] = -1 

    backward_chain =[]
    curr_left = left_I[anchor_idx]

    while curr_left != -1 and curr_left not in backward_chain:
        backward_chain.append(curr_left)
        curr_left = left_I[curr_left]
        
    backward_chain.reverse() 
    # forward_chain = []
    # curr_right = right_I[anchor_idx]
    # while curr_right != -1 and curr_right not in forward_chain:
    #     forward_chain.append(curr_right)
    #     curr_right = right_I[curr_right]

    # full_atsc_chain = backward_chain + [anchor_idx] + forward_chain
    atsc_chain = backward_chain + [anchor_idx]
    
    atsc_chain_v = np.array([raw_array[idx : idx + m] for idx in atsc_chain])
    return atsc_chain, atsc_chain_v


def calculate_gpd(returns_series, quantiles=[0.10, 0.30, 0.70, 0.90]): # 252 ret_return
    """
    基于极值理论(EVT)与GPD分布 动态计算收益率的 Bin 边界和代表值(期望)
    :param returns_series: 历史收益率数组 (例如过去 1-2 年的日收益率)
    :param quantiles: 分位数切分点
    """
    returns = np.array(returns_series)
    returns = returns[np.isfinite(returns)]
    
    edges = np.quantile(returns, quantiles) # any np.nan return nan
    u_down = edges[0] 
    u_up = edges[-1]  

    centers = np.zeros(len(quantiles) + 1)
    
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
        c_right, loc_right, scale_right = genpareto.fit(right_tail, floc=0)
        
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


def calculate_gpd_cvar(returns, confidence_level=0.99):
    """基于 GPD 计算 99% 极值条件在险价值 (CVaR)"""
    # ====== 在仓位管理中的应用 ======
    # 假设您的总资金是 100 万，您能承受的单日极限回撤是 5 万 (5%)
    # 正态分布可能告诉您全仓买入没事。但 GPD 告诉您 99% CVaR 是 12%！
    # 您的严格仓位上限 = 极限承受力 / GPD_CVaR = 5% / 12% = 41.6% (绝不满仓！)
    losses = -np.array(returns)
    threshold_percentile = 95
    u = np.percentile(losses, threshold_percentile)
    
    tail_losses = losses[losses > u] - u
    # c 是形状参数 (xi), loc 是位置参数(固定为0), scale 是尺度参数 (beta)
    shape_xi, loc, scale_beta = genpareto.fit(tail_losses, floc=0)
    
    # GPD CVar 相比于正态分布的 VaR
    tail_prob = 1.0 - (threshold_percentile / 100.0)
    alpha = 1.0 - confidence_level
    
    cvar_gpd = u + (scale_beta / (1 - shape_xi)) * ( ((tail_prob / alpha) ** shape_xi) - 1 )
    return cvar_gpd


def get_dynamic_macro_state(market_ret, his_market_returns): # 252 ret_return
    """
    使用动态分位数界定宏观状态, 自适应高波/低波周期
    """
    # 很多技术形态链（FSM）在“普通阴跌（Bin 1）”时依然有效，但在“流动性危机/千股跌停（Bin 0）”时会彻底失效（即 Alpha 被 Beta 强势反噬）。如果不把宏观的“极端尾部”单独切分出来，您就无法在全概率公式中隔离这种黑天鹅风险。
    # 不再使用固定的 `±0.5%`，而是对大盘历史收益率求动态分位数：
    # * **宏观 Bin 0 (空头尾部情绪)**：大盘收益率 `< 过去252天的 20% 分位数`
    # * **宏观 Bin 1 (常规震荡情绪)**：大盘收益率介于 `20% ~ 80% 分位数`
    # * **宏观 Bin 2 (多头尾部情绪)**：大盘收益率 `> 过去252天的 80% 分位数`

    # 假设您把宏观大盘分为 **5 个 Bins**（暴跌、阴跌、震荡、小涨、暴涨），同时微观个股也分为 **5 个 Bins**。
    # * 您的微观条件概率矩阵 `conditional_alpha` 的维度将变成 `5 × 5 = 25` 个格子！
    # * 假设一条极其罕见但胜率极高的 FSM 链条，在历史上只触发了 15 次。
    # * 这 15 次观测值要散落到 25 个格子中。结果就是：**大部分格子全是空的！**
    # * 此时，基于拉普拉斯平滑（Dirichlet 先验的 `+1.0`），未观测到的状态全靠先验概率支撑，模型会严重退化，失去预测准度。
    p20 = np.percentile(his_market_returns, 20)
    p80 = np.percentile(his_market_returns, 80)
    
    if market_ret < p20:
        return 0  
    elif market_ret > p80:
        return 2  
    else:
        return 1  


def robust_z_normalize(window_data):
    """使用 MAD 进行鲁棒 Z-标准化, 替换原来的 (x - mean)/std """
    median_val = np.median(window_data)
    abs_dev = np.abs(window_data - median_val)
    
    mad = np.median(abs_dev)
    if mad == 0:
        mad = 1e-8
        
    robust_std = 1.4826 * mad
    robust_z = (window_data - median_val) / robust_std
    return robust_z


def evaluate_objective(p_val, cond_mean, uncond_mean, alpha_penalty=100.0, beta_penalty=10.0): # 惩罚因子权重
    spread = cond_mean - uncond_mean
    
    if p_val <= 0.05 and spread > 0: # positive
        safe_pval = max(p_val, 1e-10)
        score = -np.log10(safe_pval) * spread
    else: 
        score = -np.inf
        if p_val > 0.05:
            # score -= alpha_penalty * (p_val - 0.05)
            score = 0.0
            
        if spread <= 0:
            score = -beta_penalty * abs(spread)
    return score


def evaluate_and_build_fsm(
    vec_m, 
    threshold_r,
    asset_returns,    # 10m intraday_cum (m 个nan)
    macro_returns,    # 10m benchmark cum (m 个nan) 
    asset_bins, # GPD Bins
    eod_indices,
    forward_window # KS 检验用的 T+N 个 10分钟 K 线
):
    """
    1. 当天的 14:55 作为统一执行点
    2. 提取 T+1 日开盘后 T+5, T+10 的累积收益进行 KS/MW-U 有效性检验
    3. 提取 T+1 日的全天累计收益与 T+1 日的宏观状态，更新 FSM 狄利克雷分布
    """
    m = len(vec_m)
    threshold_d = math.sqrt(2 * m * (1 - threshold_r))
    
    # =========================================================
    # step1:  daily start and end via np.nan 
    # =========================================================
    # is_val = ~np.isnan(asset_returns)
    # eod_mask = is_val[:-1] & ~is_val[1:]
    # eod_indices = np.where(eod_mask)[0].tolist() # return index / np.where(cond, x,y) ---> new array
    # if is_val[-1]: 
    #     eod_indices.append(len(asset_returns) - 1)
    # eod_indices = np.array(eod_indices)
    
    # used for ks test on minute
    start_indices = np.zeros(len(eod_indices), dtype=int)
    start_indices[0] = 0
    start_indices[1:] = eod_indices[:-1] + 1

    # =========================================================
    # step 2: Macro States: 0, 1, 2
    # =========================================================
    daily_macro_returns = macro_returns[eod_indices]
    
    valid_macro = daily_macro_returns[~np.isnan(daily_macro_returns)]
    if len(valid_macro) == 0:
        return {"status": "failed", "reason": "宏观数据全空", "metrics_score": -np.inf}
        
    p20, p80 = np.percentile(valid_macro, [20, 80])
    daily_macro_states = np.where(
        daily_macro_returns < p20, 0, 
        np.where(daily_macro_returns > p80, 2, 1)
    )
    
    # =========================================================
    # step 3: distance reflect 
    # =========================================================
    distance_profile = stumpy.mass(vec_m, asset_returns) # start_point
    trigger_indices = np.where(distance_profile < threshold_d)[0]
    
    if len(trigger_indices) < 10:
        return {"status": "failed", "reason": "总触发次数过少 (<10)", "metrics_score": -np.inf}
    
    trigger_ends = trigger_indices + m - 1
    day_indices = np.searchsorted(eod_indices, trigger_ends)
    
    valid_mask = day_indices < len(eod_indices)
    valid_day_indices = day_indices[valid_mask]
    unique_day_indices = np.unique(valid_day_indices)
    
    fsm_updates =[]
    cond_ks_returns = {fw:[] for fw in forward_window}
    
    # =========================================================
    # step 4 : T+1 ret and FSM
    # =========================================================
    for day_idx in unique_day_indices:
        if day_idx + 1 < len(eod_indices):
            trigger_cum_val = asset_returns[eod_indices[day_idx]] 
            # T+1 ret
            next_day_ret = asset_returns[eod_indices[day_idx + 1]] - trigger_cum_val 
            next_day_macro = daily_macro_states[day_idx + 1]
            
            if not np.isnan(next_day_ret):
                fsm_updates.append({
                    "next_day_macro": next_day_macro,
                    "next_day_ret": next_day_ret
                })
                
            # --- KS T+1 intraday ---
            for fw in forward_window:
                target_idx = start_indices[day_idx + 1] + fw - 1
                
                # if target_idx <= eod_indices[day_idx + 1]: # intraday
                if target_idx < len(asset_returns): 
                    fw_ret = asset_returns[target_idx] - trigger_cum_val 
                    if not np.isnan(fw_ret):
                        cond_ks_returns[fw].append(fw_ret)

    # =========================================================
    # step 5: KS / MW-U Test alpha 
    # =========================================================
    ks_results = {}
    passed_alpha_test = False
    
    for fw in forward_window:
        cond_rets = np.array(cond_ks_returns[fw])
        if len(cond_rets) < 5:
            continue
            
        all_fw_indices = start_indices + fw - 1
        # valid_fw_indices = all_fw_indices[all_fw_indices <= eod_indices]
        valid_fw_indices = all_fw_indices[all_fw_indices < len(asset_returns)]
        uncond_rets = asset_returns[valid_fw_indices]
        trigger_base_vals = asset_returns[eod_indices[:len(valid_fw_indices)]]

        uncond_rets = uncond_rets - trigger_base_vals
        uncond_rets = uncond_rets[~np.isnan(uncond_rets)]

        # 检验 A: Kolmogorov-Smirnov (K-S) 检验
        # 检验两个样本是否来自同一个分布。P-value < 0.05 拒绝原假设，说明形态有效改变了收益率分布
        ks_stat, ks_pval = stats.ks_2samp(cond_rets, uncond_rets)
        # 检验 B: 曼-惠特尼 U 检验 (Mann-Whitney U Test) / 秩和检验
        # 检验条件收益率的中位数/整体水平是否显著高于无条件收益率 (单边检验)
        u_stat, u_pval = stats.mannwhitneyu(cond_rets, uncond_rets, alternative='greater')

        cond_mean_val = np.mean(cond_rets) 
        uncond_mean_val = np.mean(uncond_rets) 
        if cond_mean_val > uncond_mean_val:
            direction = "Long"
            u_stat, u_pval = stats.mannwhitneyu(cond_rets, uncond_rets, alternative='greater')
        else:
            direction = "Short"
            u_stat, u_pval = stats.mannwhitneyu(cond_rets, uncond_rets, alternative='less')

        score = evaluate_objective(u_pval, cond_mean_val, uncond_mean_val)
        
        ks_results[f"T+{fw}"] = {
            "cond_mean": cond_mean_val,
            "uncond_mean": uncond_mean_val,
            "ks_pval": ks_pval,
            "u_pval": u_pval,
            "score": score
        }
        if u_pval < 0.05:
            passed_alpha_test = True
    
    metrics_score = max([k["score"] for k in ks_results.values()]) if ks_results else -np.inf

    if not passed_alpha_test:
        return {"status": "failed", "reason": "KS/MW-U 检验不显著", "ks_results": ks_results, "metrics_score": metrics_score}

    # =========================================================
    # step6 : FSM [3,5]
    # =========================================================
    num_bins = len(asset_bins) + 1
    fsm_prior_matrix = np.ones((3, num_bins)) # 拉普拉斯平滑 +1
    
    for update in fsm_updates:
        macro_s = int(update["next_day_macro"])
        ret = update["next_day_ret"]
        bin_idx = np.digitize(ret, asset_bins)
        fsm_prior_matrix[macro_s, bin_idx] += 1.0


    return {
        "status": "success",
        "fsm_trigger_count": len(fsm_updates), 
        "ks_results": ks_results,
        "fsm_prior_matrix": fsm_prior_matrix,
        "metrics_score": metrics_score
    }

def run_pipeline(config, data_ref, forward_window): # config must first

    extract = {}
    # extract ret from beta
    for asset, _ref in data_ref["tick"].items():
        extract[asset] = extract_from_beta_with_freq(_ref, data_ref["benchmark"], config["rolling_freq"], config["ewm_span"])

    # used for stumpy multiply and resample 
    m = int(config["ndays"] * np.floor(4 * 60 / config["downsample"]))  
    padded_array, bench_padded_array, eod_indices = dsample_and_concat(extract, m, downsample=config["downsample"])
    # tsc
    tsc, tsc_v = get_atsc(padded_array, m, config["threshold_r"])

    # nbins
    eod_cum_values = padded_array[eod_indices]
    daily_real_returns = np.diff(eod_cum_values, prepend=0) 
    edges, centers = calculate_gpd(daily_real_returns)

    # evaluate 
    res = evaluate_and_build_fsm(tsc_v[-1], config["threshold_r"], padded_array, bench_padded_array, edges, eod_indices, forward_window)
    return res


def train_hpo(start_date=20100101, end_date=20200101, benchmark=b"000001", market="6", frac:float=0.01, forward_window=[5,10,20], 
                num_samples:int =200, max_concurrency:int=10, topK=5): 
    # # --- 启动 Ray ---
    env_config = {}

    ray.init(address="auto", 
            namespace="backtest", 
            # runtime_env={"env_vars": json.dumps(env_config)}, # 
            ignore_reinit_error=True)

    print("preload data")
    data = preload(
        start_date=start_date, 
        end_date=end_date, 
        benchmark=benchmark,
        market=market, # 6/688/0/3
        frac=frac,
        adj=FactorTopic.Hfq
    )
    data_ref = ray.put(data) # Object store and publish to worker

    search_space = {
        # extract from beta
        "rolling_freq": tune.randint(5, 30), # m
        "ewm_span": tune.randint(5, 30), # ewm_span

        # downsample for stumpy 
        "downsample": tune.randint(10, 60),# minute
        "ndays":  tune.randint(1, 14),

        # stumpy tsc and filter
        "threshold_r": tune.uniform(0.8, 0.99),
    }

    # --- 配置 ASHA 算法 (早停) ---
    # metric: 优化目标, mode:最大化 / grace_period: 至少跑多久才开始判断 / reduction_factor: 每轮淘汰比例
    asha_scheduler = tune.schedulers.ASHAScheduler(
        metric="metrics_score",
        mode="max", 
        grace_period=1, 
        reduction_factor=4 
    )
    
    # --- 启动 Tuner ---
    wrapped_trainable = tune.with_resources(
        tune.with_parameters(
            run_pipeline,
            data_ref=data_ref,
            forward_window=forward_window  
        ),
        resources={"cpu": 8, "gpu": 0}
    )

    tuner = tune.Tuner( 
        wrapped_trainable, 

        param_space=search_space,
        
        tune_config=tune.TuneConfig(
            num_samples=num_samples,            
            max_concurrent_trials=max_concurrency,    
            scheduler=asha_scheduler
        ),
        
        run_config=tune.RunConfig(
            name="my_strategy_hpo",
            storage_path="/tmp/ray_tune_results",
        ),
    )
    results = tuner.fit()

    # --- 分析结果 ---
    best_trial = results.get_best_result(metric="metrics_score", mode="max")
    print("="*30)
    print("Best trial config: {}".format(best_trial.config))
    print("Best trial final sharpe: {}".format(best_trial.metrics["ks_results"])) 

    # # topk
    # print(f"========== Top {K} Trials ==========")
    # df = results.get_dataframe()
    # valid = df[df["metrics_score"] > -np.inf].copy()
    # top_k_df = valid.sort_values(by="metrics_score", ascending=False).head(topK)
    
    # top_k_configs =[]
    # for idx, row in top_k_df.iterrows():
    #     # Ray Tune 会把 config 平铺为 config/xxx
    #     cfg = {k.replace("config/", ""): v for k, v in row.items() if k.startswith("config/")}
    #     top_k_configs.append({
    #         "config": cfg,
    #         "metrics_score": row["metrics_score"],
    #         "fsm_prior_matrix": row.get("fsm_prior_matrix"), 
    #         "trial_id": row["trial_id"] 
    #     })
    #     print(f"Trial: {row['trial_id']} | Score: {row['metrics_score']:.4f} | Config: {cfg}")
        

if __name__ == "__main__":

    train_hpo() 
