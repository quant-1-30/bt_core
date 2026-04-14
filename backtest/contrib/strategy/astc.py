#! /usr/bin/env python3
# -*- encondig: utf-8 -*-

import numpy as np
import stumpy
import polars as pl
import scipy.stats as stats
from typing import List, Any, Dict
from dtaidistance import dtw

from workflow.function import *


def intercept(config):
    # ====================================================
    # Domain Knowledge Guardrails
    # ====================================================
    # 拦截 1 形态点数过少非有效博弈或过多无法匹配
    m = int(config["ndays"] * np.floor(240 / config["downsample"]))
    if m < 8 or m > 60:
        return {"status": "failed", "reason": f"m={m} 长度不合理", "metrics_score": -9999}
        
    # # 拦截 2 频率倒挂 采样频率比Beta频率还高噪音
    # if config["downsample"] < config["rolling_freq"]:
    #     return {"status": "failed", "reason": "频率倒挂", "metrics_score": -9999}
        
    # # 拦截 3 相关系数与长度木桶效应
    # if m > 30 and config["threshold_r"] > 0.90:
    #     return {"status": "failed", "reason": "长序列要求高r", "metrics_score": -9999}
    return {"status": "success"}


def get_atsc(raw_array: np.array, config):
    # filter by person d^2 = 2m(1-r)
    threshold_d = config["threshold_d"]
    m = config["m"]
    mp = stumpy.stump(raw_array, m=m)

    distances = np.copy(mp[:, 0])
    # np.argmin <= np.inf
    zero_mask = distances <= 1e-5
    if np.all(zero_mask):
        raise ValueError("exclude nearly horizonal vector")
    distances[zero_mask] = np.inf

    anchor_idx = np.argmin(distances)
    v_d = distances[anchor_idx]
    
    if v_d > threshold_d or np.isinf(v_d):
        print("v_d not effective: ", v_d)
        return None, np.array([])

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
    config: dict,
    macro_dict: dict,
    gpd_dict: dict,
    stats_window: list 
): 
    # laplace and FSM 
    num_bins = len(config["gpd_quantiles"]) + 1
    fsm_prior_matrix = np.ones((3, num_bins))
    
    # vectorize distance
    curves = np.stack(panel_df["curve"].to_numpy()) # stride not contiguous
    z_curves = robust_z_normalize(curves)
    z_motif = robust_z_normalize(motif)

    # C-contiguous for C speed
    z_curves_c = np.ascontiguousarray(z_curves, dtype=np.float64)
    z_motif_c = np.ascontiguousarray(z_motif, dtype=np.float64)
    # distances = np.linalg.norm(z_curves_c - z_motif_c, axis=1)
    dtw_window = calculate_dtw_params(config) 
    distances = np.array([
        dtw.distance_fast(
            row, 
            z_motif_c, 
            window=dtw_window, 
            max_dist= config["threshold_d"] # avoid 0.5 * math.sqrt(m) 
        ) for row in z_curves_c
    ]) 
    # distance concat DataFrame
    eval_df = panel_df.with_columns(
        pl.Series("distance", distances),
        pl.col("date_int").replace(macro_dict, default=1).alias("macro_state") #replace_strict
    )
    
    # trigger by threshold
    triggers = eval_df.filter(pl.col("distance") < config["threshold_d"])
    if len(triggers) < 10:
        return {"status": "failed", "reason": "总触发次数过少 (<10)", "metrics_score": -np.inf}
         
    # evaluate stats on T+1 / T+5 / T+10
    for row in triggers.iter_rows(named=True):
        macro_state = row["macro_state"]
        ret_t1 = row["fwd_ret_1"]
        if not ret_t1:
            continue
        # GPD edges
        trigger_date = row["date_int"]
        edges, _ = gpd_dict.get(trigger_date, (None, None))
        if edges is None: continue

        bin_idx = np.digitize(ret_t1, edges)
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

        score = evaluate_objective(u_pval, cond_mean_val, uncond_mean_val, len(motif), config["penalty_m"])
        
        ks_results[f"T+{fw}"] = {
            "cond_mean": cond_mean_val,
            "uncond_mean": uncond_mean_val,
            "ks_pval": ks_pval,
            "u_pval": u_pval,
            "score": score
        }
        if u_pval < 0.05:
            passed_alpha_test = True
    
    raw_score = max([k["score"] for k in ks_results.values()]) if ks_results else -np.inf

    if not passed_alpha_test:
        return {"status": "failed", "reason": "KS/MW-U 检验不显著", "metrics_score": raw_score}

    return {
        "status": "success",
        "fsm_trigger_count": len(triggers), 
        "ks_results": ks_results,
        "fsm_prior_matrix": fsm_prior_matrix,
        "learned_motif": motif.tolist(),
        "metrics_score": raw_score
    }


def run_pipeline(config: dict, data_ref: dict, stats_window: list, actual_date:int): 
    """
    Pattern and Prior Matrix KS/MW-U Score
    """
    status = intercept(config)
    if status["status"] == "failed":
        return status

    # hf_dfs = {}
    # for asset, _ref in data_ref["tick"].items():
    #     hf_dfs[asset] = extract_from_beta_with_freq(
    #         # _ref, data_ref["benchmark"], config["rolling_freq"], config["ewm_span"], config["signal_type"])
    #         _ref, data_ref["benchmark"], config["signal_type"])
    hf_dfs = process_to_residuals(data_ref["tick"], config["signal_type"])

    m = int(config["ndays"] * np.floor(4 * 60 / config["downsample"]))  
    config["threshold_d"] = math.sqrt(2 * m * (1 - config["threshold_r"])) 
    config["m"] = m

    # =========================================================
    # step 1 concat
    # =========================================================
    padded_array = dsample_and_concat(
        hf_dfs, config
    )
    if len(padded_array) < m:
        return {"status": "failed", "reason": "降采样后数据不足以组成 Motif", "metrics_score": -np.inf}
        
    # =========================================================
    # step 2 14:55 snapshot
    # =========================================================
    snapshots =[]
    for asset, hf_df in hf_dfs.items():
        records = extract_asset_feature(hf_df, config["downsample"], m, amplify=1000)
        for r in records:
            r["sid"] = asset
        snapshots.extend(records)

    panel_df = pl.DataFrame(snapshots).sort(["sid", "date_int"])

    # calculate future ret for stats test
    panel_df = panel_df.with_columns(
        pl.col("daily_ret").shift(-1).over("sid").alias("fwd_ret_1")
    )
    
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

    # calculate fsm 
    eval_panel_df = panel_df.filter(pl.col("date_int") >= actual_date)
    if len(eval_panel_df) == 0:
        return {"status": "failed", "reason": "无有效快照数据", "metrics_score": -np.inf}

    # calculate astc
    tsc, tsc_v = get_atsc(padded_array, config)
    if tsc_v is None or len(tsc_v) == 0:
        return {"status": "failed", "reason": "未找到有效 Motif", "metrics_score": -np.inf}  

    # calculate rolling macro_state and gpd
    gpd_dict = build_rolling_gpd(
        panel_df, 
        quantiles=config["gpd_quantiles"], 
        loopback=config["loopback"], 
        freq_month=config["gpd_freq_month"]
    )
    
    macro_dict = compute_rolling_macro_states(data_ref["benchmark"], config["loopback"])

    res = evaluate_and_build_fsm(
        eval_panel_df, tsc_v[-1], config, macro_dict, gpd_dict, stats_window
    )
    return res
