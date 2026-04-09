# Best trial config: {'rolling_freq': 28, 'ewm_span': 27, 'downsample': 16, 'ndays': 1, 'threshold_r': 0.9365181748464984}

#! /usr/bin/env python3
# -*- encondig: utf-8 -*-

import os
import ray
import math
import numpy as np
import pyarrow as pa
import polars as pl
from typing import List, Any, Dict

from bt_sdk.core.client import FactorTopic
from bt_sdk.core.protocol import QueryBody


class BayesianOnlineFSM:
    def __init__(self, prior_matrix):
        # Postperior Dirichlet
        self.prior_matrix = prior_matrix # np.ones((num_macro_states, num_micro_bins))
        self.pending_update = None 

    def update_posterior(self, realized_ret, gpd_edges):
        if self.pending_update is not None and len(gpd_edges) > 0:
            pre_macro_state = self.pending_update["macro_state"]
            
            real_bin = np.digitize(realized_ret, gpd_edges)
            real_bin = min(max(real_bin, 0), self.num_micro - 1) # to avoid surpass
            
            self.prior_matrix[pre_macro_state, real_bin] += 1.0
            self.pending_update = None

    def predict_expected_return(self, macro_state, gpd_centers):
        row_counts = self.prior_matrix[macro_state, :]
        probs = row_counts / np.sum(row_counts)
        return float(np.sum(probs * gpd_centers))

    def track_state(self, macro_state):
        self.pending_update = {"macro_state": macro_state}

    def get_fsm(self):
        return self.prior_matrix


# ==========================================
# Ray Worker
# ==========================================
@ray.remote(num_cpus=0.2)
def run_pipeline(
    sid: bytes,
    config: dict,
    tick_data: pl.DataFrame,
    bench_ref: pa.Table
    ):
    output_dir = "/tmp/backtest_results/parquet"
    os.makedirs(output_dir, exist_ok=True)
    parquet_path = f"{output_dir}/{sid.decode('utf-8')}.parquet"
    
    if sid not in tick_data or tick_data[sid].num_rows == 0:
        return {"sid": sid, "status": "no_data"}
        
    hf_df = extract_from_beta_with_freq(
        raw=tick_data[sid], bench_ref=bench_ref, 
        rolling_freq=config["rolling_freq"], ewm_span=config["ewm_span"]
    )
    
    m = int(config["ndays"] * np.floor(4 * 60 / config["downsample"]))
    _features = extract_asset_feature(hf_df=hf_df, downsample=config["downsample"], m=m, amplify=1000)
    panel_df = pl.DataFrame(_features).sort(["sid", "date_int"])

    eval_panel_df = panel_df.filter(pl.col("date_int") >= start_date)
    if len(eval_panel_df) < 10:
        return {"sid": sid, "status": "insufficient_data"}

    # calculate gpd
    gpd_dict = build_rolling_gpd(
        panel_df, 
        quantiles=config["gpd_quantiles"], 
        loopback=config["loopback"], 
        freq_month=config["gpd_freq_month"]
    )
    # calculate macro 
    macro_state = compute_rolling_macro_states(bench_ref, config["lookback"])

    # calculate fsm 
    records =[]
    threshold_d = math.sqrt(2 * m * (1 - config["threshold_r"]))
    z_motif = robust_z_normalize(config["learned_motif"])
    fsm = BayesianOnlineFSM(prior_matrix=config["fsm_prior"])

    for row in eval_panel_df.iter_rows(named=True):
        date_int = row["date_int"]
        curve_m = row["curve"]
        daily_ret = row["daily_ret"]
        daily_beta = row["last_beta"] 
        
        edges, centers = gpd_dict[date_int]
        fsm.update_posterior(realized_ret=daily_ret, gpd_edges=edges)
            
        z_today = robust_z_normalize(curve_m)
        dist = np.linalg.norm(z_today - z_motif) # replace by dtw
        
        if dist < threshold_d:
            macro_state = macro_state.get(date_int, 1) 
            pred_score = fsm.predict_expected_return(macro_state, centers)
            
            records.append({
                "date": date_int, "distance": float(dist), 
                "beta": float(daily_beta), "macro_state": int(macro_state), 
                "pred_score": float(pred_score), "prior_matrix": fsm.get_fsm()
            })
            fsm.track_state(macro_state)
            
    if records:
        pl.DataFrame(records).write_parquet(parquet_path)
        return {"sid": sid, "status": "success", "triggers": len(records), "path": parquet_path}
    return {"sid": sid, "status": "no_triggers"}
