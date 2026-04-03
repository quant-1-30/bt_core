#! /usr/bin/env python3
# -*- encondig: utf-8 -*-

import numpy as np
import stumpy
import polars as pl
import scipy.stats as stats
from typing import List, Any, Dict

from backtest.workflow.preprocess import *


def get_atsc(raw_array: np.array, m: int, threshold_r: float):
    # filter by person d^2 = 2m(1-r)
    threshold_d = math.sqrt(2 * m * (1 - threshold_r)) 
    mp = stumpy.stump(raw_array, m=m)

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
    atsc_chain = backward_chain + [anchor_idx]
    
    atsc_chain_v = np.array([raw_array[idx : idx + m] for idx in atsc_chain])
    return atsc_chain, atsc_chain_v


def evaluate_and_build_fsm(
    panel_df: pl.DataFrame, 
    motif: np.ndarray, 
    threshold_r: float,
    macro_ref: dict,
    asset_bins: np.ndarray, 
    stats_window: list 
):
    # align 14:55 -> 14:55 
    m = len(motif)
    threshold_d = math.sqrt(2 * m * (1 - threshold_r))
    
    # vectorize distance
    curves = np.stack(panel_df["curve"].to_numpy())
    z_curves = robust_z_normalize(curves)
    z_motif = robust_z_normalize(motif)
    
    distances = np.linalg.norm(z_curves - z_motif, axis=1)
    
    # distance concat DataFrame
    eval_df = panel_df.with_columns(
        pl.Series("distance", distances),
        pl.col("date_int").replace_strict(macro_ref, default=1).alias("macro_state")
    )
    
    # trigger by threshold
    triggers = eval_df.filter(pl.col("distance") < threshold_d)
    if len(triggers) < 10:
        return {"status": "failed", "reason": "总触发次数过少 (<10)", "metrics_score": -np.inf}
        
    # laplace and FSM 
    num_bins = len(asset_bins) + 1
    fsm_prior_matrix = np.ones((3, num_bins)) 
    
    # evaluate stats on T+1 / T+5 / T+10
    for row in triggers.iter_rows(named=True):
        macro_state = row["macro_state"]
        ret_t1 = row["fwd_ret_1"]
        
        bin_idx = np.digitize(ret_t1, asset_bins)
        bin_idx = min(max(bin_idx, 0), num_bins - 1) 
        
        fsm_prior_matrix[macro_state, bin_idx] += 1.0

    # KS / MW-U Test
    ks_results = {}
    passed_alpha_test = False
    
    for fw in stats_window:
        col_name = f"fwd_ret_{fw}"
        
        cond_rets = triggers[col_name].drop_nulls().to_numpy()
        uncond_rets = eval_df[col_name].drop_nulls().to_numpy()
        
        if len(cond_rets) < 5:
            continue
            
        ks_stat, ks_pval = stats.ks_2samp(cond_rets, uncond_rets)
        
        cond_mean_val = np.mean(cond_rets) 
        uncond_mean_val = np.mean(uncond_rets) 
        
        if cond_mean_val > uncond_mean_val:
            u_stat, u_pval = stats.mannwhitneyu(cond_rets, uncond_rets, alternative='greater')
        else:
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
        return {"status": "failed", "reason": "KS/MW-U 检验不显著", "metrics_score": metrics_score}

    return {
        "status": "success",
        "fsm_trigger_count": len(triggers), 
        "ks_results": ks_results,
        "fsm_prior_matrix": fsm_prior_matrix,
        "metrics_score": metrics_score
    }


def run_pipeline(config: dict, data_ref: dict, macro_ref: dict, stats_window: list): 
    """
    Pattern and Prior Matrix KS/MW-U Score
    """
    hf_dfs = {}
    for asset, _ref in data_ref["tick"].items():
        hf_dfs[asset] = extract_from_beta_with_freq(
            _ref, data_ref["benchmark"], config["rolling_freq"], config["ewm_span"]
        )

    m = int(config["ndays"] * np.floor(4 * 60 / config["downsample"]))  

    # =========================================================
    # step 1 concat
    # =========================================================
    padded_array = dsample_and_concat(
        hf_dfs, config["downsample"], m=m, amplify=1000
    )
    
    if len(padded_array) < m:
        return {"status": "failed", "reason": "降采样后数据不足以组成 Motif", "metrics_score": -np.inf}
        
    tsc, tsc_v = get_atsc(padded_array, m, config["threshold_r"])
    if tsc_v is None or len(tsc_v) == 0:
        return {"status": "failed", "reason": "未找到有效 Motif", "metrics_score": -np.inf}
        
    motif = tsc_v[-1]

    # =========================================================
    # step 2 14:55 snapshot
    # =========================================================
    snapshots =[]
    for asset, hf_df in hf_dfs.items():
        records = extract_asset_feature(hf_df, config["downsample"], m, amplify=1000)
        for r in records:
            r["sid"] = asset
        snapshots.extend(records)
        
    if len(snapshots) == 0:
        return {"status": "failed", "reason": "无有效快照数据", "metrics_score": -np.inf}

    panel_df = pl.DataFrame(snapshots).sort(["sid", "date_int"])

    panel_df = panel_df.with_columns(
        pl.col("daily_ret").shift(-1).over("sid").alias("fwd_ret_1")
    )
    
    # forward return used for stats test
    exprs =[]
    for fw in stats_window:
        if fw == 1: 
            continue 
            
        expr = (
            pl.col("daily_ret")
            .rolling_sum(window_size=fw)
            .shift(-fw)                   
            .over("sid")
            .alias(f"fwd_ret_{fw}")
        )
        exprs.append(expr)
        
    if exprs: 
        panel_df = panel_df.with_columns(exprs)

    # gpd and fsm
    all_daily_rets = panel_df["daily_ret"].drop_nulls().to_numpy()
    edges, centers = calculate_gpd(all_daily_rets) 


    res = evaluate_and_build_fsm(
        panel_df, motif, config["threshold_r"], macro_ref, edges, stats_window
    )
    
    if res.get("status") == "success":
        res["learned_motif"] = motif.tolist()
        res["learned_edges"] = edges.tolist()
        res["learned_gpd_centers"] = centers.tolist()
        
    return res
