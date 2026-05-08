# Best trial config: {'rolling_freq': 28, 'ewm_span': 27, 'downsample': 16, 'ndays': 1, 'threshold_r': 0.9365181748464984}

#! /usr/bin/env python3
# -*- encondig: utf-8 -*-

import os
import ray
import math
import numpy as np
import pyarrow as pa
import polars as pl
from dtaidistance import dtw
from typing import List, Any, Dict

from bt_sdk.core.client import FactorTopic
from bt_sdk.core.protocol import QueryBody
from workflow.function import *


class BayesianOnlineFSM:
    def __init__(self, prior_matrix):
        # Postperior Dirichlet
        # np.ones((num_macro_states, num_micro_bins))
        self.prior_matrix = prior_matrix if isinstance(prior_matrix, np.ndarray) else np.array(prior_matrix) 
        self.num_micro_bins = self.prior_matrix.shape[1]
        self.pending_update = None 

    def update_posterior(self, realized_ret, gpd_edges):
        if self.pending_update is not None and len(gpd_edges) > 0:
            pre_macro_state = self.pending_update["macro_state"]
            
            real_bin = np.digitize(realized_ret, gpd_edges)
            real_bin = min(max(real_bin, 0), self.num_micro_bins - 1) # to avoid surpass
            
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
@ray.remote(num_cpus=0.2, num_gpus=0)
def run_pipeline(
    sid_bytes: bytes,
    trial_config: dict,
    tick_data: pl.DataFrame,
    bench_ref: pa.Table
    ):
    if len(tick_data[sid_bytes]) == 0:
        return {"sid": sid, "status": "no_data", "tick_data": tick_data}
    
    sid = sid_bytes.decode('utf-8')
    config = trial_config["config"]
        
    hf_df = process_to_residuals(tick_data, config["signal_type"])
    
    _features = extract_asset_feature(hf_df=hf_df[sid], downsample=config["downsample"], m=config["m"], amplify=1000)
    panel_df = pl.DataFrame(_features).sort(["date_int"])

    eval_panel_df = panel_df.filter(pl.col("date_int") >= trial_config["start_date"])
    if len(eval_panel_df) < 10:
        return {"sid": sid, "status": "insufficient_data"}
    
    # threshold_d = math.sqrt(2 * m * (1 - config["threshold_r"]))
    z_motif = robust_z_normalize(trial_config["learned_motif"])
    # calculate gpd and macro
    gpd_dict = build_rolling_gpd(
        panel_df, 
        quantiles=config["gpd_quantiles"], 
        loopback=config["loopback"], 
        freq_month=config["gpd_freq_month"]
    )
    macro_states = compute_rolling_macro_states(bench_ref, config["loopback"])

    records =[]
    for row in eval_panel_df.iter_rows(named=True):
        date_int = row["date_int"]
        curve_m = row["curve"]
        daily_ret = row["daily_ret"]
        
        edges, centers = gpd_dict[date_int]
            
        z_today = robust_z_normalize(curve_m)
        # dist = np.linalg.norm(z_today - z_motif) # replace by dtw
        dist = dtw.distance_fast(
            z_today, 
            z_motif, 
            window=config["dtw_window"], 
            max_dist=config["threshold_d"] 
        )
        
        if dist < config["threshold_d"]:
            macro_state = macro_states.get(date_int, 1) 

            records.append({
                "date": date_int, "distance": float(dist), 
                "edges": edges, "centes": centers, 
                "macro_state": int(macro_state), 
            })
            
    if records:
        print("records", len(records))
        output = trial_config["output"]
        parquet_path = f"{output}/{sid}.parquet"
        pl.DataFrame(records).write_parquet(parquet_path)
        return {"sid": sid, "status": "success", "triggers": len(records), "path": parquet_path}
    return {"sid": sid, "status": "no_triggers"}
